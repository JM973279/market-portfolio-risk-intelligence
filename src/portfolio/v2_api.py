"""Public V2 routes use only a pinned, rights-approved registry release."""
from fastapi import APIRouter, HTTPException

from src.portfolio.v2 import (V2Request, V2CompareRequest, V2Unavailable,
                              analyze_bundle, compare_bundle, load_public_bundle)

router = APIRouter(prefix='/api/portfolio/v2', tags=['portfolio-v2'])


def _bundle(snapshot_id):
    try:
        return load_public_bundle(snapshot_id)
    except V2Unavailable as error:
        raise HTTPException(status_code=409, detail={'code':str(error), 'message':'No verified public analysis is available for this snapshot.'}) from error
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise HTTPException(status_code=503, detail={'code':'V2_RELEASE_UNAVAILABLE'}) from error


@router.post('/analyze')
def analyze_v2(request: V2Request):
    bundle = _bundle(request.snapshot_id)
    try:
        return analyze_bundle(bundle, request)
    except V2Unavailable as error:
        raise HTTPException(status_code=422, detail={'code':str(error)}) from error


@router.post('/compare')
def compare_v2(request: V2CompareRequest):
    bundle = _bundle(request.current.snapshot_id)
    try:
        return compare_bundle(bundle, request)
    except V2Unavailable as error:
        raise HTTPException(status_code=422, detail={'code':str(error)}) from error
