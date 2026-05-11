from __future__ import annotations

from dataclasses import dataclass
from statistics import mean
from typing import Dict, List, Sequence

from src.bots.registry import bot_entries_from_specs, resolve_bot_specs, resolve_value_charts
from src.competition.contracts import ValueChart
from src.competition.engine import EngineConfig, PocketRocketsEngine
from src.competition.simulator import SimulationResult, run_pocketrocks_simulation


@dataclass(frozen=True)
class WorkflowConfig:
    bot_sources: Sequence[str]
    include_private: bool
    n_games: int
    seed: int
    players_per_game: int
    chart_keys: Sequence[str]
    products_enabled: bool = True


def load_entries(bot_sources: Sequence[str], include_private: bool):
    specs = resolve_bot_specs(bot_sources=bot_sources, include_private=include_private)
    return bot_entries_from_specs(specs)


def run_simulation(config: WorkflowConfig) -> SimulationResult:
    entries = load_entries(config.bot_sources, config.include_private)
    charts = resolve_value_charts(config.chart_keys)
    return run_pocketrocks_simulation(
        entries,
        n_games=config.n_games,
        players_per_game=config.players_per_game,
        seed=config.seed,
        value_charts=charts if len(charts) > 1 else None,
        value_chart=charts[0] if len(charts) == 1 else None,
        products_enabled=config.products_enabled,
    )


def render_report(result: SimulationResult) -> str:
    lines = ["name,games,wins,win_rate,avg_score,avg_rank"]
    rows = sorted(result.per_bot.items(), key=lambda kv: kv[1].wins, reverse=True)
    for name, st in rows:
        if st.games == 0:
            continue
        lines.append(
            f"{name},{st.games},{st.wins},{st.wins/st.games:.3f},{st.total_score/st.games:.2f},{mean(st.ranks):.2f}"
        )
    return "\n".join(lines)


def benchmark_with_seat_splits(config: WorkflowConfig) -> Dict[str, object]:
    entries = load_entries(config.bot_sources, config.include_private)
    charts = resolve_value_charts(config.chart_keys)
    per_bot_seat_scores: Dict[str, Dict[int, List[int]]] = {e.name: {} for e in entries}
    seed_base = config.seed
    for game_idx in range(config.n_games):
        game_seed = seed_base + game_idx
        chart: ValueChart = charts[game_idx % len(charts)]
        selected = entries[: config.players_per_game]
        bots = [e.factory() for e in selected]
        names = [e.name for e in selected]
        out = PocketRocketsEngine(
            bots=bots,
            config=EngineConfig(seed=game_seed, products_enabled=config.products_enabled),
            value_chart=chart,
            bot_names=names,
        ).play()
        for pid, name, score in out["final_scores"]:
            per_bot_seat_scores.setdefault(name, {}).setdefault(int(pid), []).append(score)
    seat_means = {
        name: {seat: mean(scores) for seat, scores in seat_map.items()}
        for name, seat_map in per_bot_seat_scores.items()
        if seat_map
    }
    sim = run_simulation(config)
    return {"summary": sim, "seat_means": seat_means}
