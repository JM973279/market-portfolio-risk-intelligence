"""Capture real local contracts for comparing an archived release with HEAD.

Run this absolute script from each release root and write output outside Git.
Uses TestClient only; never sends production requests or creates prices.
"""
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path.cwd()))
from fastapi.testclient import TestClient
from src.portfolio.server import app


def main():
    result = {}
    with TestClient(app) as client:
        for path in ['/health', '/api/portfolio/universe', '/api/portfolio/scenarios']:
            response = client.get(path)
            result[path] = {'status':response.status_code, 'body':response.json()}
        samples = {}
        for name in ['before', 'after']:
            raw = json.loads((Path('examples/portfolio')/(name+'.json')).read_text())
            samples[name] = raw
            response = client.post('/api/portfolio/analyze', json=raw)
            result[name] = {'status':response.status_code, 'body':response.json()}
        response = client.post('/api/portfolio/compare', json={'current':samples['before'], 'proposed':samples['after']})
        result['compare'] = {'status':response.status_code, 'body':response.json()}
        result['invalid_status'] = client.post('/api/portfolio/analyze', json={}).status_code
        result['all_28_single_asset'] = {}
        for asset in result['/api/portfolio/universe']['body']['assets']:
            ticker = asset['ticker']
            response = client.post('/api/portfolio/analyze', json={
                'holdings':[{'ticker':ticker, 'weight':100}], 'value_usd':100000})
            assert response.status_code == 200
            canonical = json.dumps(response.json(), sort_keys=True, separators=(',', ':')).encode()
            result['all_28_single_asset'][ticker] = hashlib.sha256(canonical).hexdigest()
        assert len(result['all_28_single_asset']) == 28
        result['catalog_status'] = client.get('/api/portfolio/v2/catalog').status_code
        schema = app.openapi()
        result['schemas'] = schema['components']['schemas']
        result['paths'] = {k:v for k,v in schema['paths'].items() if k in [
            '/health', '/api/portfolio/universe', '/api/portfolio/scenarios',
            '/api/portfolio/analyze', '/api/portfolio/compare']}
    Path(sys.argv[1]).write_text(json.dumps(result, sort_keys=True)+'\n')


if __name__ == '__main__':
    main()
