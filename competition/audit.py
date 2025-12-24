from __future__ import annotations

from collections import defaultdict, Counter
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional

from competition.interface import ActionType, GamePublicState, AuctionResult


@dataclass
class ActionAudit:
    n: int = 0
    all_pass: int = 0
    win_bid0: int = 0
    avg_win_bid: float = 0.0
    max_win_bid: int = 0


@dataclass
class BotAudit:
    games: int = 0
    win_bid0: int = 0
    gems_won: int = 0
    loans_won: int = 0
    invests_won: int = 0
    trinkets_points: int = 0

    # score components summary (computed from final_public_state)
    avg_cash: float = 0.0
    avg_gem_count: float = 0.0
    avg_loans: float = 0.0
    avg_invests: float = 0.0


def audit_game(
    final_public: GamePublicState,
    history: Tuple[AuctionResult, ...],
    seating: List[str],  # player_id -> bot name
) -> Tuple[Dict[ActionType, ActionAudit], Dict[str, BotAudit], Dict[str, int]]:
    # action-type audit
    action_stats: Dict[ActionType, ActionAudit] = defaultdict(ActionAudit)

    # per-bot audit
    bot_stats: Dict[str, BotAudit] = {name: BotAudit() for name in seating}

    # winner bid histogram per bot (quick sanity)
    win_bid_hist: Dict[str, Counter] = {name: Counter() for name in seating}

    # Score components from final_public
    for p in final_public.players:
        name = seating[p.player_id]
        st = bot_stats[name]
        st.games += 1
        st.trinkets_points += p.trinket_points
        st.avg_cash += p.cash
        st.avg_gem_count += len(p.gems_owned)
        st.avg_loans += len(p.loans)
        st.avg_invests += len(p.investments)

    # Turn-by-turn from history
    for r in history:
        k = r.action.kind
        a = action_stats[k]
        a.n += 1
        a.max_win_bid = max(a.max_win_bid, r.winning_bid)
        a.avg_win_bid += r.winning_bid

        if r.bids is not None:
            if max(r.bids) == 0:
                a.all_pass += 1
        # winner bid 0
        if r.winning_bid == 0 and r.winner_id >= 0:
            a.win_bid0 += 1
            bot_stats[seating[r.winner_id]].win_bid0 += 1

        win_bid_hist[seating[r.winner_id]][r.winning_bid] += 1

        # what was won
        if k in (ActionType.AUCTION_1, ActionType.AUCTION_2):
            bot_stats[seating[r.winner_id]].gems_won += len(r.auctioned_gems)
        elif k in (ActionType.LOAN_10, ActionType.LOAN_20):
            bot_stats[seating[r.winner_id]].loans_won += 1
        elif k in (ActionType.INVESTMENT_5, ActionType.INVESTMENT_10):
            bot_stats[seating[r.winner_id]].invests_won += 1

    # finalize averages
    for a in action_stats.values():
        if a.n:
            a.avg_win_bid /= a.n

    for name, st in bot_stats.items():
        if st.games:
            st.avg_cash /= st.games
            st.avg_gem_count /= st.games
            st.avg_loans /= st.games
            st.avg_invests /= st.games

    # simple suspiciousness metric: how often win at bid 0
    suspicious = {name: st.win_bid0 for name, st in bot_stats.items()}

    return action_stats, bot_stats, suspicious


def print_audit_summary(
    action_stats_total: Dict[ActionType, ActionAudit],
    bot_stats_total: Dict[str, BotAudit],
) -> None:
    print("\n=== Action-level sanity ===")
    for k in ActionType:
        a = action_stats_total.get(k)
        if not a or a.n == 0:
            continue
        all_pass_pct = (a.all_pass / a.n * 100) if a.n else 0.0
        win0_pct = (a.win_bid0 / a.n * 100) if a.n else 0.0
        print(
            f"{k.value:14} n={a.n:5d}  all-pass={a.all_pass:5d} ({all_pass_pct:5.1f}%)"
            f"  win@0={a.win_bid0:5d} ({win0_pct:5.1f}%)  avgWinBid={a.avg_win_bid:6.2f}  maxWinBid={a.max_win_bid}"
        )

    print("\n=== Bot-level components (averages) ===")
    for name, st in sorted(bot_stats_total.items(), key=lambda kv: kv[1].games, reverse=True):
        g = st.games or 1
        print(
            f"{name:12} games={st.games:5d}  win@0={st.win_bid0:5d}"
            f"  avgCash={st.avg_cash:7.2f}  avgGems={st.avg_gem_count:5.2f}"
            f"  avgLoans={st.avg_loans:4.2f}  avgInv={st.avg_invests:4.2f}"
            f"  trinketPts/game={st.trinkets_points/g:5.2f}"
        )
