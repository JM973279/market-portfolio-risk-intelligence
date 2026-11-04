"""Local replay of existing actual V1 data; no new data or rights approval."""
import json
from pathlib import Path
import pandas as pd
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.portfolio.factors import load_factor_data
from src.portfolio.universe import load_universe


def real_replay_inputs():
    prices = pd.read_csv(ROOT/'data/portfolio/prices.csv', index_col='Date', parse_dates=True).iloc[-757:]
    _, moves = load_factor_data()
    # These are the already frozen V1 exclusions, not an exemption for new providers.
    exclusions = {factor:[{'date':str(day.date()),'reason':'frozen_v1_replay_only',
                          'reference':'https://fred.stlouisfed.org/series/DGS10'}
                         for day in moves.index[moves[factor].isna()]] for factor in moves}
    scenarios = {s['id']:s for s in json.loads((ROOT/'data/portfolio/scenarios.json').read_text())['scenarios']}
    provenance = {'scope':'research_only', 'origin':'existing_frozen_v1_local_replay',
                  'dependencies':{}, 'reviews':{}, 'new_public_use_approved':False}
    metadata = {'snapshot_as_of':str(prices.index[-1].date()), 'built_at':'2026-11-04T00:00:00Z',
                'market':'US','base_currency':'USD','methodology_version':'us-v1-local-replay',
                'revision_note':'Real existing data only; no new source or public-use approval'}
    return prices, prices.index, moves, load_universe(), scenarios, provenance, exclusions, metadata



if __name__ == '__main__':
    import argparse
    import sys
    sys.path.insert(0, str(ROOT))
    from src.portfolio.v2 import build_bundle
    from src.portfolio.expansion import sha256
    parser = argparse.ArgumentParser(description='Existing V1 local research replay only; never public approval')
    parser.add_argument('--snapshot-id', required=True)
    parser.add_argument('--hash-report')
    args = parser.parse_args()
    target = ROOT/'data/portfolio_expansion/research'
    manifest = build_bundle(target, args.snapshot_id, *real_replay_inputs())
    report = {'scope':'research_only', 'new_assets':0, 'public_use_approved':False,
              'origin':'existing_frozen_v1_28', 'snapshot_id':args.snapshot_id,
              'manifest_sha256':sha256(target/args.snapshot_id/'manifest.json'),
              'artifact_sha256':manifest['sha256']}
    payload = json.dumps(report,indent=2)+'\n'
    if args.hash_report: Path(args.hash_report).write_text(payload)
    print(payload)
