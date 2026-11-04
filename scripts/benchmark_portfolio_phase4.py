"""Reuse the same Phase 3 workloads with bounded Phase 4 private HTTP routes."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.benchmark_portfolio_phase3 import run_trial, RESEARCH_ID


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True)
    parser.add_argument('--trials',type=int,default=3);parser.add_argument('--requests',type=int,default=24)
    args=parser.parse_args()
    if not (ROOT/'data/portfolio_expansion/research'/RESEARCH_ID).exists():
        subprocess.run([sys.executable,'scripts/portfolio_phase2_replay.py','--snapshot-id',RESEARCH_ID],cwd=ROOT,check=True,stdout=subprocess.DEVNULL)
    report={'measured_on':'2026-11-04','scope':'existing_actual_28_only_bounded_v1_v2_private_http',
            'render_certification':False,'trials':[]}
    for name,as_mib,tokens in [('as512_default',512,0),('as512_tokens4',512,4),('unlimited_default',0,0)]:
        config={'name':name,'as_mib':as_mib,'thread_tokens':tokens,'probe_factory':'scripts.portfolio_phase4_probe:create_app'}
        for trial in range(1,args.trials+1):
            result=run_trial(config,trial,args.requests);report['trials'].append(result)
            Path(args.output).write_text(json.dumps(report,indent=2)+'\n')
            failures=sum(row['requests']-row['statuses'].get('200',0) for row in result['workloads'])
            print(json.dumps({'configuration':name,'trial':trial,'failures':failures,'thread_creation_failure':result['thread_creation_failure'],
                              'peak':result['peak'],'harness_error':result.get('harness_error')}),flush=True)


if __name__=='__main__':main()
