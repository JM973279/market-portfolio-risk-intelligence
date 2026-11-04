"""Real HTTP fault/status matrix, local child server only; never targets Render."""
from concurrent.futures import ThreadPoolExecutor
import json
import math
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.benchmark_portfolio_phase3 import request, process_sample


def main():
    env = {**os.environ, 'MPRI_PHASE3_LOCAL_PROBE':'1', 'MPRI_PHASE3_AS_MIB':'512',
           'MPRI_PHASE4_FAULT_TESTS':'1', 'OPENBLAS_NUM_THREADS':'1', 'OMP_NUM_THREADS':'1', 'MKL_NUM_THREADS':'1'}
    with socket.socket() as bound:
        bound.bind(('127.0.0.1', 0))
        port = bound.getsockname()[1]
    report = {'scope':'loopback_AS512_fault_matrix', 'production_timeout_seconds':25,
              'fixture_timeout_seconds':.5, 'actual_cgroup_certification':False, 'rows':[]}
    with tempfile.TemporaryFile() as log:
        server = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'scripts.portfolio_phase4_probe:create_app',
            '--factory', '--host', '127.0.0.1', '--port', str(port), '--log-level', 'warning'],
            cwd=ROOT, env=env, stdout=log, stderr=log)
        try:
            url = f'http://127.0.0.1:{port}'
            for _ in range(100):
                if request(url, '/_phase3/diagnostics')['status'] == 200:
                    break
                time.sleep(.05)
            else:
                raise RuntimeError('Local fault fixture unavailable')
            raw = json.loads((ROOT/'examples/portfolio/before.json').read_text())
            assert request(url, '/api/portfolio/analyze', raw)['status'] == 200
            for concurrency in [1, 2, 4]:
                for path, expected in [('address-pressure',503), ('unknown-defect',500), ('slow',504)]:
                    gate = threading.Barrier(concurrency)
                    def run(_):
                        gate.wait()
                        return request(url, '/_phase4/fault/'+path)
                    with ThreadPoolExecutor(max_workers=concurrency) as pool:
                        results = list(pool.map(run, range(concurrency)))
                    assert all(r['status'] == expected for r in results), results
                    # A timed-out running calculation retains its real slot.
                    if path == 'slow':
                        time.sleep(.65)
                    assert request(url, '/health')['status'] == 200
                    latency = sorted(round(r['seconds']*1000,3) for r in results)
                    report['rows'].append({'concurrency':concurrency, 'fault':path, 'statuses':{str(expected):len(results)},
                        'p95_ms':latency[math.ceil(.95*len(latency))-1], 'max_ms':max(latency),
                        'memory_after':process_sample(server.pid), 'recovered_health':200})
            assert request(url, '/api/portfolio/analyze', raw)['status'] == 200
            Path(sys.argv[1]).write_text(json.dumps(report, indent=2)+'\n')
            print(json.dumps(report))
        finally:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait()


if __name__ == '__main__':
    main()
