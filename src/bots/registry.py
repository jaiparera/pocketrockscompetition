from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, List, Sequence

from src.bots.samples.always_pass_bot import AlwaysPassBot
from src.bots.samples.random_bid_bot import RandomBidBot
from src.bots.samples.value_trader_bot import ValueTraderBot
from src.competition.contracts import PocketRocketsBot, ValueChart
from src.competition.simulator import BotEntry

BotFactory = Callable[[], PocketRocketsBot]


@dataclass(frozen=True)
class BotSpec:
    name: str
    factory: BotFactory


VALUE_CHARTS = {
    "A": ValueChart(mapping=[0, 4, 8, 12, 16, 20]),
    "B": ValueChart(mapping=[20, 16, 12, 8, 4, 0]),
    "C": ValueChart(mapping=[0, 2, 5, 9, 14, 20]),
    "D": ValueChart(mapping=[20, 18, 15, 11, 6, 0]),
    "E": ValueChart(mapping=[0, 4, 10, 18, 6, 0]),
}

SAMPLE_BOTS: List[BotSpec] = [
    BotSpec("AlwaysPass", lambda: AlwaysPassBot()),
    BotSpec("RandomBidA", lambda: RandomBidBot(seed=7)),
    BotSpec("RandomBidB", lambda: RandomBidBot(seed=19)),
    BotSpec("ValueTrader", lambda: ValueTraderBot(risk=0.9)),
]


def make_value_trader_specs(risks: Sequence[float]) -> List[BotSpec]:
    return [
        BotSpec(name=f"ValueTrader(r={risk:.2f})", factory=(lambda r=risk: ValueTraderBot(risk=float(r))))
        for risk in risks
    ]


def baseline_public_specs() -> List[BotSpec]:
    return [s for s in SAMPLE_BOTS if not s.name.startswith("ValueTrader")]


def _load_specs_from_path(module_name: str, file_path: Path, symbol: str) -> List[BotSpec]:
    if not file_path.exists():
        return []
    spec = importlib.util.spec_from_file_location(module_name, str(file_path))
    if spec is None or spec.loader is None:
        return []
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    loaded = getattr(module, symbol, [])
    return [BotSpec(name=s.name, factory=s.factory) for s in loaded]


def load_private_bot_specs() -> List[BotSpec]:
    return _load_specs_from_path("local_private_registry", Path("local/private_bots/registry.py"), "PRIVATE_BOTS")


def resolve_bot_specs(bot_sources: Sequence[str], include_private: bool = False) -> List[BotSpec]:
    out: List[BotSpec] = []
    if "public" in bot_sources:
        out.extend(SAMPLE_BOTS)
    if "private" in bot_sources and include_private:
        out.extend(load_private_bot_specs())
    return out


def bot_entries_from_specs(specs: Iterable[BotSpec]) -> List[BotEntry]:
    return [BotEntry(s.name, s.factory) for s in specs]


def resolve_value_charts(chart_keys: Sequence[str]) -> List[ValueChart]:
    return [VALUE_CHARTS[k] for k in chart_keys]
