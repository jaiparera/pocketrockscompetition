from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from .contracts import PocketRocketsBot, ValueChart
from .engine import EngineConfig, PocketRocketsEngine

BotFactory = Callable[[], PocketRocketsBot]


@dataclass(frozen=True)
class BotEntry:
    name: str
    factory: BotFactory


@dataclass
class BotStats:
    games: int = 0
    wins: int = 0
    top2: int = 0
    total_score: float = 0.0
    scores: List[int] = field(default_factory=list)
    ranks: List[int] = field(default_factory=list)


@dataclass(frozen=True)
class SimulationResult:
    per_bot: Dict[str, BotStats]
    game_logs: List[dict]


def default_value_chart() -> ValueChart:
    return ValueChart(mapping=[0, 4, 8, 12, 16, 20])


def run_pocketrocks_simulation(
    bots: Sequence[BotEntry],
    n_games: int,
    *,
    players_per_game: Optional[int] = None,
    seed: int = 0,
    engine_config_factory: Optional[Callable[[int], EngineConfig]] = None,
    value_chart: Optional[ValueChart] = None,
    value_charts: Optional[Sequence[ValueChart]] = None,
    products_enabled: bool = True,
) -> SimulationResult:
    if value_chart is not None and value_charts is not None:
        raise ValueError("Provide either value_chart or value_charts, not both.")
    rng = random.Random(seed)
    if players_per_game is None:
        players_per_game = len(bots)
    if not (3 <= players_per_game <= 5):
        raise ValueError("PocketRockets supports 3-5 players per game.")
    if len(bots) < players_per_game:
        raise ValueError("Not enough bots for players_per_game.")
    if value_charts is not None:
        charts = list(value_charts)
        if n_games % len(charts) != 0:
            raise ValueError("n_games must be divisible by len(value_charts).")
        game_charts = charts * (n_games // len(charts))
        rng.shuffle(game_charts)
    else:
        game_charts = [value_chart or default_value_chart()] * n_games
    per_bot: Dict[str, BotStats] = {b.name: BotStats() for b in bots}
    logs: List[dict] = []
    for g in range(n_games):
        participants = list(bots) if len(bots) == players_per_game else rng.sample(list(bots), k=players_per_game)
        rng.shuffle(participants)
        instances = [b.factory() for b in participants]
        names = [b.name for b in participants]
        game_seed = rng.randrange(1_000_000_000)
        cfg = engine_config_factory(game_seed) if engine_config_factory else EngineConfig(seed=game_seed, products_enabled=products_enabled)
        if engine_config_factory is None:
            cfg = EngineConfig(seed=game_seed, products_enabled=products_enabled)
        out = PocketRocketsEngine(instances, cfg, value_chart=game_charts[g], bot_names=names).play()
        final_scores: List[Tuple[int, str, int]] = list(out["final_scores"])
        rank_by_pid = {pid: idx + 1 for idx, (pid, _, _) in enumerate(final_scores)}
        for pid, name, score in final_scores:
            st = per_bot[name]
            st.games += 1
            st.total_score += score
            st.scores.append(score)
            rank = rank_by_pid[pid]
            st.ranks.append(rank)
            if rank == 1:
                st.wins += 1
            if rank <= 2:
                st.top2 += 1
        logs.append({"participants": names, "final_scores": final_scores, "winner_id": out["winner_id"]})
    return SimulationResult(per_bot=per_bot, game_logs=logs)


def print_pocketrocks_report(res: SimulationResult) -> None:
    print("name,games,wins,win_rate,avg_score,avg_rank")
    for name, st in sorted(res.per_bot.items(), key=lambda kv: kv[1].wins, reverse=True):
        if st.games == 0:
            continue
        print(f"{name},{st.games},{st.wins},{st.wins / st.games:.3f},{st.total_score / st.games:.2f},{sum(st.ranks) / st.games:.2f}")

