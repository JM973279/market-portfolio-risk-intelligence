"""Offline synthetic/recorded-shape tests. Never call providers or the real model."""
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
import copy
import functools
import importlib.util
import os
import subprocess
import json
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from market_engine.us_validation.checks import (candidate_eligible, comparisons, due_session,
    independent_msi, source_changes, stages, validate_sources)
from market_engine.us_validation.engine import analyze, candidate, candidate_material, WorkerFailure
from market_engine.us_validation.sources import action_changes, collect, encode_frame, normalize_fred, normalize_yahoo, verify_snapshot
from market_engine.us_validation.store import EvidenceStore, IntegrityError, ROOT
from market_engine.us_validation.worker import model_info, historical_inputs


def calendar_environment(method):
    """Use the already pinned inference env; do not alter Portfolio dependencies."""
    @functools.wraps(method)
    def run(self):
        if importlib.util.find_spec('exchange_calendars'):
            return method(self)
        python=ROOT.parent/'market-stress-early-warning/.venv/bin/python'
        self.assertTrue(python.exists(),'Pinned inference environment is required for calendar tests')
        result=subprocess.run([str(python),'-m','unittest',self.id()],cwd=ROOT,capture_output=True,
            env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','OPENBLAS_NUM_THREADS':'1'},timeout=60)
        self.assertEqual(result.returncode,0,result.stderr.decode())
    return run


def yahoo(name='SPY', values=(10.,11.,12.), dates=('2026-10-09','2026-10-12','2026-10-13')):
    stamps=[int(pd.Timestamp(day+' 16:00',tz='America/New_York').timestamp()) for day in dates]
    return json.dumps({'chart':{'error':None,'result':[{'meta':{'symbol':'SPY' if name=='SPY' else '^VIX',
        'exchangeTimezoneName':'America/New_York'},'timestamp':stamps,
        'indicators':{'quote':[{'close':[v*2 if v else v for v in values],
            'open':list(values),'high':list(values),'low':list(values),'volume':[100]*len(values)}],
            'adjclose':[{'adjclose':list(values)}]},'events':{}}]}}).encode()


def fred(name='DBAA'):
    return f'observation_date,{name}\n2026-10-09,5\n2026-10-12,.\n2026-10-13,6\n'.encode()


def fake_get(url, *, params, **kwargs):
    if 'finance.yahoo' in url:
        name='VIX' if '^VIX' in url else 'SPY'
        body=yahoo(name)
    else:
        body=fred(params['id'])
    return SimpleNamespace(status_code=200,content=body,headers={'Content-Type':'test','Set-Cookie':'not recorded'})


def quality_fixture():
    days=pd.to_datetime(['2026-10-09','2026-10-12','2026-10-13'])
    frames={name:pd.DataFrame({'value':[10.,11.,12.]},index=days) for name in ['SPY','VIX','DBAA','DGS10']}
    for name in ['DBAA','DGS10']:frames[name].loc['2026-10-12','value']=np.nan
    manifest={'completed_at':'2026-10-14T08:30:00+00:00',
              'interval':{'start':'2026-10-09','end':'2026-10-13'},
              'sources':{name:{'adjustment':'PROVIDER_ADJ_CLOSE' if name=='SPY' else 'UNADJUSTED_LEVEL',
                         'vintage':{'kind':'LATEST_KNOWN_NOT_POINT_IN_TIME','as_of':None}} for name in frames}}
    return manifest,frames


class ImmutableSourceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='mpri-us-test-')
        self.addCleanup(self.temp.cleanup)
        self.store=EvidenceStore(Path(self.temp.name)/'evidence')

    def test_http_bodies_retained_and_normalization_reproducible(self):
        key=collect(self.store,'2026-10-09','2026-10-13',get=fake_get)
        doc,frames=verify_snapshot(self.store,key)
        self.assertTrue(doc['collection_complete'])
        self.assertEqual(self.store.read(doc['sources']['SPY']['raw_sha256']),yahoo())
        self.assertEqual(frames['SPY'].value.tolist(),[10.,11.,12.])
        self.assertNotIn('Set-Cookie',doc['sources']['SPY']['response_headers'])
        self.assertFalse(doc['public_approved'])

    def test_repeat_and_revision_have_distinct_immutable_receipts(self):
        first=collect(self.store,'2026-10-09','2026-10-13',get=fake_get)
        previous=self.store.read(first,'snapshots')
        def revised(url,**kw):
            response=fake_get(url,**kw)
            if url.endswith('/SPY'):response.content=yahoo(values=(10.,11.5,12.))
            return response
        second=collect(self.store,'2026-10-09','2026-10-13',previous=first,get=revised)
        a,old=verify_snapshot(self.store,first);b,new=verify_snapshot(self.store,second)
        self.assertNotEqual(first,second)
        self.assertEqual(self.store.read(first,'snapshots'),previous)
        self.assertEqual(b['previous'],first)
        change=source_changes(old['SPY'],new['SPY'])
        self.assertEqual(change['counts'],{'REVISED_OBSERVATION':1})

    def test_http_failure_body_kept_no_false_collection_success(self):
        response=SimpleNamespace(status_code=429,content=b'rate limited',headers={})
        key=collect(self.store,'2026-10-09','2026-10-13',get=lambda *a,**k:response)
        doc,_=verify_snapshot(self.store,key)
        self.assertFalse(doc['collection_complete'])
        self.assertEqual(self.store.read(doc['sources']['SPY']['raw_sha256']),b'rate limited')

    def test_tampering_with_raw_blob_detected(self):
        key=self.store.put(b'original')
        path=self.store.root/'blobs'/key;path.chmod(0o644);path.write_bytes(b'changed')
        with self.assertRaises(IntegrityError):self.store.read(key)
        with self.assertRaises(IntegrityError):self.store.put(b'original')

    def test_derived_csv_cannot_disagree_with_original_response(self):
        key=collect(self.store,'2026-10-09','2026-10-13',get=fake_get)
        doc,frames=verify_snapshot(self.store,key)
        altered=frames['SPY'].copy();altered.iloc[0,altered.columns.get_loc('value')]=99
        doc['sources']['SPY']['normalized_sha256']=self.store.put(encode_frame(altered))
        forged=self.store.document(doc,'snapshots')
        with self.assertRaisesRegex(ValueError,'NORMALIZATION'):verify_snapshot(self.store,forged)

    def test_path_traversal_and_public_store_rejected(self):
        with self.assertRaises(IntegrityError):self.store.read('../model')
        with self.assertRaises(ValueError):EvidenceStore(ROOT/'frontend/public/private-prices')
        outside=Path(self.temp.name)/'outside';outside.mkdir()
        (self.store.root/'blobs').symlink_to(outside,target_is_directory=True)
        with self.assertRaises(IntegrityError):self.store.put(b'escape')

    def test_fred_key_not_recorded_and_vintage_retained(self):
        seen=[]
        def get(url,params,**kw):
            if 'yahoo' in url:return fake_get(url,params=params,**kw)
            seen.append(params['api_key']);v=params['realtime_start']
            body=json.dumps({'realtime_start':v,'realtime_end':v,'count':1,
                'observations':[{'date':'2026-10-09','value':'5','realtime_start':v,'realtime_end':v}]}).encode()
            return SimpleNamespace(status_code=200,content=body,headers={})
        key=collect(self.store,'2026-10-09','2026-10-13',fred_vintage='2026-10-14',fred_key='secret-marker',get=get)
        body=self.store.read(key,'snapshots');doc,_=verify_snapshot(self.store,key)
        self.assertEqual(len(seen),2);self.assertNotIn(b'secret-marker',body)
        self.assertEqual(doc['sources']['DBAA']['vintage']['kind'],'EXPLICIT_AS_OF')


class NormalizationQualityTests(unittest.TestCase):
    def test_spy_requires_adjusted_price_never_fallback(self):
        body=json.loads(yahoo());del body['chart']['result'][0]['indicators']['adjclose']
        with self.assertRaisesRegex(ValueError,'ADJUSTED'):normalize_yahoo(json.dumps(body).encode(),'SPY')

    def test_wrong_symbol_timezone_and_array_lengths_rejected(self):
        for variant in ['symbol','timezone','length']:
            body=json.loads(yahoo());r=body['chart']['result'][0]
            if variant=='symbol':r['meta']['symbol']='QQQ'
            elif variant=='timezone':r['meta']['exchangeTimezoneName']='UTC'
            else:r['indicators']['quote'][0]['close']=[]
            with self.assertRaises(ValueError):normalize_yahoo(json.dumps(body).encode(),'SPY')

    def test_yahoo_utc_timestamp_mapped_to_exchange_local_date(self):
        body=json.loads(yahoo(values=(10.,),dates=('2026-10-09',)))
        body['chart']['result'][0]['timestamp']=[int(datetime(2026,10,10,1,tzinfo=timezone.utc).timestamp())]
        frame=normalize_yahoo(json.dumps(body).encode(),'SPY')
        self.assertEqual(str(frame.index[0].date()),'2026-10-09')

    def test_fred_null_and_duplicate_dates_preserved_not_filled(self):
        frame=normalize_fred(b'observation_date,DBAA\n2026-10-09,.\n2026-10-09,5\n','DBAA')
        self.assertTrue(pd.isna(frame.value.iloc[0]));self.assertTrue(frame.index.has_duplicates)

    def test_corporate_action_amount_revision_is_not_hidden_by_same_count(self):
        old=json.loads(yahoo());new=copy.deepcopy(old)
        old['chart']['result'][0]['events']={'dividends':{'1':{'date':1,'amount':1.2}}}
        new['chart']['result'][0]['events']={'dividends':{'1':{'date':1,'amount':1.3}}}
        result=action_changes(json.dumps(old).encode(),json.dumps(new).encode())
        self.assertEqual(len(result['dividends']['revised']),1)
        self.assertFalse(result['dividends']['added'])

    def test_fred_vintage_mismatch_and_pagination_rejected(self):
        payload={'realtime_start':'2026-10-14','realtime_end':'2026-10-14','count':2,'observations':[]}
        for v in ['2026-10-13','2026-10-14']:
            with self.assertRaises(ValueError):normalize_fred(json.dumps(payload).encode(),'DBAA',v)

    @calendar_environment
    def test_holiday_missing_is_recorded_without_imputation(self):
        m,f=quality_fixture();result=validate_sources(m,f,'2026-10-08')
        self.assertTrue(result['passed'],result)
        self.assertEqual(result['sources']['DBAA']['missing_dates'],['2026-10-12'])
        self.assertTrue(pd.isna(f['DBAA'].loc['2026-10-12','value']))

    @calendar_environment
    def test_due_day_missing_blocks_source_approval(self):
        m,f=quality_fixture();f['DBAA'].loc['2026-10-13','value']=np.nan
        result=validate_sources(m,f,'2026-10-08')
        self.assertFalse(result['passed'])
        self.assertIn('DUE_DATE_REAL_VALUE_MISSING',[i['code'] for i in result['issues']])

    @calendar_environment
    def test_nonholiday_gap_and_duplicates_block(self):
        m,f=quality_fixture();f['SPY']=f['SPY'].drop(pd.Timestamp('2026-10-13'))
        self.assertFalse(validate_sources(m,f,'2026-10-08')['passed'])
        m,f=quality_fixture();f['SPY']=pd.concat([f['SPY'],f['SPY'].iloc[:1]])
        self.assertFalse(validate_sources(m,f,'2026-10-08')['structural_passed'])

    @calendar_environment
    def test_nonfinite_negative_and_outside_interval_block(self):
        for value in [np.inf,-1.,0.]:
            m,f=quality_fixture();f['SPY'].iloc[0,0]=value
            self.assertFalse(validate_sources(m,f,'2026-10-08')['passed'])
        m,f=quality_fixture();m['interval']['start']='2026-10-12'
        self.assertFalse(validate_sources(m,f,'2026-10-08')['passed'])

    @calendar_environment
    def test_provider_extra_live_bar_is_not_approved(self):
        m,f=quality_fixture();m['interval']['end']='2026-10-14'
        f['VIX'].loc[pd.Timestamp('2026-10-14'),'value']=15.
        result=validate_sources(m,f,'2026-10-08')
        self.assertFalse(result['structural_passed'])
        self.assertIn('UNCOMPLETED_SESSION',[i['code'] for i in result['issues']])

    @calendar_environment
    def test_dst_due_policy_and_naive_clock(self):
        self.assertEqual(due_session('2026-11-05T08:59:00+00:00')[0],'2026-11-03')
        self.assertEqual(due_session('2026-11-05T09:00:00+00:00')[0],'2026-11-04')
        with self.assertRaises(ValueError):due_session('2026-11-05T09:00:00')


class InputMsiGateTests(unittest.TestCase):
    def test_change_classification_separates_late_arrival_and_revision(self):
        days=pd.date_range('2026-01-01',periods=4)
        old=pd.DataFrame({'value':[np.nan,2.,3.]},index=days[:3])
        new=pd.DataFrame({'value':[1.,2.1,np.nan,4.]},index=days)
        result=source_changes(old,new)
        self.assertEqual(result['counts'],{'FILLED_MISSING_OBSERVATION':1,'REVISED_OBSERVATION':1,'BECAME_MISSING':1,'NEW_OBSERVATION':1})

    def test_reference_coverage_and_fixed_tolerance(self):
        old=pd.DataFrame({'x':[1.,2.]},index=pd.date_range('2026-01-01',periods=2))
        self.assertTrue(comparisons(old.copy(),old,['x'])['x']['passed'])
        self.assertFalse(comparisons(old.iloc[:1],old,['x'])['x']['passed'])
        self.assertFalse(comparisons(old.assign(x=[1.,2.+1e-6]),old,['x'])['x']['passed'])
        with self.assertRaises(ValueError):comparisons(pd.concat([old,old]),old,['x'])

    def market(self):
        rng=np.random.default_rng(14);dates=pd.bdate_range('2020-01-01',periods=800)
        return pd.DataFrame({'SPY':100*np.exp(np.cumsum(rng.normal(0,.01,800))),
                             'VIX':20+rng.normal(0,2,800),'BAA_Treasury_Spread':2+rng.normal(0,.1,800)},index=dates)

    def test_msi_threshold_past_only_and_three_equal_components(self):
        raw=self.market();result=independent_msi(raw,.9);day=result.index[-1]
        stress=np.array([-raw.SPY.pct_change(21).iloc[-1],raw.VIX.iloc[-1],raw.BAA_Treasury_Spread.iloc[-1]])
        histories=np.column_stack([-raw.SPY.pct_change(21).iloc[-253:-1],raw.VIX.iloc[-253:-1],raw.BAA_Treasury_Spread.iloc[-253:-1]])
        manual=((stress-histories.mean(axis=0))/(histories.std(axis=0,ddof=1)+1e-8)).sum()/3
        self.assertAlmostEqual(result.loc[day,'MSI'],manual,places=12)
        changed=raw.copy();changed.iloc[-1,1]=1000
        revised=independent_msi(changed,.9)
        self.assertEqual(result.iloc[-1].Stress_Threshold,revised.iloc[-1].Stress_Threshold)
        pd.testing.assert_frame_equal(result.iloc[:-1],revised.iloc[:-1])

    def test_msi_incomplete_component_has_no_output_and_warmup_enforced(self):
        raw=self.market();self.assertTrue(independent_msi(raw.iloc[:300],.9).empty)
        raw.iloc[-1,2]=np.nan
        self.assertNotIn(raw.index[-1],independent_msi(raw,.9).index)

    def test_msi_success_alone_cannot_approve_candidate_or_publication(self):
        doc={'stages':stages(True,True,False,True),'baseline_reproduction_passed':True,
             'model_contract':{'passed':True},'public_approved':False}
        self.assertFalse(candidate_eligible(doc));self.assertEqual(doc['stages']['public_approval'],'NOT_ELIGIBLE')
        doc['stages']=stages(True,True,True,True)
        self.assertTrue(candidate_eligible(doc));self.assertFalse(doc['public_approved'])
        self.assertEqual(stages(True,True,True,True,True)['public_approval'],'PENDING')

    def test_blocked_candidate_never_invokes_prediction_worker(self):
        with tempfile.TemporaryDirectory(prefix='mpri-us-test-') as tmp:
            store=EvidenceStore(Path(tmp))
            key=store.document({'stages':stages(True,True,False,True)},'analyses')
            with patch('market_engine.us_validation.engine.run_worker') as worker:
                with self.assertRaisesRegex(ValueError,'blocked'):candidate(store,key)
                worker.assert_not_called()

    def test_forged_passed_flags_recomputed_from_raw_before_inference(self):
        with tempfile.TemporaryDirectory(prefix='mpri-us-test-') as tmp:
            store=EvidenceStore(Path(tmp));code={'code':'same'};frozen={'frozen':'same'}
            doc={'stages':stages(True,True,True,True),'baseline_reproduction_passed':True,
                 'model_contract':{'passed':True},'public_approved':False,'code':code,'frozen':frozen,'snapshot':'snapshot'}
            key=store.document(doc,'analyses')
            blocked=copy.deepcopy(doc);blocked['stages']=stages(True,True,False,True)
            with patch('market_engine.us_validation.engine.code_receipt',return_value=code), patch('market_engine.us_validation.engine.frozen_receipt',return_value=({},frozen)), patch('market_engine.us_validation.engine.analyze',return_value=(None,blocked,None)) as audit:
                with self.assertRaisesRegex(ValueError,'revalidation'):candidate_material(store,key,ROOT)
                self.assertFalse(audit.call_args.kwargs['persist'])
                self.assertFalse(audit.call_args.kwargs['sensitivity'])

    def test_historical_sensitivity_cannot_include_new_dates(self):
        ref=pd.DataFrame({'x':[1.,2.]},index=pd.date_range('2026-10-01',periods=2))
        new=pd.DataFrame({'x':[1.,2.1,9999.]},index=pd.date_range('2026-10-01',periods=3))
        before,after=historical_inputs(ref,new,['x'])
        self.assertEqual(after.index.max(),ref.index.max())
        self.assertEqual(len(after),2)
        self.assertNotIn(9999.,after.x.tolist())
        with self.assertRaises(ValueError):historical_inputs(ref,new.iloc[1:],['x'])

    def test_candidate_success_path_stays_private_with_synthetic_worker(self):
        with tempfile.TemporaryDirectory(prefix='mpri-us-test-') as tmp:
            store=EvidenceStore(Path(tmp))
            doc={'stages':stages(True,True,True,True),'baseline_reproduction_passed':True,
                'model_contract':{'passed':True},'public_approved':False,'snapshot':'synthetic',
                'source_validation':{'due_date':'2026-10-13'}}
            key=store.document(doc,'analyses')
            fake={'kind':'SYNTHETIC_TEST_ONLY','date':'2026-10-13','risk':.25,'public_approved':True}
            with patch('market_engine.us_validation.engine.run_worker',return_value=fake):
                output=candidate(store,key)
            saved=store.load(output,'candidates')
            self.assertFalse(saved['public_approved'])
            self.assertEqual(saved['stages']['public_approval'],'PENDING')
            self.assertEqual(saved['kind'],'SYNTHETIC_TEST_ONLY')

    def test_worker_failure_has_immutable_diagnostics_and_no_candidate(self):
        with tempfile.TemporaryDirectory(prefix='mpri-us-test-') as tmp:
            store=EvidenceStore(Path(tmp))
            with patch('market_engine.us_validation.engine._analyze',side_effect=WorkerFailure('build','baseline',b'wrong library version')):
                key,report,features=analyze(store,'synthetic')
            self.assertIsNone(features);self.assertFalse(report['public_approved'])
            self.assertEqual(report['stages']['model_inference_validation'],'BLOCKED')
            self.assertEqual(store.read(report['error']['private_log_sha256']),b'wrong library version')
            self.assertEqual(store.load(key,'analyses'),report)

    def test_scaler_order_classes_and_fingerprint(self):
        cols=[f'f{i}' for i in range(17)]
        scaler=SimpleNamespace(mean_=np.zeros(17),var_=np.ones(17),scale_=np.ones(17),n_samples_seen_=100)
        model=SimpleNamespace(feature_names_in_=cols,n_features_in_=17,classes_=np.array([0,1]),named_steps={'scaler':scaler,'classifier':object()})
        before=model_info(model,cols);self.assertEqual(before,model_info(model,cols))
        model.feature_names_in_=cols[::-1]
        with self.assertRaises(ValueError):model_info(model,cols)
        model.feature_names_in_=cols;model.classes_=np.array([1,0])
        with self.assertRaises(ValueError):model_info(model,cols)


if __name__=='__main__':unittest.main()
