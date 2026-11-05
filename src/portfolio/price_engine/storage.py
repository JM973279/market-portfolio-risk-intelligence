"""Immutable, replayable local captures under the existing ignored research root."""
import base64
from datetime import datetime, timezone
import json
from pathlib import Path
import platform

import numpy as np
import pandas as pd
import pydantic

from src.portfolio.expansion import verify_release, write_release
from .adapters import (ADAPTER_VERSION, AlphaVantageArchiveAdapter, Capture,
                       CsvArchiveAdapter, KrxArchiveAdapter, collect_archives)
from .contracts import (PipelineError, QualityPolicy, ResearchPermission,
                        SourceReceipt, SymbolMapping, TradingCalendar, Window)
from .engine import ENGINE_VERSION, validate_prices

RESEARCH_ROOT = Path(__file__).resolve().parents[3] / 'data/portfolio_expansion/research/price_engine'


def encode(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False, indent=2) + '\n').encode()


def _within_research(path):
    path = Path(path)
    # Resolving the configured root must not redirect it via an existing symlink.
    if path.absolute() != path.resolve() or RESEARCH_ROOT.absolute() != RESEARCH_ROOT.resolve():
        raise PipelineError('RESEARCH_PATH_SYMLINK_OR_TRAVERSAL')
    if not path.resolve().is_relative_to(RESEARCH_ROOT.resolve()):
        raise PipelineError('RESEARCH_DESTINATION_REQUIRED')
    return path


def save_research(run_id, collection, calendars, window, *, policy=None, revision_note,
                  code_version, previous_snapshot_id=None):
    """Validation failures may be quarantined for diagnosis, never auto-approved."""
    root = _within_research(RESEARCH_ROOT)
    policy = policy or QualityPolicy()
    validation = validate_prices(collection, calendars, window, policy)
    if validation.report['market'] is None or validation.report['currency'] is None:
        raise PipelineError('FX_POLICY_REQUIRED')
    if not code_version.strip():
        raise PipelineError('CODE_VERSION_REQUIRED')
    if any(i['code'] in {'RESEARCH_PERMISSION_REQUIRED', 'NORMALIZED_CONTENT_CHANGED'} for i in validation.report['issues']):
        raise PipelineError('RESEARCH_INPUT_NOT_AUTHORIZED_OR_IMMUTABLE')
    sources = {'captures': [
        {'content_base64': base64.b64encode(c.content).decode(), 'sha256': c.sha256,
         'receipt': c.receipt.model_dump(mode='json')} for c in collection.captures],
        'mappings': [m.model_dump(mode='json') for m in collection.mappings],
        'permissions': [p.model_dump(mode='json') for p in collection.permissions],
        'jobs': list(collection.jobs)}
    replay = {'window': window.model_dump(mode='json'), 'policy': policy.model_dump(mode='json'),
              'calendars': [c.model_dump(mode='json') for c in calendars],
              'engine_version': ENGINE_VERSION, 'adapter_version': ADAPTER_VERSION,
              'code_version': code_version,
              'dependencies': {'python': platform.python_version(), 'numpy': np.__version__,
                               'pandas': pd.__version__, 'pydantic': pydantic.__version__}}
    artifacts = {'sources.json': encode(sources), 'replay.json': encode(replay),
                 'validation.json': encode(validation.report),
                 'normalized.csv': collection.frame.to_csv(index=False, float_format='%.17g').encode()}
    return write_release(root, run_id, artifacts, {
        'snapshot_as_of': (validation.prices.index[-1].date().isoformat()
                           if validation.prices is not None else window.end.isoformat()), 'built_at': datetime.now(timezone.utc).isoformat(),
        'market': validation.report['market'], 'base_currency': validation.report['currency'],
        'methodology_version': ENGINE_VERSION, 'approval_status': 'quarantined',
        'previous_snapshot_id': previous_snapshot_id, 'revision_note': revision_note})


def replay_research(path):
    """Verify hashes, reparse raw bytes, rerun quality gates and compare outputs."""
    path = _within_research(path)
    manifest = verify_release(path)
    required = {'sources.json', 'replay.json', 'validation.json', 'normalized.csv'}
    if set(manifest['sha256']) != required or manifest['metadata']['approval_status'] != 'quarantined':
        raise PipelineError('INVALID_RESEARCH_RELEASE')
    sources = json.loads((path / 'sources.json').read_text())
    replay = json.loads((path / 'replay.json').read_text())
    if replay['engine_version'] != ENGINE_VERSION or replay['adapter_version'] != ADAPTER_VERSION:
        raise PipelineError('REPLAY_VERSION_MISMATCH')
    current_dependencies = {'python': platform.python_version(), 'numpy': np.__version__,
                            'pandas': pd.__version__, 'pydantic': pydantic.__version__}
    if replay['dependencies'] != current_dependencies:
        raise PipelineError('REPLAY_DEPENDENCY_MISMATCH')
    captures = [Capture(base64.b64decode(c['content_base64'], validate=True),
                        SourceReceipt.model_validate(c['receipt'])) for c in sources['captures']]
    if any(c.sha256 != saved['sha256'] for c, saved in zip(captures, sources['captures'])):
        raise PipelineError('SOURCE_HASH_MISMATCH')
    mappings = {m['instrument']['asset_id']: SymbolMapping.model_validate(m) for m in sources['mappings']}
    parsers = {'CsvArchiveAdapter': CsvArchiveAdapter, 'AlphaVantageArchiveAdapter': AlphaVantageArchiveAdapter,
               'KrxArchiveAdapter': KrxArchiveAdapter}
    jobs = []
    for job in sources['jobs']:
        factory = parsers.get(job['adapter'])
        if factory is None:
            raise PipelineError('REPLAY_ADAPTER_UNSUPPORTED')
        adapter = factory(job['source_id']) if factory is CsvArchiveAdapter else factory()
        jobs.append((adapter, mappings[job['asset_id']], captures[job['capture_index']]))
    collection = collect_archives(jobs, [ResearchPermission.model_validate(p) for p in sources['permissions']])
    if collection.frame.to_csv(index=False, float_format='%.17g').encode() != (path / 'normalized.csv').read_bytes():
        raise PipelineError('NORMALIZATION_REPLAY_MISMATCH')
    calendars = [TradingCalendar.model_validate(c) for c in replay['calendars']]
    window = Window.model_validate(replay['window'])
    policy = QualityPolicy.model_validate(replay['policy'])
    validation = validate_prices(collection, calendars, window, policy)
    if validation.report != json.loads((path / 'validation.json').read_text()):
        raise PipelineError('VALIDATION_REPLAY_MISMATCH')
    return collection, calendars, window, policy, validation
