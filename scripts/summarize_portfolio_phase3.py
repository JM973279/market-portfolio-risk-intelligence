"""Rebuild summary from saved Phase 3 trials without pooling trial percentiles."""
import json
from pathlib import Path
root=Path('reports/design')
matrix=json.loads((root/'PORTFOLIO_PHASE3_BENCHMARKS.json').read_text())
summary={'measured_on':'2026-11-04','scope':matrix['scope'],'new_public_approvals':0,
         'render_certification':False,'groups':[],'latency_ranges':[]}
for name in dict.fromkeys(t['configuration']['name'] for t in matrix['trials']):
 trials=[t for t in matrix['trials'] if t['configuration']['name']==name]
 workloads=[w for t in trials for w in t['workloads']]
 errors=sum(w['requests']-w['statuses'].get('200',0) for w in workloads)
 group={'configuration':name,'trials':len(trials),'workload_requests':sum(w['requests'] for w in workloads),
        'non_200_requests':errors,'thread_failure_trials':sum(t['thread_creation_failure'] for t in trials),
        'max_rss_mib':round(max(t['peak']['VmHWM'] for t in trials)/1024,3),
        'max_vm_peak_mib':round(max(t['peak']['VmPeak'] for t in trials)/1024,3),
        'max_os_threads':max(t['peak']['Threads'] for t in trials),
        'max_noaccess_anon_mib':max(t['peak']['large_anon_noaccess_mib'] for t in trials),
        'health_after':[t['health_after'] for t in trials],
        'public_v2_status':[t['public_v2_status'] for t in trials]}
 summary['groups'].append(group)
 if name=='unlimited_default':
  for concurrency in (1,2,4):
   for version in ('v1','v2'):
    for operation in ('analyze','compare','analyze_10','compare_10'):
     rows=[w for w in workloads if w['concurrency']==concurrency and w['version']==version and w['operation']==operation]
     summary['latency_ranges'].append({'concurrency':concurrency,'version':version,'operation':operation,
                                      'trials':len(rows),'requests':sum(w['requests'] for w in rows),
                                      'p50_min_ms':min(w['p50_ms'] for w in rows),'p50_max_ms':max(w['p50_ms'] for w in rows),
                                      'p95_min_ms':min(w['p95_ms'] for w in rows),'p95_max_ms':max(w['p95_ms'] for w in rows)})
(root/'PORTFOLIO_PHASE3_SUMMARY.json').write_text(json.dumps(summary,indent=2)+'\n')
for row in summary['groups']:print(row)
print('No-address-cap p95 ranges:')
for row in summary['latency_ranges']:
 if row['concurrency']==4:print(row)
