"""Separate source/input/MSI gates, historical diagnostics and private candidates."""
from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

import numpy as np
import pandas as pd

from .checks import (ATOL, RTOL, candidate_eligible, comparisons, due_session,
                     independent_msi, source_changes, stages, validate_sources)
from .sources import action_changes, SERIES, encode_frame, read_frame, utcnow, verify_snapshot
from .store import EvidenceStore, ROOT, canonical, sha256
from .worker import RAW_SHA

ORIGINAL = ROOT.parent/'market-stress-early-warning'
CONTRACT = ROOT/'market_engine/operations/contract.json'


def digest(path: Path) -> str:
    return sha256(path.read_bytes())


def code_receipt() -> dict:
    paths = [*Path(__file__).parent.glob('*.py'), CONTRACT, ROOT/'market_engine/operations/run.py',
             ROOT/'market_engine/operations/requirements.txt']
    return {str(p.relative_to(ROOT)): digest(p) for p in sorted(paths)}


def frozen_receipt(original: Path) -> tuple[dict, dict]:
    contract = json.loads(CONTRACT.read_text())
    config = contract['markets']['us']
    wanted = {**contract['original_sources'], config['model']: config['model_sha256'],
              config['reference']: config['reference_sha256'], 'data/raw/raw_market_data.csv': RAW_SHA}
    actual = {name: digest(original/name) for name in wanted}
    if wanted != actual:
        raise ValueError('Frozen artifact/code hash mismatch')
    return config, actual


class WorkerFailure(ValueError):
    def __init__(self, mode, stage, detail):
        super().__init__('ISOLATED_V1_WORKER_FAILED')
        self.mode, self.stage, self.detail = mode, stage, detail


def run_worker(mode: str, original: Path, stage: Path, python: str, **options) -> dict:
    command = [str(Path(python).absolute()), str(Path(__file__).with_name('worker.py')),
               mode, '--original', str(original), '--stage', str(stage)]
    for key, value in options.items():
        if value is not None:
            command += ['--'+key.replace('_','-'), str(value)]
    env = {'PATH': os.environ.get('PATH','/usr/bin:/bin'), 'PYTHONDONTWRITEBYTECODE':'1',
           'OPENBLAS_NUM_THREADS':'1', 'OMP_NUM_THREADS':'1', 'MKL_NUM_THREADS':'1'}
    completed = subprocess.run(command, cwd=stage, env=env, capture_output=True, timeout=180)
    if completed.returncode:
        # Local diagnostics only; worker does not make HTTP calls or load keys.
        raise WorkerFailure(mode,stage.name,completed.stderr)
    return json.loads((stage/'worker-result.json').read_text())


def build(raw: pd.DataFrame, parent: Path, label: str, original: Path, python: str):
    stage = parent/label
    stage.mkdir()
    raw.to_csv(stage/'raw_market_data.csv',index_label='Date',float_format='%.17g')
    result = run_worker('build',original,stage,python)
    frame = lambda name: pd.read_csv(stage/name,index_col='Date',parse_dates=True)
    return stage, frame('latest_features.csv'), frame('targets.csv'), frame('cleaned_market_data.csv'), result


def all_passed(result: dict) -> bool:
    return bool(result) and all(item['passed'] for item in result.values())


def previous_changes(store, manifest, frames):
    report = {}
    if manifest.get('previous'):
        prior, old_frames = verify_snapshot(store,manifest['previous'])
        report['previous_snapshot_changes'] = {n:source_changes(old_frames[n],frames[n]) for n in SERIES if n in old_frames}
        report['previous_snapshot_field_changes'] = {
            n:{col:source_changes(old_frames[n][[col]].rename(columns={col:'value'}),
                                  frames[n][[col]].rename(columns={col:'value'}))
               for col in frames[n].select_dtypes(include='number').columns
               if col in old_frames[n] and col!='value'} for n in SERIES if n in old_frames}
        report['previous_corporate_action_changes'] = {
            n:action_changes(store.read(prior['sources'][n]['raw_sha256']),
                             store.read(manifest['sources'][n]['raw_sha256'])) for n in ('SPY','VIX') if n in old_frames}
        report['previous_vintage_metadata'] = {
            n:{'previous':prior['sources'][n]['vintage'],'current':manifest['sources'][n]['vintage']}
            for n in ('DBAA','DGS10') if n in old_frames}
        report['previous_request_intervals'] = {'previous':prior['interval'],'current':manifest['interval'],
                'note':'NEW/REMOVED rows may reflect changed request coverage, not provider revision.'}
    return report


def _analyze(store: EvidenceStore, snapshot: str, *, original: Path = ORIGINAL,
            python: str = sys.executable, sensitivity: bool = True, persist: bool = True):
    original = original.resolve()
    config, frozen = frozen_receipt(original)
    code = code_receipt()
    manifest, frames = verify_snapshot(store,snapshot)
    baseline_raw = pd.read_csv(original/'data/raw/raw_market_data.csv',index_col='Date',parse_dates=True)
    reference = pd.read_csv(original/config['reference'],index_col='Date',parse_dates=True)
    quality = validate_sources(manifest,frames,str(baseline_raw.index.max().date()))
    report = {'schema': 1, 'kind':'PRIVATE_US_VALIDATION', 'created_at':utcnow(), 'snapshot':snapshot,
              'code':code, 'frozen':frozen, 'tolerance':{'rtol':RTOL,'atol':ATOL,'changed':False},
              'source_validation':quality, 'baseline_reproduction_passed':False, 'model_contract':{'passed':False},
              'public_approved':False, 'public_reasons':['No publication approval mechanism in Phase 1'],
              'stages':stages(manifest['collection_complete'],quality['passed'],False,False),
              'evidence_blobs':{}, 'candidate_generated':False}
    report.update(previous_changes(store,manifest,frames))
    if not quality['structural_passed']:
        key = store.document(report,'analyses') if persist else None
        return key, report, None
    raw = pd.concat([frames[n].value.rename(n) for n in SERIES],axis=1).sort_index()
    raw['BAA_Treasury_Spread'] = raw.DBAA-raw.DGS10
    raw = raw[['SPY','VIX','BAA_Treasury_Spread']]
    with tempfile.TemporaryDirectory(prefix='mpri-us-validation-') as directory:
        scratch = Path(directory)
        base_stage, base_features, base_official, base_cleaned, base_meta = build(baseline_raw,scratch,'baseline',original,python)
        new_stage, features, official, cleaned, new_meta = build(raw,scratch,'snapshot',original,python)
        cols = config['features']
        baseline_features = comparisons(base_features,reference,cols)
        baseline_msi = comparisons(base_official,reference,['MSI','Stress_Threshold'])
        baseline_reproduced = all_passed(baseline_features) and all_passed(baseline_msi)
        formula_base = comparisons(independent_msi(base_cleaned,base_meta['quantile']),base_official,['MSI','Stress_Threshold'])
        formula_new = comparisons(independent_msi(cleaned,new_meta['quantile']),official,['MSI','Stress_Threshold'])
        input_diff = comparisons(features,reference,cols)
        msi_diff = comparisons(official,reference,['MSI','Stress_Threshold'])
        model_contract = run_worker('inspect',original,new_stage,python)
        due = pd.Timestamp(quality['due_date'])
        complete_input = (due in features.index and np.isfinite(features.loc[due,cols].to_numpy(dtype=float)).all())
        complete_msi = (due in official.index and np.isfinite(official.loc[due,['MSI','Stress_Threshold']].to_numpy(dtype=float)).all())
        input_pass = bool(quality['passed'] and baseline_reproduced and all_passed(input_diff) and complete_input and model_contract['passed'])
        msi_pass = bool(quality['passed'] and baseline_reproduced and all_passed(msi_diff) and all_passed(formula_base) and all_passed(formula_new) and complete_msi)
        report.update(baseline_reproduction_passed=baseline_reproduced, model_contract=model_contract,
                      baseline={'features':baseline_features,'msi':baseline_msi},
                      feature_changes=input_diff, msi={'calculated':True,'formula_baseline':formula_base,
                      'formula_new':formula_new,'historical_parity':msi_diff,'due_inputs_complete':bool(complete_msi),
                      'independent_public_approval':False,
                      'reason':'Calculation/formula parity alone does not approve revised historical distributions.'},
                      raw_value_comparison=comparisons(raw,baseline_raw,list(raw.columns)),
                      raw_changes={n:source_changes(baseline_raw[[n]].rename(columns={n:'value'}),raw[[n]].rename(columns={n:'value'})) for n in raw},
                      rolling_effect={'feature_windows':[1,5,20,60,252],'msi_equity_return_window':21,
                                      'msi_distribution_window':252,'msi_min_observations':126,
                                      'threshold':'shift(1).expanding(min_periods=252).quantile(pinned_config)',
                                      'drawdown':'full historical cummax; effects are not bounded to 252 rows',
                                      'feature_impact_intervals':input_diff},
                      stages=stages(True,quality['passed'],input_pass,msi_pass), versions=new_meta['versions'],
                      observed_interval={'start':str(raw.SPY.dropna().index.min().date()),'end':str(raw.SPY.dropna().index.max().date()),
                                         'reference_start':str(reference.index.min().date()),'reference_end':str(reference.index.max().date())},
                      historical_fill_provenance={'policy':'Unchanged original cleaner ffill(limit=5) on SPY sessions; not new imputation',
                            'baseline_missing':{n:int(baseline_raw.loc[baseline_raw.SPY.notna(),n].isna().sum()) for n in ['VIX','BAA_Treasury_Spread']},
                            'snapshot_missing':{n:int(raw.loc[raw.SPY.notna(),n].isna().sum()) for n in ['VIX','BAA_Treasury_Spread']}})
        if not quality['passed']:
            report['stages']['input_change_validation'] = 'BLOCKED'
            report['stages']['msi_validation'] = 'BLOCKED'
        report['historical_fill_provenance']['snapshot_filled_dates'] = {
            n:[str(d.date()) for d in cleaned.index.intersection(raw.index[raw.SPY.notna() & raw[n].isna()])]
            for n in ['VIX','BAA_Treasury_Spread']}
        spy = frames['SPY']
        ratio = spy.adj_close/spy.close
        report['price_adjustment'] = {'selection':'provider Adj Close, without cent rounding/repair',
                    'min_adjustment_ratio':float(ratio.min()),'max_adjustment_ratio':float(ratio.max()),
                    'dividend_events':int(spy.dividends_count.sum()),'split_events':int(spy.splits_count.sum()),
                    'backend_revision_cause':'Not proven; the original response/action/request vintage was not retained.'}
        if sensitivity and baseline_reproduced:
            diagnostics = {'all_sources':run_worker('sensitivity',original,new_stage,python,input=new_stage/'latest_features.csv')}
            # Separate actual provider changes without changing any frozen data.
            for label,replace_cols in [('spy_only',['VIX','BAA_Treasury_Spread']),('credit_only',['SPY','VIX'])]:
                variant = raw.copy()
                common = variant.index.intersection(baseline_raw.index)
                variant.loc[common,replace_cols] = baseline_raw.loc[common,replace_cols]
                stage, f, o, cl, meta = build(variant,scratch,label,original,python)
                diagnostics[label] = run_worker('sensitivity',original,stage,python,input=stage/'latest_features.csv')
                diagnostics[label]['msi_changes'] = comparisons(o,reference,['MSI','Stress_Threshold'])
            report['historical_sensitivity'] = diagnostics
        # Private counterfactual, not an approved splice: quantify rolling effects
        # after the reference ends, without any post-reference model predictions.
        anchored = raw.copy()
        common = anchored.index.intersection(baseline_raw.index)
        anchored.loc[common,raw.columns] = baseline_raw.loc[common,raw.columns]
        _,anchor_features,anchor_msi,_,_ = build(anchored,scratch,'window-impact',original,python)
        actual_dates = raw.dropna().index
        later = actual_dates[(actual_dates > reference.index.max()) & (actual_dates <= due)]
        f_dates = later.intersection(anchor_features.index).intersection(features.index)
        m_dates = later.intersection(anchor_msi.index).intersection(official.index)
        report['post_reference_window_impact'] = {
            'kind':'COUNTERFACTUAL_LEGACY_HISTORY_VS_FULL_VINTAGE_NOT_APPROVED_INPUT',
            'from':str(later.min().date()) if len(later) else None,
            'to':str(later.max().date()) if len(later) else None,
            'features':comparisons(features.loc[f_dates],anchor_features.loc[f_dates],cols) if len(f_dates) else {},
            'msi':comparisons(official.loc[m_dates],anchor_msi.loc[m_dates],['MSI','Stress_Threshold']) if len(m_dates) else {},
            'new_model_predictions_generated':False}
        # Immutable private artifacts, never frontend/public or an API registry.
        if persist:
            for name, path in {'features':new_stage/'latest_features.csv','msi':new_stage/'targets.csv',
                               'cleaned':new_stage/'cleaned_market_data.csv'}.items():
                report['evidence_blobs'][name] = store.put(path.read_bytes())
        final_frozen = frozen_receipt(original)[1]
        if final_frozen != frozen or code_receipt() != code:
            raise ValueError('Inputs/code mutated during validation')
        key = store.document(report,'analyses') if persist else None
        return key,report,features


def analyze(store: EvidenceStore, snapshot: str, *, original: Path = ORIGINAL,
            python: str = sys.executable, sensitivity: bool = True, persist: bool = True):
    try:
        return _analyze(store,snapshot,original=original,python=python,sensitivity=sensitivity,persist=persist)
    except Exception as error:
        if not persist:
            raise
        # Failure evidence is also immutable; no silent drop of failed calculations.
        report = {'schema':1,'kind':'PRIVATE_US_VALIDATION_FAILURE','created_at':utcnow(),
                  'snapshot':snapshot,'public_approved':False,'candidate_generated':False,
                  'baseline_reproduction_passed':False,'model_contract':{'passed':False},
                  'stages':{name:'NOT_RUN' for name in ('collection','source_validation','input_change_validation','msi_validation')},
                  'error':{'type':type(error).__name__,'code':'VALIDATION_FAILED_CLOSED'}}
        report['stages'].update(model_inference_validation='BLOCKED',public_approval='NOT_ELIGIBLE')
        if isinstance(error,WorkerFailure):
            report['error'].update(code='ISOLATED_V1_WORKER_FAILED',mode=error.mode,stage=error.stage,
                                   private_log_sha256=store.put(error.detail))
        key = store.document(report,'analyses')
        return key,report,None


def candidate_material(store: EvidenceStore, analysis: str, original: Path):
    saved = store.load(analysis,'analyses')
    if saved.get('code') != code_receipt() or saved.get('frozen') != frozen_receipt(original)[1]:
        raise ValueError('Candidate evidence/code binding changed')
    if not candidate_eligible(saved):
        raise ValueError('Candidate blocked: source/input/MSI gates have not all passed')
    # Recompute from raw bodies. Forging PASSED flags or replacing a derived CSV
    # cannot bypass source, reference, MSI or artifact verification.
    _,report,features = analyze(store,saved['snapshot'],original=original,python=sys.executable,
                               sensitivity=False,persist=False)
    if not candidate_eligible(report): raise ValueError('Candidate revalidation failed')
    if report['source_validation']['due_date'] != due_session(utcnow())[0]:
        raise ValueError('Candidate evidence is stale')
    return report,features


def candidate(store: EvidenceStore, analysis: str, *, original: Path = ORIGINAL, python: str = sys.executable) -> str:
    original = original.resolve()
    saved = store.load(analysis,'analyses')
    if not candidate_eligible(saved):
        raise ValueError('Candidate blocked: source/input/MSI gates have not all passed')
    # The worker repeats all checks and rebuilds the candidate from original responses.
    with tempfile.TemporaryDirectory(prefix='mpri-us-candidate-') as directory:
        result = run_worker('candidate',original,Path(directory),python,store=store.root,analysis=analysis,
                            date=saved['source_validation']['due_date'])
    result.update(analysis=analysis,snapshot=saved['snapshot'],stages=stages(True,True,True,True,True),
                  public_approved=False,public_status='PENDING',created_at=utcnow())
    return store.document(result,'candidates')
