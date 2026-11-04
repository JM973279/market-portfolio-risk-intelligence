"""Loopback-only real HTTP overload/deadline/ENOMEM/status checks."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.benchmark_portfolio_phase3 import request,process_sample


def main():
    env={**os.environ,'MPRI_PHASE3_LOCAL_PROBE':'1','MPRI_PHASE3_AS_MIB':'512','MPRI_PHASE4_FAULT_TESTS':'1',
         'OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1','MKL_NUM_THREADS':'1'}
    with socket.socket() as bound:bound.bind(('127.0.0.1',0));port=bound.getsockname()[1]
    with tempfile.TemporaryFile() as log:
        server=subprocess.Popen([sys.executable,'-m','uvicorn','scripts.portfolio_phase4_probe:create_app','--factory',
                                 '--host','127.0.0.1','--port',str(port),'--log-level','warning'],cwd=ROOT,env=env,stdout=log,stderr=log)
        try:
            url=f'http://127.0.0.1:{port}'
            for _ in range(100):
                if request(url,'/_phase3/diagnostics')['status']==200:break
                time.sleep(.05)
            else:raise RuntimeError('Local fault server failed to start')
            report={'measured_on':'2026-11-04','scope':'private_loopback_fault_fixtures',
                    'fixture_timeout_seconds':.5,'production_timeout_seconds':25,'as_limit_mib':512}
            raw=json.loads((ROOT/'examples/portfolio/before.json').read_text())
            assert request(url,'/api/portfolio/analyze',raw)['status']==200
            report['invalid_input']=request(url,'/api/portfolio/analyze',{})['status']
            v2={'snapshot_id':'no-approved-release','market':'US','base_currency':'USD','holdings':raw['holdings'],'value_amount':raw['value_usd']}
            report['unsupported_v2']=request(url,'/api/portfolio/v2/analyze',v2)['status']
            pressure=request(url,'/_phase4/fault/address-pressure')
            report['real_mmap_enomem_status']=pressure['status']
            report['health_after_pressure']=request(url,'/health')['status']
            gate=threading.Barrier(8)
            def run(_):gate.wait();return request(url,'/_phase4/fault/slow')
            with ThreadPoolExecutor(max_workers=8) as pool:results=list(pool.map(run,range(8)))
            report['overload_statuses']={str(status):sum(r['status']==status for r in results) for status in {r['status'] for r in results}}
            report['health_while_timed_out_job_still_running']=request(url,'/health')['status']
            time.sleep(.65)
            report['health_after_real_completion']=request(url,'/health')['status']
            report['normal_analysis_after_recovery']=request(url,'/api/portfolio/analyze',raw)['status']
            report['unknown_defect_status']=request(url,'/_phase4/fault/unknown-defect')['status']
            report['memory_after']=process_sample(server.pid)
            assert report['invalid_input']==422 and report['unsupported_v2']==409
            assert report['real_mmap_enomem_status']==503 and report['health_after_pressure']==200
            assert report['overload_statuses']=={'503':4,'504':4}
            assert report['health_while_timed_out_job_still_running']==503
            assert report['health_after_real_completion']==200 and report['normal_analysis_after_recovery']==200
            assert report['unknown_defect_status']==500
            log.seek(0);report['server_log']=log.read().decode().replace(str(ROOT),'<repo>')[-12000:]
            Path(sys.argv[1]).write_text(json.dumps(report,indent=2)+'\n')
            print(json.dumps({k:v for k,v in report.items() if k!='server_log'}))
        finally:
            server.terminate()
            try:server.wait(timeout=5)
            except subprocess.TimeoutExpired:server.kill();server.wait()


if __name__=='__main__':main()
