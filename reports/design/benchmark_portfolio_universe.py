"""Local size experiment only; repeats existing series, never registers real assets.

Run from repository root with .venv/bin/python. No network, no source data writes.
The additional columns are workload placeholders, NOT supported market securities.
"""
import json
import os
from pathlib import Path
import resource
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]


def child(count):
    import numpy as np
    import pandas as pd
    from src.portfolio import analytics, factors

    prices = pd.read_csv(ROOT / "data/portfolio/prices.csv", index_col="Date", parse_dates=True)
    original = list(prices.columns)
    expanded = pd.DataFrame(
        np.tile(prices.to_numpy(), (1, (count + len(original) - 1) // len(original))))
    expanded = expanded.iloc[:, :count]
    expanded.columns = original[:count] + [f"__WORKLOAD_ONLY_{i}" for i in range(len(original), count)]
    expanded.index = prices.index
    with tempfile.TemporaryDirectory(prefix="mpri-universe-size-") as directory:
        target = Path(directory) / "prices.csv"
        expanded.to_csv(target, index_label="Date")
        disk = target.stat().st_size
        # Release the generator before measuring the current runtime loading path.
        del expanded, prices
        analytics.SNAPSHOT_PRICES_PATH = target
        factors.SNAPSHOT_PRICES_PATH = target
        started = time.perf_counter()
        returns = analytics.load_window_returns()
        factor_data = factors.load_factor_data()
        betas = factors.load_asset_betas()
        cold_seconds = time.perf_counter() - started
        portfolio = {"AAPL": .3, "MSFT": .3, "NVDA": .2, "AMZN": .2}
        universe = pd.read_csv(ROOT / "data/portfolio/universe.csv").set_index("ticker")
        started = time.perf_counter()
        for _ in range(5):
            result = analytics.analyze_portfolio(portfolio, returns, universe)
            factors.portfolio_exposure(portfolio, betas, factor_data)
        warm_seconds = (time.perf_counter() - started) / 5
        assert result["volatility"] == 23.38
        return {
            "columns": count,
            "rows": len(returns) + 1,
            "source_rows": 2215,
            "csv_bytes": disk,
            "returns_frame_bytes": int(returns.memory_usage(deep=True).sum()),
            "factor_asset_returns_bytes": int(factor_data[0].memory_usage(deep=True).sum()),
            "cold_cache_seconds": round(cold_seconds, 4),
            "warm_analysis_plus_exposure_seconds": round(warm_seconds, 4),
            "process_peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            "real_legacy_before_volatility": result["volatility"],
        }


if __name__ == "__main__":
    if len(sys.argv) > 1:
        print(json.dumps(child(int(sys.argv[1]))))
    else:
        results = []
        for count in (28, 100, 550, 800):
            process = subprocess.run(
                [sys.executable, str(Path(__file__).resolve()), str(count)],
                cwd=ROOT,
                env={**os.environ, "PYTHONPATH": str(ROOT), "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1"},
                check=True, capture_output=True, text=True,
            )
            results.append(json.loads(process.stdout))
        print(json.dumps({
            "date": "2026-11-03",
            "scope": "Local Linux. Existing real 28 series repeated solely for size/load; no new assets or market results added. Not Render/cgroup or market coverage validation.",
            "peak_includes": "imports, CSV workload generation and runtime caches; not an API-server RSS measurement",
            "samples_per_size": 1,
            "results": results,
        }, indent=2))
