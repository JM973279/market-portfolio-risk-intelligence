"""Local archive ingestion/replay CLI. No network transport or public activation.

python scripts/portfolio_price_engine.py ingest config.json --run-id research-001 \
    --code-version ee301f6+phase7b --revision-note 'initial archive review'
python scripts/portfolio_price_engine.py replay research-001

Config paths are relative to the config file. All output artifacts go exclusively
under data/portfolio_expansion/research/price_engine (gitignored).
"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pydantic import ValidationError
from src.portfolio.price_engine.adapters import (AlphaVantageArchiveAdapter,
    CsvArchiveAdapter, KrxArchiveAdapter, collect_archives, read_capture)
from src.portfolio.price_engine.contracts import (PipelineError, QualityPolicy,
    ResearchPermission, SourceReceipt, SymbolMapping, TradingCalendar, Window)
from src.portfolio.price_engine import storage


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest='action', required=True)
    ingest = actions.add_parser('ingest')
    ingest.add_argument('config', type=Path)
    ingest.add_argument('--run-id', required=True)
    ingest.add_argument('--code-version', required=True)
    ingest.add_argument('--revision-note', required=True)
    replay = actions.add_parser('replay')
    replay.add_argument('run_id')
    args = parser.parse_args(argv)
    try:
        if args.action == 'replay':
            *_, validation = storage.replay_research(storage.RESEARCH_ROOT / args.run_id)
            report = validation.report
        else:
            config = json.loads(args.config.read_text())
            permissions = [ResearchPermission.model_validate(p) for p in config['permissions']]
            mappings = [SymbolMapping.model_validate(m) for m in config['mappings']]
            if len({m.instrument.asset_id for m in mappings}) != len(mappings):
                raise PipelineError('DUPLICATE_ASSET_MAPPING')
            mappings = {m.instrument.asset_id: m for m in mappings}
            factories = {'csv': CsvArchiveAdapter, 'alpha_vantage': AlphaVantageArchiveAdapter,
                         'krx_openapi': KrxArchiveAdapter}
            jobs = []
            for job in config['archives']:
                mapping = mappings[job['asset_id']]
                grant = next((p for p in permissions if p.source_id == mapping.source_id), None)
                if not grant or not grant.storage_allowed or not grant.processing_allowed:
                    raise PipelineError('RESEARCH_PERMISSION_REQUIRED')
                factory = factories[job['adapter']]
                adapter = factory(mapping.source_id) if factory is CsvArchiveAdapter else factory()
                receipt = SourceReceipt.model_validate(job['receipt'])
                jobs.append((adapter, mapping, read_capture(args.config.parent / job['path'], receipt)))
            collection = collect_archives(jobs, permissions)
            calendars = [TradingCalendar.model_validate(c) for c in config['calendars']]
            window = Window.model_validate(config['window'])
            policy = QualityPolicy.model_validate(config.get('policy', {}))
            storage.save_research(args.run_id, collection, calendars, window, policy=policy,
                                  code_version=args.code_version, revision_note=args.revision_note)
            *_, validation = storage.replay_research(storage.RESEARCH_ROOT / args.run_id)
            report = validation.report
        print(json.dumps(report, ensure_ascii=False, allow_nan=False, indent=2))
        return 0 if report['research_ready'] else 2
    except PipelineError as error:
        print(json.dumps(error.as_dict(), ensure_ascii=False), file=sys.stderr)
        return 2
    except (OSError, ValueError, KeyError, TypeError, ValidationError):
        # Do not echo input contents, source credentials or unreviewed price data.
        print(json.dumps({'code': 'INVALID_LOCAL_INPUT_OR_ARTIFACT'}), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
