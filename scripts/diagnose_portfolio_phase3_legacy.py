"""Instrument the unchanged Phase 2 HTTP harness; preserve failures and controls."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import urllib.error

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.benchmark_portfolio_phase3 import process_sample
from scripts import benchmark_portfolio_phase2 as legacy


def trial(configuration, number):
    env={**os.environ,'OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1','MKL_NUM_THREADS':'1'}
    env.pop('MALLOC_ARENA_MAX',None);env.pop('GLIBC_TUNABLES',None)
    if configuration=='arena2':env['MALLOC_ARENA_MAX']='2'
    original_popen=legacy.subprocess.Popen
    original_limit=legacy.limit_address_space
    original_urlopen=legacy.urllib.request.urlopen
    process=None;watcher=None;samples=[];failures=[];stop=threading.Event()
    def popen(*args,**kwargs):
        nonlocal process,watcher
        process=original_popen(*args,**kwargs)
        def monitor():
            while not stop.wait(.003):
                sample=process_sample(process.pid)
                if sample:samples.append(sample)
        watcher=threading.Thread(target=monitor,daemon=True);watcher.start()
        return process
    def urlopen(request,*args,**kwargs):
        try:return original_urlopen(request,*args,**kwargs)
        except urllib.error.HTTPError as error:
            body=json.loads(request.data) if getattr(request,'data',None) else {}
            holdings=(body.get('current') or body).get('holdings',[])
            failures.append({'http_status':error.code,'operation':request.full_url.rsplit('/',1)[-1],
                             'holding_count':len(holdings),'memory_at_error':process_sample(process.pid)})
            raise
    legacy.subprocess.Popen=popen;legacy.urllib.request.urlopen=urlopen
    if configuration=='unlimited':legacy.limit_address_space=lambda:None
    row={'configuration':configuration,'trial':number}
    try:
        row['benchmark']=legacy.http_benchmark(env)
        row['success']=True
    except Exception as error:
        row['success']=False
        row['exception']=str(error).replace(str(ROOT),'<repo>')
    finally:
        stop.set()
        if watcher:watcher.join(timeout=2)
        legacy.subprocess.Popen=original_popen;legacy.limit_address_space=original_limit
        legacy.urllib.request.urlopen=original_urlopen
    row['failures']=failures
    row['peak']={key:max((s.get(key,0) for s in samples),default=0) for key in
                 ('VmSize','VmPeak','VmRSS','VmHWM','Threads','large_anon_noaccess_regions','large_anon_noaccess_mib')}
    return row


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True)
    parser.add_argument('--default-trials',type=int,default=5);args=parser.parse_args()
    report={'scope':'unchanged_phase2_http_harness_existing_actual_28','measured_on':'2026-11-04','trials':[]}
    for config,count in [('default',args.default_trials),('arena2',3),('unlimited',3)]:
        for number in range(1,count+1):
            row=trial(config,number);report['trials'].append(row)
            Path(args.output).write_text(json.dumps(report,indent=2)+'\n')
            print(json.dumps({key:row[key] for key in ('configuration','trial','success','failures','peak')}),flush=True)


if __name__=='__main__':main()
