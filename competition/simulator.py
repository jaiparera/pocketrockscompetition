from __future__ import annotations

from itertools import combinations
import math
import random
import statistics
from dataclasses import dataclass
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple
from competition.interface import *
from competition.game import *
from collections import defaultdict
from competition.audit import audit_game, print_audit_summary, ActionAudit, BotAudit

# Assumes your interface + engine are importable / in-scope:
# from pocketrocks_interface import (
#   PocketRocketsBot, ValueChart, TrinketObjective, Card, Suit
# )
# from pocketrocks_engine import PocketRocketsEngine, EngineConfig


# -----------------------------
# Tournament wiring
# -----------------------------

BotFactory = Callable[[], "PocketRocketsBot"]


@dataclass(frozen=True)
class BotEntry:
    """
    name: stable label used for reporting (can differ from bot.bot_name).
    factory: returns a *fresh* bot instance each game.
    """
    name: str
    factory: BotFactory


@dataclass
class BotStats:
    games: int = 0
    wins: int = 0
    top2: int = 0
    total_score: float = 0.0
    scores: List[int] = None
    ranks: List[int] = None

    def __post_init__(self):
        if self.scores is None:
            self.scores = []
        if self.ranks is None:
            self.ranks = []


@dataclass(frozen=True)
class SimulationResult:
    per_bot: Dict[str, BotStats]
    game_logs: List[dict]  # each includes seating + final_scores + winner


# -----------------------------
# Defaults (optional helpers)
# -----------------------------

def default_value_chart() -> "ValueChart":
    """
    Example mapping: mapping[k] = per-gem value when k cards of that suit
    were dealt into info hands at start.
    Adjust to match your manual / chart.
    """
    # index: 0..6 (with 30-card deck, 3*5 = 15 info max; clamp handled by engine)
    return ValueChart(mapping=[0, 4, 8, 12, 16, 20, 24])



def _cards_for_suits(suits: Sequence["Suit"], *, prefix: str) -> Tuple["Card", ...]:
    """
    Create Cards for a suit-multiset. IDs just need to be unique within the trinket.
    """
    return tuple(Card(id=f"{prefix}{i}", suit=s) for i, s in enumerate(suits))


def generate_all_possible_trinkets() -> List["TrinketObjective"]:
    """
    Generates the full menu of possible trinkets per your rules:

    - 2-gem trinkets (pendants), worth 5 points:
        * either two-of-a-kind (AA)
        * or two different suits (AB)
    - 3-gem trinkets, worth 10 points: all different (ABC)
    - 4-gem trinkets, worth 15 points: all different (ABCD)

    Note: With 5 suits total, counts are:
      2-kind: 5
      2-diff: C(5,2)=10
      3-diff: C(5,3)=10
      4-diff: C(5,4)=5
      total: 30
    """
    out: List[TrinketObjective] = []
    suits = list(Suit)

    # 2-gem: two of same suit
    for s in suits:
        req = _cards_for_suits([s, s], prefix=f"pendant_{s.name}_")
        out.append(
            TrinketObjective(
                id=f"P2_SAME_{s.name}",
                points=5,
                required_cards=req,
                display_text=f"Pendant (5): {s.name} + {s.name}",
            )
        )

    # 2-gem: two different suits
    for a, b in combinations(suits, 2):
        req = _cards_for_suits([a, b], prefix=f"pendant_{a.name}_{b.name}_")
        out.append(
            TrinketObjective(
                id=f"P2_DIFF_{a.name}_{b.name}",
                points=5,
                required_cards=req,
                display_text=f"Pendant (5): {a.name} + {b.name}",
            )
        )

    # 3-gem: all different
    for a, b, c in combinations(suits, 3):
        req = _cards_for_suits([a, b, c], prefix=f"triple_{a.name}_{b.name}_{c.name}_")
        out.append(
            TrinketObjective(
                id=f"T3_{a.name}_{b.name}_{c.name}",
                points=10,
                required_cards=req,
                display_text=f"Trinket (10): {a.name} + {b.name} + {c.name}",
            )
        )

    # 4-gem: all different
    for a, b, c, d in combinations(suits, 4):
        req = _cards_for_suits([a, b, c, d], prefix=f"quad_{a.name}_{b.name}_{c.name}_{d.name}_")
        out.append(
            TrinketObjective(
                id=f"T4_{a.name}_{b.name}_{c.name}_{d.name}",
                points=15,
                required_cards=req,
                display_text=f"Trinket (15): {a.name} + {b.name} + {c.name} + {d.name}",
            )
        )

    return out


def default_trinkets(*, seed: Optional[int] = None, rng: Optional[random.Random] = None) -> List["TrinketObjective"]:
    """
    Returns 4 randomly sampled trinkets from the full possible set.

    Provide either:
      - seed=... (convenience), or
      - rng=Random(...) (preferred if you want the engine RNG to control everything)

    If both are provided, rng wins.
    """
    if rng is None:
        rng = random.Random(seed)

    all_trinkets = generate_all_possible_trinkets()
    # sample 4 distinct trinkets
    return rng.sample(all_trinkets, k=4)


# -----------------------------
# Simulation
# -----------------------------

def run_pocketrocks_simulation(
    bots: Sequence[BotEntry],
    n_games: int,
    *,
    players_per_game: Optional[int] = None,
    seed: int = 0,
    engine_config_factory: Optional[Callable[[int], "EngineConfig"]] = None,
    value_chart: Optional["ValueChart"] = None,
    trinkets: Optional[Sequence["TrinketObjective"]] = None,
    verbose_every: int = 0,
) -> SimulationResult:
    """
    Runs n_games. Randomizes seating each game.
    If players_per_game is None, uses len(bots) (must be 3–5).
    If you provide more than 5 bots and want round-robin, set players_per_game to 3–5;
    each game will sample that many bots uniformly at random.

    engine_config_factory(game_seed) -> EngineConfig lets you vary per-game seeds cleanly.
    """
    if value_chart is None:
        value_chart = default_value_chart()
    if trinkets is None:
        trinkets = default_trinkets()

    rng = random.Random(seed)

    if players_per_game is None:
        players_per_game = len(bots)
    if not (3 <= players_per_game <= 5):
        raise ValueError("PocketRockets supports 3–5 players per game.")
    if len(bots) < players_per_game:
        raise ValueError("Not enough bots for players_per_game.")

    # Stats init
    per_bot: Dict[str, BotStats] = {b.name: BotStats() for b in bots}
    game_logs: List[dict] = []

    for g in range(n_games):
        game_seed = rng.randrange(1_000_000_000)

        # pick participants
        if len(bots) == players_per_game:
            participants = list(bots)
        else:
            participants = rng.sample(list(bots), k=players_per_game)

        # randomize seating (player_id order is the seating)
        rng.shuffle(participants)

        # fresh bot instances for this game
        bot_instances = [be.factory() for be in participants]
        bot_names = [be.name for be in participants]

        # engine config
        if engine_config_factory is None:
            cfg = EngineConfig(seed=game_seed)
        else:
            cfg = engine_config_factory(game_seed)

        engine = PocketRocketsEngine(
            bots=bot_instances,
            config=cfg,
            value_chart=value_chart,
            trinkets=trinkets,
            bot_names=bot_names,
        )

        out = engine.play()
        
        action_stats, bot_stats, suspicious = audit_game(
            final_public=out["final_public_state"],
            history=out["history"],
            seating=[be.name for be in participants],
        )

        # accumulate totals
        if g == 0:
            action_stats_total = defaultdict(ActionAudit)
            bot_stats_total = {name: BotAudit() for name in per_bot.keys()}

        for k, a in action_stats.items():
            t = action_stats_total[k]
            t.n += a.n
            t.all_pass += a.all_pass
            t.win_bid0 += a.win_bid0
            t.avg_win_bid += a.avg_win_bid * a.n
            t.max_win_bid = max(t.max_win_bid, a.max_win_bid)

        for name, st in bot_stats.items():
            T = bot_stats_total[name]
            T.games += st.games
            T.win_bid0 += st.win_bid0
            T.gems_won += st.gems_won
            T.loans_won += st.loans_won
            T.invests_won += st.invests_won
            T.trinkets_points += st.trinkets_points
            T.avg_cash += st.avg_cash * st.games
            T.avg_gem_count += st.avg_gem_count * st.games
            T.avg_loans += st.avg_loans * st.games
            T.avg_invests += st.avg_invests * st.games

        # after the loop, finalize weighted averages:
        for k, t in action_stats_total.items():
            if t.n:
                t.avg_win_bid = t.avg_win_bid / t.n

        for name, T in bot_stats_total.items():
            if T.games:
                T.avg_cash /= T.games
                T.avg_gem_count /= T.games
                T.avg_loans /= T.games
                T.avg_invests /= T.games
                
        # Debugger
        # print_audit_summary(action_stats_total, bot_stats_total)

        # out["final_scores"] is [(player_id, name, score)] sorted desc
        final_scores: List[Tuple[int, str, int]] = list(out["final_scores"])
        winner_id = out["winner_id"]

        # Build rank by player_id
        # rank 1 = best
        rank_by_pid: Dict[int, int] = {}
        score_by_pid: Dict[int, int] = {}
        for rank, (pid, name, score) in enumerate(final_scores, start=1):
            rank_by_pid[pid] = rank
            score_by_pid[pid] = int(score)

        # Update stats for each participating bot
        for pid, be in enumerate(participants):
            name = be.name
            st = per_bot[name]
            st.games += 1
            st.scores.append(score_by_pid[pid])
            st.ranks.append(rank_by_pid[pid])
            st.total_score += score_by_pid[pid]
            if pid == winner_id:
                st.wins += 1
            if rank_by_pid[pid] <= 2:
                st.top2 += 1

        game_logs.append(
            {
                "game_index": g,
                "seed": game_seed,
                "seating": [be.name for be in participants],  # player_id order
                "final_scores": final_scores,
                "winner": next(name for (pid, name, _) in final_scores if pid == winner_id),
            }
        )

        if verbose_every and (g + 1) % verbose_every == 0:
            print(f"[game {g+1}/{n_games}] winner={game_logs[-1]['winner']} seating={game_logs[-1]['seating']}")

    return SimulationResult(per_bot=per_bot, game_logs=game_logs)


# -----------------------------
# Reporting
# -----------------------------

def print_pocketrocks_report(result: SimulationResult) -> None:
    rows = []
    for name, st in result.per_bot.items():
        if st.games == 0:
            continue
        avg_score = st.total_score / st.games
        med_score = statistics.median(st.scores)
        sd_score = statistics.pstdev(st.scores) if st.games > 1 else 0.0
        avg_rank = sum(st.ranks) / st.games
        win_rate = st.wins / st.games
        top2_rate = st.top2 / st.games
        rows.append(
            {
                "name": name,
                "games": st.games,
                "wins": st.wins,
                "win%": win_rate,
                "top2%": top2_rate,
                "avg_rank": avg_rank,
                "avg_score": avg_score,
                "med_score": med_score,
                "sd_score": sd_score,
                "min": min(st.scores),
                "max": max(st.scores),
            }
        )

    # Sort by win%, then avg_score
    rows.sort(key=lambda r: (r["win%"], r["avg_score"]), reverse=True)

    # Pretty print (no external deps)
    def fmt_pct(x: float) -> str:
        return f"{x*100:5.1f}%"

    headers = ["Bot", "Games", "Wins", "Win%", "Top2%", "AvgRank", "AvgScore", "Med", "SD", "Min", "Max"]
    col_w = [max(len(h), 8) for h in headers]

    table = []
    table.append(headers)
    for r in rows:
        table.append(
            [
                r["name"],
                str(r["games"]),
                str(r["wins"]),
                fmt_pct(r["win%"]),
                fmt_pct(r["top2%"]),
                f"{r['avg_rank']:.2f}",
                f"{r['avg_score']:.2f}",
                str(r["med_score"]),
                f"{r['sd_score']:.2f}",
                str(r["min"]),
                str(r["max"]),
            ]
        )

    # compute widths
    widths = [0] * len(headers)
    for row in table:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))

    # print
    def print_row(row: List[str]) -> None:
        print(" | ".join(cell.ljust(widths[i]) for i, cell in enumerate(row)))

    print_row(table[0])
    print("-+-".join("-" * w for w in widths))
    for row in table[1:]:
        print_row(row)

    # Overall sanity
    total_games = len(result.game_logs)
    print(f"\nTotal games: {total_games}")
    if total_games:
        winners = [g["winner"] for g in result.game_logs]
        most_common = max(set(winners), key=winners.count)
        print(f"Most common winner: {most_common} ({winners.count(most_common)}/{total_games})")