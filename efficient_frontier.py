"""Efficient frontier analysis for the multi-ticker OHLCV dataset.

This script loads `temp.csv`, derives close-to-close log returns for
Samsung Electronics (005930.KS), Apple (AAPL), and NVIDIA (NVDA), and
generates an efficient frontier plot saved as `efficient_frontier.svg`.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Dict, List, Tuple

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


TRADING_DAYS = 252
DATA_FILE = Path(__file__).with_name("temp.csv")
OUTPUT_FILE = Path(__file__).with_name("efficient_frontier.svg")


def load_close_prices(path: Path) -> pd.DataFrame:
    """Return a wide DataFrame of close prices indexed by date."""

    df = pd.read_csv(path, header=[0, 1, 2])
    date_series = pd.to_datetime(df[("Price", "Ticker", "Date")])

    closes = df["Close"].copy()
    closes.columns = closes.columns.droplevel(-1)
    closes = closes.apply(pd.to_numeric, errors="coerce")
    closes.index = date_series
    closes = closes.sort_index()
    closes = closes.dropna(how="any")
    return closes


def compute_log_returns(closes: pd.DataFrame) -> pd.DataFrame:
    returns = np.log(closes / closes.shift(1)).dropna(how="any")
    return returns


def annualised_statistics(returns: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray]:
    mean_daily = returns.mean().to_numpy()
    cov_daily = returns.cov().to_numpy()
    mu = mean_daily * TRADING_DAYS
    cov = cov_daily * TRADING_DAYS
    return mu, cov


def solve_frontier(mu: np.ndarray, cov: np.ndarray, n_points: int = 60) -> Dict[str, np.ndarray]:
    inv_cov = np.linalg.inv(cov)
    ones = np.ones_like(mu)

    a = ones @ inv_cov @ ones
    b = ones @ inv_cov @ mu
    c = mu @ inv_cov @ mu
    d = a * c - b**2

    target_returns = np.linspace(mu.min(), mu.max(), n_points)
    weights = []
    vols = []
    for r_target in target_returns:
        lambda1 = (c - b * r_target) / d
        lambda2 = (a * r_target - b) / d
        w = inv_cov @ (lambda1 * ones + lambda2 * mu)
        weights.append(w)
        variance = w @ cov @ w
        vols.append(math.sqrt(max(variance, 0.0)))

    weights_arr = np.vstack(weights)
    vols_arr = np.asarray(vols)
    return {
        "returns": target_returns,
        "vols": vols_arr,
        "weights": weights_arr,
        "a": a,
        "b": b,
        "c": c,
    }


def global_min_variance_weights(inv_cov: np.ndarray, ones: np.ndarray) -> np.ndarray:
    numer = inv_cov @ ones
    denom = ones @ numer
    return numer / denom


def max_sharpe(frontier: Dict[str, np.ndarray], risk_free: float = 0.0) -> Tuple[float, float, np.ndarray]:
    excess_returns = frontier["returns"] - risk_free
    sharpe = np.divide(
        excess_returns,
        frontier["vols"],
        out=np.zeros_like(excess_returns),
        where=frontier["vols"] > 0,
    )
    idx = int(np.nanargmax(sharpe))
    return frontier["vols"][idx], frontier["returns"][idx], frontier["weights"][idx]


def plot_frontier(
    frontier: Dict[str, np.ndarray],
    asset_returns: np.ndarray,
    asset_vols: np.ndarray,
    tickers: List[str],
    gmv_point: Tuple[float, float],
    max_sharpe_point: Tuple[float, float],
    output: Path,
) -> None:
    plt.figure(figsize=(9, 6))
    plt.plot(frontier["vols"], frontier["returns"], color="#1f77b4", linewidth=2, label="Efficient frontier")
    plt.scatter(asset_vols, asset_returns, color="#d62728", s=60, label="Assets")
    for ticker, x, y in zip(tickers, asset_vols, asset_returns):
        plt.annotate(ticker, (x, y), textcoords="offset points", xytext=(8, -8))

    plt.scatter(*gmv_point, color="#ff7f0e", s=80, label="Global min variance")
    plt.annotate("GMV", gmv_point, textcoords="offset points", xytext=(10, -15))

    plt.scatter(*max_sharpe_point, color="#2ca02c", s=80, label="Max Sharpe")
    plt.annotate("Max Sharpe", max_sharpe_point, textcoords="offset points", xytext=(10, 10))

    plt.xlabel("Annualised volatility")
    plt.ylabel("Annualised return")
    plt.title("Efficient frontier for 005930.KS, AAPL, and NVDA")
    plt.grid(True, which="both", linestyle="--", linewidth=0.5, alpha=0.6)
    plt.legend()
    plt.tight_layout()
    plt.savefig(output, format="svg")
    plt.close()


def main() -> None:
    closes = load_close_prices(DATA_FILE)
    returns = compute_log_returns(closes)
    mu, cov = annualised_statistics(returns)

    frontier = solve_frontier(mu, cov)
    inv_cov = np.linalg.inv(cov)
    ones = np.ones_like(mu)

    gmv_weights = global_min_variance_weights(inv_cov, ones)
    gmv_return = float(gmv_weights @ mu)
    gmv_vol = float(math.sqrt(max(gmv_weights @ cov @ gmv_weights, 0.0)))

    ms_vol, ms_ret, ms_weights = max_sharpe(frontier)

    asset_vols = np.sqrt(np.diag(cov))
    tickers = closes.columns.tolist()

    plot_frontier(
        frontier,
        asset_returns=mu,
        asset_vols=asset_vols,
        tickers=tickers,
        gmv_point=(gmv_vol, gmv_return),
        max_sharpe_point=(ms_vol, ms_ret),
        output=OUTPUT_FILE,
    )

    print("Annualised mean returns:")
    for ticker, ret in zip(tickers, mu):
        print(f"  {ticker}: {ret * 100:.2f}%")

    print("Annualised volatilities:")
    for ticker, vol in zip(tickers, asset_vols):
        print(f"  {ticker}: {vol * 100:.2f}%")

    print("Global minimum variance portfolio:")
    for ticker, weight in zip(tickers, gmv_weights):
        print(f"  {ticker}: {weight * 100:.2f}%")
    print(f"  Return: {gmv_return * 100:.2f}%  Volatility: {gmv_vol * 100:.2f}%")

    print("Maximum Sharpe portfolio:")
    for ticker, weight in zip(tickers, ms_weights):
        print(f"  {ticker}: {weight * 100:.2f}%")
    print(f"  Return: {ms_ret * 100:.2f}%  Volatility: {ms_vol * 100:.2f}%")


if __name__ == "__main__":
    main()

