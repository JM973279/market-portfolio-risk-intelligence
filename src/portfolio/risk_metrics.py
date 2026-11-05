"""Offline price-risk diagnostics. Does not approve data or alter V1 contracts."""
import numpy as np
import pandas as pd


def risk_metrics(returns, weights, *, confidence=.95):
    """Daily rebalanced, long-only portfolio; decimal returns and loss units."""
    if (not isinstance(returns.index, pd.DatetimeIndex) or len(returns) < 2
            or returns.index.hasnans or not returns.index.is_unique
            or not returns.index.is_monotonic_increasing or not returns.columns.is_unique
            or not weights or set(weights) - set(returns.columns)
            or not 0 < confidence < 1):
        raise ValueError('Invalid return window or confidence')
    tickers = sorted(weights)
    w = np.array([weights[t] for t in tickers], dtype=float)
    values = returns[tickers].to_numpy(dtype=float)
    if (not np.isfinite(values).all() or (values <= -1).any()
            or not np.isfinite(w).all() or (w <= 0).any()
            or not np.isclose(w.sum(), 1, rtol=0, atol=1e-10)):
        raise ValueError('Invalid returns or weights; missing values are never filled')
    portfolio = values @ w
    covariance = np.atleast_2d(np.cov(values, rowvar=False, ddof=1))
    losses = -portfolio
    quantile = float(np.quantile(losses, confidence, method='linear'))
    nav = np.r_[1., np.cumprod(1 + portfolio)]
    if not np.isfinite(nav).all() or not np.isfinite(covariance).all():
        raise ValueError('Nonfinite risk calculation')
    drawdown = 1 - nav / np.maximum.accumulate(nav)
    # Constant assets have undefined correlations; represent them explicitly.
    correlation = pd.DataFrame(values).corr().to_numpy()
    return {
        'methodology_version': 'portfolio-price-risk-v1',
        'window': {'start': str(returns.index[0].date()), 'end': str(returns.index[-1].date()), 'observations': len(returns)},
        'quality': {'missing_observations': 0, 'imputation': 'none', 'approval': 'not_granted_by_calculation'},
        'methodology': {'returns': 'daily_simple', 'rebalance': 'daily_constant_weights',
                        'annualization': 252, 'covariance_ddof': 1, 'confidence': confidence,
                        'quantile': 'linear', 'es_tail': 'loss >= raw_var_quantile_including_ties',
                        'loss_floor': 0, 'drawdown_initial_nav': 1},
        'tickers': tickers, 'covariance_daily': covariance.tolist(),
        'correlation': [[float(v) if np.isfinite(v) else None for v in row] for row in correlation],
        'mean_return_daily': float(portfolio.mean()),
        'cumulative_return': float(nav[-1] - 1),
        'volatility_annual': float(np.sqrt(w @ covariance @ w * 252)),
        'var_daily': max(0., quantile),
        'expected_shortfall_daily': max(0., float(losses[losses >= quantile].mean())),
        'max_drawdown': float(drawdown.max()),
    }


def compare_risk_metrics(returns, current, proposed, *, confidence=.95):
    before = risk_metrics(returns, current, confidence=confidence)
    after = risk_metrics(returns, proposed, confidence=confidence)
    keys = ('mean_return_daily', 'cumulative_return', 'volatility_annual',
            'var_daily', 'expected_shortfall_daily', 'max_drawdown')
    return {'current': before, 'proposed': after,
            'change': {key: after[key] - before[key] for key in keys}}
