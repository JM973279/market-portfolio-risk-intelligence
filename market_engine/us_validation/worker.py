"""Fresh-process bridge to hash-pinned V1. Never execute its API/refresh/trainer."""
import argparse
import contextlib
import hashlib
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
RAW_SHA = 'fbe912a1dfb39cf6944b7ee5423d33ae1be41c480767ded9c8bce83533f3f771'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(original):
    contract = json.loads((ROOT/'market_engine/operations/contract.json').read_text())
    for rel, expected in contract['original_sources'].items():
        if digest(original/rel) != expected: raise ValueError('Frozen original code hash mismatch')
    config = contract['markets']['us']
    for key in ('model','reference'):
        if digest(original/config[key]) != config[key+'_sha256']: raise ValueError('Frozen artifact hash mismatch')
    if digest(original/'data/raw/raw_market_data.csv') != RAW_SHA: raise ValueError('Frozen raw hash mismatch')
    requirements = (ROOT/'market_engine/operations/requirements.txt').read_text().splitlines()
    versions = {}
    for line in requirements:
        if '==' in line:
            name, wanted = line.split('==')
            versions[name] = importlib.metadata.version(name)
            if versions[name] != wanted: raise ValueError('Unverified inference environment: '+name)
    return contract, config, versions


def load_bridge():
    spec = importlib.util.spec_from_file_location('pinned_operational_bridge', ROOT/'market_engine/operations/run.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def model_info(model, columns):
    import numpy as np
    load_bridge().verify_model(model, columns)
    if list(model.classes_) != [0,1]: raise ValueError('Classifier class order changed')
    scaler = model.named_steps['scaler']
    payload = b''.join(np.asarray(v,dtype='<f8').tobytes() for v in [scaler.mean_,scaler.var_,scaler.scale_])
    return {'passed': True, 'features': columns, 'steps': list(model.named_steps),
            'scaler_sha256': hashlib.sha256(payload).hexdigest(), 'scaler_samples': int(scaler.n_samples_seen_),
            'training_provenance': 'cutoff_estimated_not_a_preserved_training_receipt'}


def prediction(model, features):
    import numpy as np
    values = model.predict_proba(features)
    if values.shape != (len(features),2) or not np.isfinite(values).all() or (values<0).any() or (values>1).any() or not np.allclose(values.sum(axis=1),1):
        raise ValueError('Invalid fixed model output')
    return values[:,1]


def historical_inputs(reference, new, columns):
    import numpy as np
    if new.index.has_duplicates or reference.index.has_duplicates:
        raise ValueError('Duplicate sensitivity date')
    dates = reference.index.intersection(new.index)
    baseline, changed = reference.loc[dates,columns], new.loc[dates,columns]
    if len(dates) != len(reference) or not np.isfinite(changed.to_numpy(dtype=float)).all():
        raise ValueError('Incomplete historical sensitivity inputs')
    return baseline, changed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['build','inspect','sensitivity','candidate'])
    parser.add_argument('--original', type=Path, required=True)
    parser.add_argument('--stage', type=Path, required=True)
    parser.add_argument('--input', type=Path)
    parser.add_argument('--date')
    parser.add_argument('--store', type=Path)
    parser.add_argument('--analysis')
    args = parser.parse_args()
    original, stage = args.original.resolve(), args.stage.resolve()
    if not stage.is_relative_to(Path('/tmp')): raise ValueError('Worker output must be isolated in /tmp')
    contract, config, versions = verify(original)
    # Prevent mixing the Portfolio and original V1 src packages.
    sys.path.insert(0, str(original))
    import numpy as np
    import pandas as pd
    if args.mode == 'build':
        with (stage/'calculation.log').open('w') as stream, contextlib.redirect_stdout(stream), contextlib.redirect_stderr(stream):
            load_bridge().calculate('us', stage, original, contract)
        from src.config import STRESS_QUANTILE_THRESHOLD
        result = {'versions': versions, 'quantile': STRESS_QUANTILE_THRESHOLD}
    else:
        import joblib
        model = joblib.load(original/config['model'])
        info = model_info(model, config['features'])
        reference = pd.read_csv(original/config['reference'], index_col='Date', parse_dates=True)
        if args.mode == 'inspect':
            result = info
        elif args.mode == 'sensitivity':
            new = pd.read_csv(args.input, index_col='Date', parse_dates=True)
            # Discard every date outside the frozen reference, even if supplied.
            baseline, changed = historical_inputs(reference,new,config['features'])
            dates = baseline.index
            a, b = prediction(model, baseline), prediction(model, changed)
            scaled_a = model.named_steps['scaler'].transform(baseline)
            scaled_b = model.named_steps['scaler'].transform(changed)
            leaf_a = model.named_steps['classifier'].apply(scaled_a)
            leaf_b = model.named_steps['classifier'].apply(scaled_b)
            result = {'kind': 'HISTORICAL_SENSITIVITY_NOT_OOS_EVALUATION', 'from': str(dates.min().date()),
                      'to': str(dates.max().date()), 'rows': len(dates), 'changed_outputs': int((a!=b).sum()),
                      'changed_leaf_dates': int(np.any(leaf_a!=leaf_b,axis=1).sum()),
                      'max_abs_risk_delta': float(np.max(np.abs(a-b))),
                      'threshold_050_flips': int(((a>=.5)!=(b>=.5)).sum()),
                      'max_scaled_feature_delta': dict(zip(config['features'],np.max(np.abs(scaled_a-scaled_b),axis=0).tolist())),
                      'model_contract': info}
        else:
            # Revalidate inside the inference process, not just the CLI caller.
            # No --force/allow-revision switch exists.
            sys.path.insert(0,str(ROOT))
            from market_engine.us_validation.engine import candidate_material
            from market_engine.us_validation.store import EvidenceStore
            report, frame = candidate_material(EvidenceStore(args.store), args.analysis, original)
            day = report['source_validation']['due_date']
            if args.date != day or day <= config['training_cutoff']:
                raise ValueError('Candidate date not eligible')
            features = frame.loc[[pd.Timestamp(day)],config['features']]
            if not np.isfinite(features.to_numpy(dtype=float)).all(): raise ValueError('Incomplete candidate features')
            first, second = prediction(model,features), prediction(model,features)
            if not np.array_equal(first,second): raise ValueError('Nonreproducible candidate inference')
            result = {'kind': 'PRIVATE_UNAPPROVED_CANDIDATE', 'date': day, 'risk': float(first[0]),
                      'model_contract': info, 'public_approved': False}
        verify(original)
        if model_info(model,config['features']) != info: raise ValueError('Scaler changed during inference')
    (stage/'worker-result.json').write_text(json.dumps(result,allow_nan=False,sort_keys=True)+'\n')
    verify(original)


if __name__ == '__main__':
    main()
