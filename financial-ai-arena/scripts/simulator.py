"""Paper-trading simulation state and scoring."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Portfolio:
    cash: float = 100_000.0
    positions: dict[str, float] = field(default_factory=dict)  # symbol -> shares

    def total_value(self, prices: dict[str, float]) -> float:
        v = self.cash
        for sym, qty in self.positions.items():
            p = prices.get(sym, 0.0)
            v += qty * p
        return v


def drift_prices(prices: dict[str, float], rng: random.Random) -> dict[str, float]:
    out: dict[str, float] = {}
    for sym, p in prices.items():
        shock = rng.gauss(0, 0.012)
        out[sym] = max(0.01, p * (1.0 + shock))
    return out


def apply_decision(
    pf: Portfolio,
    decision: dict[str, Any],
    prices: dict[str, float],
    *,
    fee_rate: float = 0.0003,
    universe: list[str],
) -> None:
    action = decision.get("action", "hold")
    target = decision.get("target") or ""
    if target and target not in prices:
        if universe:
            target = universe[0]
    if not target or target not in prices:
        return

    price = prices[target]
    if price <= 0:
        return

    size_pct = float(decision.get("size_pct", 0) or 0) / 100.0
    size_pct = max(0.0, min(1.0, size_pct))

    if action == "buy":
        budget = pf.cash * size_pct
        if budget <= 0:
            return
        fee = budget * fee_rate
        spend = budget - fee
        shares = spend / price
        if shares <= 0:
            return
        pf.cash -= budget
        pf.positions[target] = pf.positions.get(target, 0.0) + shares

    elif action == "sell":
        held = pf.positions.get(target, 0.0)
        if held <= 0:
            return
        qty = held * size_pct if size_pct > 0 else held
        qty = max(0.0, min(held, qty))
        gross = qty * price
        fee = gross * fee_rate
        pf.cash += gross - fee
        pf.positions[target] = held - qty
        if pf.positions[target] <= 1e-12:
            del pf.positions[target]


def initial_prices(symbols: list[str], rng: random.Random) -> dict[str, float]:
    return {s: round(rng.uniform(50, 200), 4) for s in symbols}


def rank_players(totals: dict[str, float]) -> list[tuple[str, float]]:
    return sorted(totals.items(), key=lambda x: x[1], reverse=True)


def weights_from_rank(rank_ids: list[str]) -> dict[str, float]:
    n = len(rank_ids)
    if n <= 0:
        return {}
    raw = [float(n - i) for i in range(n)]
    s = sum(raw) or 1.0
    return {rid: w / s for rid, w in zip(rank_ids, raw)}
