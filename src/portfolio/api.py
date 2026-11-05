import json

from fastapi import APIRouter, Query
from typing import Literal
from src.portfolio.execution import bounded_endpoint

from src.portfolio.readiness import require_snapshot

from src.portfolio.analytics import (
    analyze_portfolio,
    load_snapshot_meta,
    load_window_returns,
)
from src.portfolio.factors import (
    load_asset_betas,
    load_factor_data,
    portfolio_exposure,
)
from src.portfolio.scenarios import SCENARIOS_PATH, describe_methodology
from src.portfolio.schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    CompareRequest,
    CompareResponse,
)
from src.portfolio.stress import compute_stress
from src.portfolio.universe import describe_sector_methodology, load_universe
from src.portfolio.whatif import compare_analyses

# 메인 앱에서 app.include_router(router) 한 줄로 연결합니다.
router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


def get_universe():
    """지원 자산 목록"""
    assets = load_universe().reset_index()
    return {
        "assets": assets.to_dict(orient="records"),
        "sector_methodology": describe_sector_methodology(),
    }


def get_scenarios():
    """Stress 시나리오 정의·충격 크기·근거 구간"""
    return json.loads(SCENARIOS_PATH.read_text())


def analyze(request: AnalyzeRequest):
    """포트폴리오 Hidden Risk 분석. What-if는 변경 전후로 두 번 호출합니다."""
    weights = {h.ticker: h.weight / 100 for h in request.holdings}
    result = analyze_portfolio(weights, load_window_returns(), load_universe())

    exposure = portfolio_exposure(weights, load_asset_betas(), load_factor_data())
    result["factor_exposure"] = exposure
    result["stress"] = compute_stress(
        weights, request.value_usd, exposure["by_asset"],
        get_scenarios()["scenarios"],
    )
    # 시나리오 손익은 그 팩터의 포트폴리오 베타가 0과 구분될 때만 방향을 말할 수 있습니다.
    significant = exposure.get("significant") or {}
    for s in result["stress"]:
        s["significant"] = significant.get(s["factor"])

    meta = load_snapshot_meta()
    return {
        "as_of": meta["as_of"],
        "window": {
            "start": meta["window_start"],
            "end": meta["window_end"],
            "days": meta["window_days"],
        },
        "value_usd": request.value_usd,
        **result,
        "methodology": describe_methodology(),
        "sector_methodology": describe_sector_methodology(),
    }


def compare(request: CompareRequest):
    """What-if: 변경 전후를 같은 엔진으로 분석하고 주요 지표 차이를 돌려줍니다."""
    current = analyze(request.current)
    proposed = current if request.current == request.proposed else analyze(request.proposed)
    return {
        "current": current,
        "proposed": proposed,
        "comparison": compare_analyses(current, proposed),
    }


def catalog():
    """Versioned discovery/capability metadata; V1 analysis remains unchanged."""
    from src.portfolio.catalog import get_catalog
    return get_catalog()


def discovery(q: str = Query('', max_length=100), market: Literal['US', 'KR'] | None = None,
              kind: Literal['stock', 'etf'] | None = None,
              status: Literal['full', 'partial', 'unsupported'] | None = None,
              offset: int = Query(0, ge=0), limit: int = Query(30, ge=1, le=100)):
    from src.portfolio.catalog import search_discovery
    return search_discovery(q, market, kind, status, offset, limit)


# Keep synchronous cores callable by demo/offline users; HTTP always enters the
# single bounded executor once, including the unchanged snapshot SHA check.
for path, core, methods, response_model in [
    ('/universe', get_universe, ['GET'], None),
    ('/scenarios', get_scenarios, ['GET'], None),
    ('/analyze', analyze, ['POST'], AnalyzeResponse),
    ('/compare', compare, ['POST'], CompareResponse),
    ('/v2/catalog', catalog, ['GET'], None),
    ('/v2/discovery', discovery, ['GET'], None),
]:
    router.add_api_route(path, bounded_endpoint(core, check=require_snapshot),
                         methods=methods, response_model=response_model)
