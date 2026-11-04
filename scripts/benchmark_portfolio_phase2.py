"""Local 512MiB address-space experiment, NOT a Render cgroup certification.

Run: .venv/bin/python scripts/benchmark_portfolio_phase2.py --output reports/design/PORTFOLIO_PHASE2_RESOURCES.json
Uses only existing actual 28-asset V1 data. No synthetic columns or new data.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import resource
import socket
import statistics
import subprocess
import sys
import tempfile
import time
import urllib.request
import urllib.error

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
LIMIT = 512 * 1024 * 1024


def stats(durations):
    values = sorted(durations)
    return {'requests':len(values), 'median_ms':round(statistics.median(values)*1000,3),
            'p95_ms':round(values[min(len(values)-1, int(len(values)*.95))]*1000,3),
            'max_ms':round(max(values)*1000,3)}


def peak_mib(pid):
    for line in Path(f'/proc/{pid}/status').read_text().splitlines():
        if line.startswith('VmHWM:'):
            return round(int(line.split()[1])/1024,3)
    return None


def limit_address_space():
    resource.setrlimit(resource.RLIMIT_AS, (LIMIT,LIMIT))


def v2_worker():
    limit_address_space()
    from src.portfolio.v2 import build_bundle, load_research_bundle, analyze_bundle, compare_bundle, V2Request, V2CompareRequest
    from scripts.portfolio_phase2_replay import real_replay_inputs
    with tempfile.TemporaryDirectory(prefix='mpri-phase2-replay-') as tmp:
        build_bundle(tmp,'local-real-v1',*real_replay_inputs())
        start=time.perf_counter();bundle=load_research_bundle(Path(tmp)/'local-real-v1');cold=time.perf_counter()-start
        def request(name):
            raw=json.loads((ROOT/f'examples/portfolio/{name}.json').read_text())
            return V2Request(snapshot_id='local-real-v1',market='US',base_currency='USD',holdings=raw['holdings'],value_amount=raw['value_usd'])
        before=request('before');after=request('after');comparison=V2CompareRequest(current=before,proposed=after)
        ten=before.model_copy(update={'holdings':[type(before.holdings[0])(ticker=t,weight=10) for t in list(bundle.universe.index)[:10]]})
        ten_comparison=V2CompareRequest(current=ten,proposed=ten)
        rows=[]
        for concurrency in (1,2,4):
            for name,operation in [('analyze',lambda:analyze_bundle(bundle,before)),('compare',lambda:compare_bundle(bundle,comparison)),('analyze_10',lambda:analyze_bundle(bundle,ten)),('compare_10',lambda:compare_bundle(bundle,ten_comparison))]:
                def run(_):
                    start=time.perf_counter();result=operation();elapsed=time.perf_counter()-start
                    if name=='analyze':assert result['analysis']['volatility']==23.38
                    elif name=='compare':assert result['proposed']['analysis']['volatility']==16.94
                    elif name=='analyze_10':assert len(result['analysis']['allocation'])==10
                    else:assert len(result['proposed']['analysis']['allocation'])==10
                    return elapsed
                with ThreadPoolExecutor(max_workers=concurrency) as pool:
                    durations=list(pool.map(run,range(12)))
                rows.append({'concurrency':concurrency,'operation':name,**stats(durations)})
        print(json.dumps({'scope':'research_only_existing_actual_28','cold_load_ms':round(cold*1000,3),
                          'peak_rss_mib':peak_mib(os.getpid()),'address_space_limit_mib':512,'workloads':rows}))


def http_benchmark(env):
    with socket.socket() as bound:
        bound.bind(('127.0.0.1',0));port=bound.getsockname()[1]
    with tempfile.TemporaryFile() as log:
        server=subprocess.Popen([sys.executable,'-m','uvicorn','src.portfolio.server:app','--host','127.0.0.1','--port',str(port),'--workers','1','--log-level','warning'],cwd=ROOT,env=env,stdout=log,stderr=log,preexec_fn=limit_address_space)
        try:
            url=f'http://127.0.0.1:{port}'
            for _ in range(100):
                if server.poll() is not None:
                    log.seek(0);raise RuntimeError(log.read().decode()[-2000:])
                try:
                    with urllib.request.urlopen(url+'/health',timeout=1) as response:assert response.status==200
                    break
                except (OSError,urllib.error.URLError):time.sleep(.1)
            else:raise RuntimeError('Local server startup timed out')
            with urllib.request.urlopen(url+'/api/portfolio/v2/catalog',timeout=5) as response:
                assert len(json.load(response)['assets'])==80
            requests={name:json.loads((ROOT/f'examples/portfolio/{name}.json').read_text()) for name in ('before','after')}
            ten={'holdings':[{'ticker':t,'weight':10} for t in ['AAPL','MSFT','NVDA','GOOGL','META','AMZN','JPM','BAC','XOM','CVX']],'value_usd':100000}
            def call(operation):
                body=(ten if operation=='analyze_10' else {'current':ten,'proposed':ten}) if operation.endswith('_10') else (requests['before'] if operation=='analyze' else {'current':requests['before'],'proposed':requests['after']})
                request=urllib.request.Request(url+'/api/portfolio/'+operation.replace('_10',''),data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
                start=time.perf_counter()
                with urllib.request.urlopen(request,timeout=30) as response:result=json.load(response)
                elapsed=time.perf_counter()-start
                if operation=='analyze':assert result['volatility']==23.38
                elif operation=='compare':assert result['proposed']['volatility']==16.94
                elif operation=='analyze_10':assert len(result['allocation'])==10
                else:assert len(result['proposed']['allocation'])==10
                return elapsed
            cold=call('analyze');baseline=peak_mib(server.pid);rows=[]
            for concurrency in (1,2,4):
                for operation in ('analyze','compare','analyze_10','compare_10'):
                    with ThreadPoolExecutor(max_workers=concurrency) as pool:
                        durations=list(pool.map(lambda _:call(operation),range(12)))
                    rows.append({'concurrency':concurrency,'operation':operation,**stats(durations)})
            return {'scope':'actual_v1_http_28_and_catalog_80','cold_analyze_ms':round(cold*1000,3),
                    'post_first_request_high_water_rss_mib':baseline,'peak_rss_mib':peak_mib(server.pid),
                    'address_space_limit_mib':512,'workers':1,'blas_threads':1,'workloads':rows}
        except Exception as error:
            log.seek(0)
            raise RuntimeError('Local benchmark failed; peak RSS MiB='+str(peak_mib(server.pid))+'; server log: '+log.read().decode()[-4000:]) from error
        finally:
            server.terminate()
            try:server.wait(timeout=5)
            except subprocess.TimeoutExpired:server.kill();server.wait()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output');parser.add_argument('--v2-worker',action='store_true');args=parser.parse_args()
    if args.v2_worker:v2_worker();return
    env={**os.environ,'OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1','MKL_NUM_THREADS':'1'}
    result={'measured_on':'2026-11-04','render_actual_test':False,'new_approved_assets':0,
            'limitations':['Linux local CPU differs from Render Free', 'RLIMIT_AS limits virtual address space, not cgroup RSS',
                           'No new approved 60-100 asset workload exists', 'Frontend service RSS and shared platform overhead are excluded'],
            'v1_http':http_benchmark(env)}
    child=subprocess.run([sys.executable,__file__,'--v2-worker'],cwd=ROOT,env=env,capture_output=True,text=True,check=True)
    result['v2_research']=json.loads(child.stdout)
    payload=json.dumps(result,indent=2)+'\n'
    if args.output:Path(args.output).write_text(payload)
    else:print(payload)
    print('PASS: existing actual 28-asset HTTP and V2 local research replay under 512MiB address-space cap')


if __name__=='__main__':main()
