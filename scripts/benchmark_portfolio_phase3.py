"""Repeatable HTTP/allocator/virtual-memory diagnosis with existing real data only.

No production changes, approval bypass, external data download or Render request.
Run with .venv/bin/python; writes only summaries, never return matrices/prices.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import platform
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import urllib.error

ROOT = Path(__file__).resolve().parents[1]
RESEARCH_ID = 'phase3-existing-v1-replay'


def process_sample(pid):
    values = {}
    try:
        for line in Path(f'/proc/{pid}/status').read_text().splitlines():
            key = line.split(':',1)[0]
            if key in {'VmSize','VmPeak','VmRSS','VmHWM','Threads'}:
                values[key] = int(line.split()[1])
        reserved = []
        for line in Path(f'/proc/{pid}/maps').read_text().splitlines():
            parts = line.split()
            if parts[1] == '---p' and len(parts) == 5:
                start,end = (int(v,16) for v in parts[0].split('-'))
                if end-start >= 32*1024**2:
                    reserved.append(end-start)
        values['large_anon_noaccess_regions'] = len(reserved)
        values['large_anon_noaccess_mib'] = round(sum(reserved)/1024**2,3)
    except (OSError, ValueError, IndexError):
        pass
    return values


def request(url, path, body=None):
    call = urllib.request.Request(url+path, data=None if body is None else json.dumps(body).encode(),
                                  headers={'Content-Type':'application/json'})
    start=time.perf_counter()
    try:
        with urllib.request.urlopen(call, timeout=10) as response:
            payload=json.load(response)
            return {'status':response.status,'seconds':time.perf_counter()-start,'payload':payload}
    except urllib.error.HTTPError as error:
        error.read()
        return {'status':error.code,'seconds':time.perf_counter()-start}
    except (OSError,ValueError) as error:
        return {'status':0,'seconds':time.perf_counter()-start,'error_type':type(error).__name__}


def percentiles(results):
    durations=sorted(r['seconds']*1000 for r in results)
    statuses={}
    for row in results:
        key=str(row['status']);statuses[key]=statuses.get(key,0)+1
    def nearest(p):
        import math
        return round(durations[max(0,math.ceil(len(durations)*p)-1)],3)
    return {'requests':len(results),'statuses':statuses,'p50_ms':nearest(.5),'p95_ms':nearest(.95),'max_ms':round(durations[-1],3)}


def validate_response(version, operation, payload, golden):
    if operation.endswith('_10'):
        analyses = [payload['current']['analysis'],payload['proposed']['analysis']] if version=='v2' and operation.startswith('compare') else [payload['current'],payload['proposed']] if operation.startswith('compare') else [payload['analysis'] if version=='v2' else payload]
        for analysis in analyses:
            assert len(analysis['allocation'])==10
            assert len(analysis['stress'])==3
            assert abs(sum(r['share'] for r in analysis['risk_contribution'])-100)<.1
    elif version=='v1':
        expected = golden['comparison'] if operation=='compare' else golden['responses']['before']
        assert payload==expected
    elif operation=='analyze':
        for key,value in payload['analysis'].items():
            assert value==golden['responses']['before'][key], key
    else:
        assert payload['comparison']==golden['comparison']['comparison']
        for label,example in [('current','before'),('proposed','after')]:
            for key,value in payload[label]['analysis'].items():
                assert value==golden['responses'][example][key], key


def run_trial(configuration, trial_number, requests_per_case):
    env={**os.environ,'OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1','MKL_NUM_THREADS':'1',
         'MPRI_PHASE3_LOCAL_PROBE':'1','MPRI_PHASE3_AS_MIB':str(configuration['as_mib']),
         'MPRI_PHASE3_THREAD_TOKENS':str(configuration.get('thread_tokens',0)),
         'MPRI_PHASE3_RESEARCH_PATH':str(ROOT/'data/portfolio_expansion/research'/RESEARCH_ID)}
    env.pop('MALLOC_ARENA_MAX',None)
    env.pop('GLIBC_TUNABLES',None)
    if configuration.get('arena_max'):
        env['MALLOC_ARENA_MAX']=str(configuration['arena_max'])
    with socket.socket() as bound:
        bound.bind(('127.0.0.1',0));port=bound.getsockname()[1]
    with tempfile.TemporaryFile() as log:
        server=subprocess.Popen([sys.executable,'-m','uvicorn',configuration.get('probe_factory','scripts.portfolio_phase3_probe:create_app'),'--factory',
                                 '--host','127.0.0.1','--port',str(port),'--workers','1','--log-level','warning'],
                                cwd=ROOT,env=env,stdout=log,stderr=log)
        samples=[];stop=threading.Event()
        def monitor():
            while not stop.wait(.005):
                sample=process_sample(server.pid)
                if sample:samples.append(sample)
        watcher=threading.Thread(target=monitor,daemon=True);watcher.start()
        result={'configuration':configuration,'trial':trial_number,'workloads':[]}
        try:
            url=f'http://127.0.0.1:{port}'
            for _ in range(150):
                if server.poll() is not None:raise RuntimeError('Probe startup failed')
                probe=request(url,'/_phase3/diagnostics')
                if probe['status']==200:
                    result['diagnostics']=probe['payload'];break
                time.sleep(.05)
            else:raise RuntimeError('Probe startup timed out')
            golden=json.loads((ROOT/'tests/fixtures/portfolio_v1_golden.json').read_text())
            before=golden['requests']['before'];after=golden['requests']['after']
            ten={'holdings':[{'ticker':t,'weight':10} for t in ['AAPL','MSFT','NVDA','GOOGL','META','AMZN','JPM','BAC','XOM','CVX']],'value_usd':100000}
            def v2_body(raw):
                return {'snapshot_id':RESEARCH_ID,'market':'US','base_currency':'USD','holdings':raw['holdings'],'value_amount':raw['value_usd']}
            def call(version,operation):
                compare=operation.startswith('compare')
                first=ten if operation.endswith('_10') else before
                second=ten if operation.endswith('_10') else after
                if version=='v2':first,second=v2_body(first),v2_body(second)
                body={'current':first,'proposed':second} if compare else first
                path=('/api/portfolio/' if version=='v1' else '/_phase3/research/')+('compare' if compare else 'analyze')
                response=request(url,path,body)
                if response['status']==200:
                    validate_response(version,operation,response.pop('payload'),golden)
                else:response['memory_at_error']=process_sample(server.pid)
                return response
            for version in ('v1','v2'):
                cold=call(version,'analyze')
                result.setdefault('cold',{})[version]={key:value for key,value in cold.items()}
            for concurrency in (1,2,4):
                for version in ('v1','v2'):
                    for operation in ('analyze','compare','analyze_10','compare_10'):
                        with ThreadPoolExecutor(max_workers=concurrency) as pool:
                            responses=list(pool.map(lambda _:call(version,operation),range(requests_per_case)))
                        result['workloads'].append({'concurrency':concurrency,'version':version,'operation':operation,
                                                    **percentiles(responses),'memory_after':process_sample(server.pid),
                                                    'errors':[row for row in responses if row['status']!=200]})
            result['health_after']=request(url,'/health')['status']
            # The real public V2 registry stays empty; research paths are local only.
            result['public_v2_status']=request(url,'/api/portfolio/v2/analyze',v2_body(before))['status']
        except Exception as error:
            result['harness_error']=type(error).__name__+': '+str(error)
        finally:
            stop.set();watcher.join(timeout=2)
            result['peak']={key:max((s.get(key,0) for s in samples),default=0) for key in
                            ('VmSize','VmPeak','VmRSS','VmHWM','Threads','large_anon_noaccess_regions','large_anon_noaccess_mib')}
            server.terminate()
            try:server.wait(timeout=5)
            except subprocess.TimeoutExpired:server.kill();server.wait()
            log.seek(0);server_log=log.read().decode(errors='replace').replace(str(ROOT),'<repo>')
            result['server_error_log']=server_log[-18000:]
            result['thread_creation_failure']="can't start new thread" in server_log
            result['process_exit_after_termination']=server.returncode
        return result


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True)
    parser.add_argument('--trials',type=int,default=3);parser.add_argument('--requests',type=int,default=24)
    parser.add_argument('--config',choices=['all','as512_default','as512_arena2','unlimited_default','as512_tokens4'],default='all')
    args=parser.parse_args()
    research=ROOT/'data/portfolio_expansion/research'/RESEARCH_ID
    if not research.exists():
        subprocess.run([sys.executable,'scripts/portfolio_phase2_replay.py','--snapshot-id',RESEARCH_ID],cwd=ROOT,check=True,stdout=subprocess.DEVNULL)
    configurations=[{'name':'as512_default','as_mib':512}, {'name':'as512_arena2','as_mib':512,'arena_max':2},
                    {'name':'unlimited_default','as_mib':0}, {'name':'as512_tokens4','as_mib':512,'thread_tokens':4}]
    if args.config!='all':configurations=[c for c in configurations if c['name']==args.config]
    report={'measured_on':'2026-11-04','scope':'existing_actual_28_only_v2_private_loopback_replay',
            'render_certification':False,'python':platform.python_version(),'libc':platform.libc_ver(),
            'host_cgroup_memory_max':Path('/sys/fs/cgroup/memory.max').read_text().strip(),
            'host_cgroup_pids_max':Path('/sys/fs/cgroup/pids.max').read_text().strip(),'trials':[]}
    for configuration in configurations:
        for trial in range(1,args.trials+1):
            result=run_trial(configuration,trial,args.requests);report['trials'].append(result)
            Path(args.output).write_text(json.dumps(report,indent=2)+'\n')
            failures=sum(row['requests']-row['statuses'].get('200',0) for row in result['workloads'])
            print(json.dumps({'configuration':configuration['name'],'trial':trial,'failures':failures,
                              'thread_creation_failure':result['thread_creation_failure'],'peak':result['peak'],
                              'harness_error':result.get('harness_error')}),flush=True)


if __name__=='__main__':main()
