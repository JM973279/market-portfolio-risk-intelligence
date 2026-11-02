from functools import lru_cache

import numpy as np
import pandas as pd

from src.portfolio.data import WINDOW_DAYS
from src.portfolio.snapshot import SNAPSHOT_FACTORS_PATH, SNAPSHOT_PRICES_PATH

# 팩터별 일간 변화의 단위: market = SPY 수익률(소수), rate = DGS10 변화(bp),
# volatility = VIX 변화(pt). 베타는 그 단위 1당 자산 수익률(소수)입니다.
FACTORS = ("market", "rate", "volatility")

# |t|가 이 값보다 작은 베타는 0과 구분할 수 없는 값으로 표시합니다.
SIGNIFICANCE_T = 2


def build_factor_moves(prices, factors, window_days=WINDOW_DAYS):
    """
    추정 기간의 자산 일간 수익률과 세 팩터의 일간 변화를 같은 날짜로 만듭니다.

    기간은 analytics의 변동성·상관 계산과 같은 최근 window_days 거래일입니다.
    DGS10 결측일(채권시장 휴장)은 이어 쓰지 않으므로 그날과 다음 날의
    금리 변화가 비고, 금리 회귀에서만 빠집니다.
    """
    days = prices.index[-(window_days + 1):]
    asset_returns = prices.loc[days].pct_change().iloc[1:]
    factor_moves = pd.DataFrame({
        "market": prices.loc[days, "SPY"].pct_change(),
        "rate": factors.loc[days, "DGS10"].diff() * 100,
        "volatility": factors.loc[days, "VIX"].diff(),
    }).iloc[1:]
    return asset_returns, factor_moves


def estimate_betas(asset_returns, factor_moves):
    """
    자산마다 팩터 하나씩 따로 단순회귀(절편 포함)해 베타·R²·t값·표본 수를 구합니다.

    다른 팩터를 통제하지 않은 민감도이므로 팩터 간 상관에 따른 중복이 있습니다.
    """
    rows = []
    for ticker in asset_returns.columns:
        row = {"ticker": ticker}
        for factor in FACTORS:
            pair = pd.concat(
                [asset_returns[ticker], factor_moves[factor]], axis=1
            ).dropna()
            y, x = pair.iloc[:, 0], pair.iloc[:, 1]
            n = len(pair)

            beta = y.cov(x) / x.var()
            r2 = y.corr(x) ** 2
            se = np.sqrt((1 - r2) / (n - 2)) * y.std() / x.std()

            row[factor] = beta
            row[f"{factor}_r2"] = r2
            row[f"{factor}_t"] = beta / se if se > 0 else np.inf
            row[f"{factor}_n"] = n
        rows.append(row)

    return pd.DataFrame(rows).set_index("ticker")


@lru_cache(maxsize=1)
def load_factor_data(window_days=WINDOW_DAYS):
    """스냅샷으로 추정 기간의 자산 수익률과 팩터 변화를 한 번 만들어 재사용합니다."""
    prices = pd.read_csv(SNAPSHOT_PRICES_PATH, index_col="Date", parse_dates=True)
    factors = pd.read_csv(SNAPSHOT_FACTORS_PATH, index_col="Date", parse_dates=True)
    return build_factor_moves(prices, factors, window_days)


@lru_cache(maxsize=1)
def load_asset_betas(window_days=WINDOW_DAYS):
    """스냅샷으로 지원 자산 전체의 베타를 한 번 추정해 재사용합니다."""
    return estimate_betas(*load_factor_data(window_days))


def _significance(row):
    """
    베타별 t값과 |t| >= SIGNIFICANCE_T 여부를 돌려줍니다.

    완전 적합(SPY의 Market 베타처럼 표준오차 0)이면 t값은 None, 유의함은 True입니다.
    """
    t = {f: float(row[f"{f}_t"]) for f in FACTORS}
    return (
        {f: round(v, 2) if np.isfinite(v) else None for f, v in t.items()},
        {f: bool(abs(v) >= SIGNIFICANCE_T) for f, v in t.items()},
    )


def portfolio_exposure(weights, betas, factor_data=None):
    """
    자산 베타를 비중(소수)으로 가중합한 포트폴리오 베타와 자산별 베타를 돌려줍니다.

    자산별 목록은 analytics의 allocation과 같은 순서(비중 큰 순, 티커 순)입니다.
    factor_data(자산 수익률, 팩터 변화)를 주면 포트폴리오 일간 수익률을 직접
    회귀해 포트폴리오 베타의 t값과 유의함도 붙입니다. 같은 표본을 쓰므로
    회귀 베타는 가중합 베타와 같습니다.
    """
    tickers = sorted(weights, key=lambda t: (-weights[t], t))
    exposure = {
        factor: float(sum(weights[t] * betas.at[t, factor] for t in tickers))
        for factor in FACTORS
    }

    by_asset = []
    for t in tickers:
        t_stat, significant = _significance(betas.loc[t])
        by_asset.append({
            "ticker": t,
            **{f: float(betas.at[t, f]) for f in FACTORS},
            "t_stat": t_stat,
            "significant": significant,
        })
    exposure["by_asset"] = by_asset

    if factor_data is not None:
        asset_returns, factor_moves = factor_data
        series = asset_returns[tickers] @ np.array([weights[t] for t in tickers])
        row = estimate_betas(series.to_frame("portfolio"), factor_moves).loc["portfolio"]
        exposure["t_stat"], exposure["significant"] = _significance(row)

    return exposure
