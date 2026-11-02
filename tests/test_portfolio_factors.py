import numpy as np
import pandas as pd
import pytest

from src.portfolio.factors import (
    build_factor_moves,
    estimate_betas,
    portfolio_exposure,
)


@pytest.fixture
def market_data():
    rng = np.random.default_rng(1)
    n = 301
    days = pd.bdate_range("2024-01-01", periods=n)

    spy_ret = rng.normal(0, 0.01, n)
    rate_bp = rng.normal(0, 5, n)
    vix_pt = rng.normal(0, 1, n)
    noise = rng.normal(0, 0.001, n)

    # 알려진 베타로 만든 자산: LEV는 시장 1.5배, BOND는 금리 1bp당 -0.1%
    lev_ret = 1.5 * spy_ret + noise
    bond_ret = -0.001 * rate_bp + noise

    prices = pd.DataFrame({
        "SPY": 100 * np.cumprod(1 + spy_ret),
        "LEV": 100 * np.cumprod(1 + lev_ret),
        "BOND": 100 * np.cumprod(1 + bond_ret),
    }, index=days)
    factors = pd.DataFrame({
        "DGS10": 4 + np.cumsum(rate_bp) / 100,
        "VIX": 20 + np.cumsum(vix_pt),
    }, index=days)
    return prices, factors


def test_betas_recover_known_sensitivities(market_data):
    prices, factors = market_data
    asset_returns, factor_moves = build_factor_moves(prices, factors, window_days=300)

    betas = estimate_betas(asset_returns, factor_moves)

    assert betas.at["SPY", "market"] == pytest.approx(1.0)
    assert betas.at["LEV", "market"] == pytest.approx(1.5, abs=0.02)
    assert betas.at["BOND", "rate"] == pytest.approx(-0.001, abs=0.00005)
    assert betas.at["LEV", "market_r2"] > 0.95
    assert betas.at["BOND", "market_r2"] < 0.05


def test_missing_rate_day_drops_only_from_rate_regression(market_data):
    prices, factors = market_data
    factors.iloc[150, factors.columns.get_loc("DGS10")] = np.nan
    asset_returns, factor_moves = build_factor_moves(prices, factors, window_days=300)

    betas = estimate_betas(asset_returns, factor_moves)

    # 결측일 당일과 다음 날의 금리 변화가 함께 빠짐
    assert betas.at["BOND", "rate_n"] == 298
    assert betas.at["BOND", "market_n"] == 300


def test_portfolio_exposure_is_weighted_sum_in_allocation_order():
    betas = pd.DataFrame(
        {
            "market": [1.2, -0.1], "rate": [-0.0002, -0.0014], "volatility": [-0.004, 0.0002],
            "market_t": [20.0, 1.5], "rate_t": [-1.3, -64.0], "volatility_t": [-17.0, 0.3],
        },
        index=pd.Index(["AAPL", "TLT"], name="ticker"),
    )

    exposure = portfolio_exposure({"TLT": 0.4, "AAPL": 0.6}, betas)

    assert exposure["market"] == pytest.approx(0.6 * 1.2 + 0.4 * -0.1)
    assert exposure["rate"] == pytest.approx(0.6 * -0.0002 + 0.4 * -0.0014)
    assert [a["ticker"] for a in exposure["by_asset"]] == ["AAPL", "TLT"]
    assert exposure["by_asset"][1]["market"] == -0.1
    assert exposure["by_asset"][1]["significant"] == {
        "market": False, "rate": True, "volatility": False
    }
    assert exposure["by_asset"][0]["t_stat"]["market"] == 20.0
    # 수익률 데이터 없이는 포트폴리오 t값을 만들지 않음
    assert "t_stat" not in exposure


def test_portfolio_t_stat_comes_from_regressing_portfolio_returns(market_data):
    prices, factors = market_data
    factor_data = build_factor_moves(prices, factors, window_days=300)
    betas = estimate_betas(*factor_data)

    exposure = portfolio_exposure({"LEV": 0.5, "BOND": 0.5}, betas, factor_data)

    portfolio = (factor_data[0][["LEV", "BOND"]] @ [0.5, 0.5]).to_frame("p")
    direct = estimate_betas(portfolio, factor_data[1]).loc["p"]
    assert exposure["market"] == pytest.approx(direct["market"])
    assert exposure["rate"] == pytest.approx(direct["rate"])
    assert exposure["t_stat"]["market"] == pytest.approx(round(direct["market_t"], 2))
    assert exposure["significant"]["market"] and exposure["significant"]["rate"]


def test_perfect_fit_has_no_t_value_but_counts_as_significant(market_data):
    prices, factors = market_data
    betas = estimate_betas(*build_factor_moves(prices, factors, window_days=300))

    spy = portfolio_exposure({"SPY": 1.0}, betas)["by_asset"][0]

    assert spy["t_stat"]["market"] is None
    assert spy["significant"]["market"] is True
