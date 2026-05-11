from __future__ import annotations

import csv
import itertools
import random
import sys
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from src.bots.registry import (
    baseline_public_specs,
    bot_entries_from_specs,
    load_private_bot_specs,
    make_value_trader_specs,
    resolve_bot_specs,
    resolve_value_charts,
)
from src.competition.contracts import ValueChart
from src.competition.engine import EngineConfig, PocketRocketsEngine
from src.competition.simulator import BotEntry, BotStats, SimulationResult, run_pocketrocks_simulation


@dataclass(frozen=True)
class WorkflowConfig:
    bot_sources: Sequence[str]
    include_private: bool
    n_games: int
    seed: int
    players_per_game: int
    chart_keys: Sequence[str]
    products_enabled: bool = True


@dataclass(frozen=True)
class ScenarioAxes:
    products_enabled_values: Sequence[bool]
    players_per_game_values: Sequence[int]
    chart_keys: Sequence[str]


@dataclass(frozen=True)
class StageBenchmarkConfig:
    n_games_per_scenario: int = 80
    seed: int = 101
    value_trader_risks: Sequence[float] = (0.5, 0.7, 0.9, 1.0, 1.1, 1.2)
    final_top_value_traders: int = 3
    final_max_lineups: int = 24


@dataclass(frozen=True)
class ReportPaths:
    output_dir: str = "local/benchmark_outputs"
    markdown_file: str = "benchmark_report.md"


class _ProgressBar:
    def __init__(self, total: int, *, width: int = 28):
        self.total = max(1, int(total))
        self.width = width
        self.current = 0

    def advance(self, *, stage: str) -> None:
        self.current += 1
        ratio = min(1.0, self.current / self.total)
        filled = int(self.width * ratio)
        bar = ("#" * filled) + ("-" * (self.width - filled))
        msg = f"\r[{bar}] {self.current}/{self.total} ({ratio * 100:5.1f}%) stage={stage}"
        print(msg, end="", flush=True)
        if self.current >= self.total:
            print("", file=sys.stdout, flush=True)


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


def _metrics_row(name: str, st: BotStats) -> Optional[Dict[str, object]]:
    if st.games == 0:
        return None
    return {
        "bot": name,
        "games": st.games,
        "wins": st.wins,
        "win_rate": st.wins / st.games,
        "top2_rate": st.top2 / st.games,
        "avg_score": st.total_score / st.games,
        "avg_rank": mean(st.ranks),
    }


def _result_rows(result: SimulationResult) -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = []
    for name, st in sorted(result.per_bot.items(), key=lambda kv: kv[1].wins, reverse=True):
        row = _metrics_row(name, st)
        if row is not None:
            rows.append(row)
    return rows


def render_report(result: SimulationResult) -> str:
    lines = ["name,games,wins,win_rate,avg_score,avg_rank,top2_rate"]
    for row in _result_rows(result):
        lines.append(
            f"{row['bot']},{row['games']},{row['wins']},{row['win_rate']:.3f},{row['avg_score']:.2f},{row['avg_rank']:.2f},{row['top2_rate']:.3f}"
        )
    return "\n".join(lines)


def benchmark_with_seat_splits(config: WorkflowConfig) -> Dict[str, object]:
    entries = load_entries(config.bot_sources, config.include_private)
    charts = resolve_value_charts(config.chart_keys)
    per_bot_seat_scores: Dict[str, Dict[int, List[int]]] = {e.name: {} for e in entries}
    rng = random.Random(config.seed)

    for game_idx in range(config.n_games):
        chart: ValueChart = charts[game_idx % len(charts)]
        selected = list(entries) if len(entries) == config.players_per_game else rng.sample(list(entries), k=config.players_per_game)
        rng.shuffle(selected)
        bots = [e.factory() for e in selected]
        names = [e.name for e in selected]
        game_seed = rng.randrange(1_000_000_000)
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


def _aggregate_rows(rows: Iterable[Dict[str, object]]) -> List[Dict[str, object]]:
    grouped: Dict[str, Dict[str, float]] = {}
    for row in rows:
        name = str(row["bot"])
        g = grouped.setdefault(name, {"games": 0.0, "wins": 0.0, "top2": 0.0, "score": 0.0, "rank": 0.0})
        games = float(row["games"])
        g["games"] += games
        g["wins"] += float(row["wins"])
        g["top2"] += float(row["top2_rate"]) * games
        g["score"] += float(row["avg_score"]) * games
        g["rank"] += float(row["avg_rank"]) * games
    out: List[Dict[str, object]] = []
    for name, g in grouped.items():
        games = int(g["games"])
        if games == 0:
            continue
        out.append(
            {
                "bot": name,
                "games": games,
                "wins": int(g["wins"]),
                "win_rate": g["wins"] / games,
                "top2_rate": g["top2"] / games,
                "avg_score": g["score"] / games,
                "avg_rank": g["rank"] / games,
            }
        )
    out.sort(key=lambda r: (r["win_rate"], r["avg_score"]), reverse=True)
    return out


def _write_csv(path: Path, rows: List[Dict[str, object]], fieldnames: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(fieldnames))
        writer.writeheader()
        writer.writerows(rows)


def _scenario_combos(names: Sequence[str], k: int, max_lineups: int, seed: int) -> List[Tuple[str, ...]]:
    all_combos = [tuple(c) for c in itertools.combinations(sorted(set(names)), k)]
    if len(all_combos) <= max_lineups:
        return all_combos
    rng = random.Random(seed)
    return sorted(rng.sample(all_combos, k=max_lineups))


def _count_total_scenarios(
    *,
    private_count: int,
    baseline_count: int,
    risk_count: int,
    final_top_value_traders: int,
    players_values: Sequence[int],
    products_values: Sequence[bool],
    final_max_lineups: int,
) -> int:
    product_factor = len(products_values)
    stage1 = 0
    for players in players_values:
        needed = players - 1
        if 0 < needed <= baseline_count:
            stage1 += private_count * len(list(itertools.combinations(range(baseline_count), needed))) * product_factor

    stage2 = private_count * risk_count * len(players_values) * product_factor

    stage3 = 0
    final_pool_size = private_count + max(1, min(final_top_value_traders, risk_count))
    for players in players_values:
        if players > final_pool_size:
            continue
        combo_count = len(list(itertools.combinations(range(final_pool_size), players)))
        stage3 += min(combo_count, final_max_lineups) * product_factor
    return stage1 + stage2 + stage3


def _run_scenario(
    *,
    scenario_id: str,
    stage: str,
    lineup: Sequence[BotEntry],
    n_games: int,
    seed: int,
    players_per_game: int,
    chart_keys: Sequence[str],
    products_enabled: bool,
) -> Dict[str, object]:
    charts = resolve_value_charts(chart_keys)
    result = run_pocketrocks_simulation(
        lineup,
        n_games=n_games,
        players_per_game=players_per_game,
        seed=seed,
        value_charts=charts if len(charts) > 1 else None,
        value_chart=charts[0] if len(charts) == 1 else None,
        products_enabled=products_enabled,
    )
    rows = _result_rows(result)
    for row in rows:
        row["scenario_id"] = scenario_id
        row["stage"] = stage
        row["players_per_game"] = players_per_game
        row["products_enabled"] = products_enabled
        row["charts"] = "|".join(chart_keys)
        row["lineup"] = "|".join(e.name for e in lineup)

    seat_rows: List[Dict[str, object]] = []
    for game in result.game_logs:
        for seat, name, score in game["final_scores"]:
            seat_rows.append(
                {
                    "scenario_id": scenario_id,
                    "stage": stage,
                    "bot": name,
                    "seat": int(seat),
                    "score": int(score),
                }
            )
    return {"result": result, "rows": rows, "seat_rows": seat_rows}


def run_staged_benchmark(
    *,
    axes: Optional[ScenarioAxes] = None,
    config: Optional[StageBenchmarkConfig] = None,
    report_paths: Optional[ReportPaths] = None,
) -> Dict[str, object]:
    axes = axes or ScenarioAxes(products_enabled_values=(True, False), players_per_game_values=(3, 4, 5), chart_keys=("A", "B", "C", "D", "E"))
    config = config or StageBenchmarkConfig()
    report_paths = report_paths or ReportPaths()

    private_specs = load_private_bot_specs()
    baseline_specs = baseline_public_specs()
    vt_specs = make_value_trader_specs(config.value_trader_risks)

    if not private_specs:
        raise ValueError("No private bots found in local/private_bots/registry.py")

    scenario_rows: List[Dict[str, object]] = []
    seat_rows: List[Dict[str, object]] = []
    stage_rank_rows: List[Dict[str, object]] = []
    total_scenarios = _count_total_scenarios(
        private_count=len(private_specs),
        baseline_count=len(baseline_specs),
        risk_count=len(vt_specs),
        final_top_value_traders=config.final_top_value_traders,
        players_values=axes.players_per_game_values,
        products_values=axes.products_enabled_values,
        final_max_lineups=config.final_max_lineups,
    )
    progress = _ProgressBar(total_scenarios)

    scenario_counter = 0

    # Stage 1: each private bot against sample baseline combos
    stage1_rows: List[Dict[str, object]] = []
    for private in private_specs:
        for players in axes.players_per_game_values:
            needed = players - 1
            if needed <= 0 or needed > len(baseline_specs):
                continue
            combos = list(itertools.combinations(baseline_specs, needed))
            for products_enabled in axes.products_enabled_values:
                for combo in combos:
                    scenario_counter += 1
                    lineup_specs = [private, *combo]
                    lineup_entries = bot_entries_from_specs(lineup_specs)
                    out = _run_scenario(
                        scenario_id=f"S{scenario_counter:04d}",
                        stage="stage1",
                        lineup=lineup_entries,
                        n_games=config.n_games_per_scenario,
                        seed=config.seed + scenario_counter,
                        players_per_game=players,
                        chart_keys=axes.chart_keys,
                        products_enabled=products_enabled,
                    )
                    scenario_rows.extend(out["rows"])
                    seat_rows.extend(out["seat_rows"])
                    stage1_rows.extend(out["rows"])
                    progress.advance(stage="stage1")

    stage1_rank = _aggregate_rows(stage1_rows)
    for r in stage1_rank:
        stage_rank_rows.append({"stage": "stage1", **r})

    # Stage 2: each private bot against value trader sweep
    stage2_rows: List[Dict[str, object]] = []
    stage2_vt_rows: List[Dict[str, object]] = []
    for private in private_specs:
        for vt in vt_specs:
            for players in axes.players_per_game_values:
                fillers = [vt] * (players - 1)
                lineup_specs = [private, *fillers]
                for products_enabled in axes.products_enabled_values:
                    scenario_counter += 1
                    out = _run_scenario(
                        scenario_id=f"S{scenario_counter:04d}",
                        stage="stage2",
                        lineup=bot_entries_from_specs(lineup_specs),
                        n_games=config.n_games_per_scenario,
                        seed=config.seed + scenario_counter,
                        players_per_game=players,
                        chart_keys=axes.chart_keys,
                        products_enabled=products_enabled,
                    )
                    scenario_rows.extend(out["rows"])
                    seat_rows.extend(out["seat_rows"])
                    stage2_rows.extend(out["rows"])
                    stage2_vt_rows.extend([r for r in out["rows"] if str(r["bot"]).startswith("ValueTrader(")])
                    progress.advance(stage="stage2")

    stage2_rank = _aggregate_rows(stage2_rows)
    for r in stage2_rank:
        stage_rank_rows.append({"stage": "stage2", **r})

    vt_rank = _aggregate_rows(stage2_vt_rows)
    top_vt_names = [str(r["bot"]) for r in vt_rank[: max(1, config.final_top_value_traders)]]
    top_vt_specs = [s for s in vt_specs if s.name in top_vt_names]

    # Stage 3: combinatorial final pool
    stage3_rows: List[Dict[str, object]] = []
    final_pool = [*private_specs, *top_vt_specs]
    final_names = [s.name for s in final_pool]
    for players in axes.players_per_game_values:
        if players > len(final_pool):
            continue
        combos = _scenario_combos(final_names, players, config.final_max_lineups, config.seed + players)
        for products_enabled in axes.products_enabled_values:
            for combo_names in combos:
                lineup_specs = [next(s for s in final_pool if s.name == name) for name in combo_names]
                scenario_counter += 1
                out = _run_scenario(
                    scenario_id=f"S{scenario_counter:04d}",
                    stage="stage3",
                    lineup=bot_entries_from_specs(lineup_specs),
                    n_games=config.n_games_per_scenario,
                    seed=config.seed + scenario_counter,
                    players_per_game=players,
                    chart_keys=axes.chart_keys,
                    products_enabled=products_enabled,
                )
                scenario_rows.extend(out["rows"])
                seat_rows.extend(out["seat_rows"])
                stage3_rows.extend(out["rows"])
                progress.advance(stage="stage3")

    stage3_rank = _aggregate_rows(stage3_rows)
    for r in stage3_rank:
        stage_rank_rows.append({"stage": "stage3", **r})

    out_dir = Path(report_paths.output_dir)
    _write_csv(
        out_dir / "scenario_results.csv",
        scenario_rows,
        ["scenario_id", "stage", "bot", "games", "wins", "win_rate", "top2_rate", "avg_score", "avg_rank", "players_per_game", "products_enabled", "charts", "lineup"],
    )
    _write_csv(out_dir / "seat_scores.csv", seat_rows, ["scenario_id", "stage", "bot", "seat", "score"])
    _write_csv(
        out_dir / "stage_rankings.csv",
        stage_rank_rows,
        ["stage", "bot", "games", "wins", "win_rate", "top2_rate", "avg_score", "avg_rank"],
    )

    final_pool_rows = [r for r in stage_rank_rows if r["stage"] == "stage3"]
    _write_csv(
        out_dir / "final_pool_results.csv",
        final_pool_rows,
        ["stage", "bot", "games", "wins", "win_rate", "top2_rate", "avg_score", "avg_rank"],
    )

    md_lines = [
        "# Benchmark Report",
        "",
        "## Summary",
        f"- Scenarios executed: {scenario_counter}",
        f"- Stage 1 rows: {len(stage1_rows)}",
        f"- Stage 2 rows: {len(stage2_rows)}",
        f"- Stage 3 rows: {len(stage3_rows)}",
        f"- Top ValueTrader variants selected for Stage 3: {', '.join(top_vt_names) if top_vt_names else 'None'}",
        "",
        "## Stage 1 Top Bots",
    ]
    for r in stage1_rank[:5]:
        md_lines.append(f"- {r['bot']}: win_rate={r['win_rate']:.3f}, avg_score={r['avg_score']:.2f}, avg_rank={r['avg_rank']:.2f}")

    md_lines.append("")
    md_lines.append("## Stage 2 Top Bots")
    for r in stage2_rank[:5]:
        md_lines.append(f"- {r['bot']}: win_rate={r['win_rate']:.3f}, avg_score={r['avg_score']:.2f}, avg_rank={r['avg_rank']:.2f}")

    md_lines.append("")
    md_lines.append("## Stage 3 Top Bots")
    for r in stage3_rank[:10]:
        md_lines.append(f"- {r['bot']}: win_rate={r['win_rate']:.3f}, avg_score={r['avg_score']:.2f}, avg_rank={r['avg_rank']:.2f}")

    md_lines.append("")
    md_lines.append("## Stability Notes")
    md_lines.append("- Results aggregate products on/off, player counts 3/4/5, and mixed value chart cycles.")
    md_lines.append("- Scenario and seat-level CSV outputs are included for deeper analysis and confidence checks.")

    md_path = out_dir / report_paths.markdown_file
    md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    return {
        "output_dir": str(out_dir),
        "markdown_path": str(md_path),
        "scenario_count": scenario_counter,
        "top_value_traders": top_vt_names,
        "stage_rankings": {
            "stage1": stage1_rank,
            "stage2": stage2_rank,
            "stage3": stage3_rank,
        },
    }
