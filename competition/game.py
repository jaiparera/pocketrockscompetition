from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple, Mapping
from competition.interface import *

# -----------------------------
# Engine configuration
# -----------------------------

@dataclass(frozen=True)
class EngineConfig:
    seed: int = 0
    info_cards_per_player: Mapping[int, int] = None
    starting_cash_by_players: Mapping[int, int] = None

    # Gem deck composition: 30 cards total -> 5 suits * 6 each by default
    gems_per_suit: int = 6

    # Action deck composition (approx 2/3 auctions, 1/6 loans, 1/6 investments)
    # You can tune these counts for your competition.
    action_counts: Mapping[ActionType, int] = None

    # Behavior on all-pass (everyone bids 0)
    # If True: item is discarded (gems removed from game; loans/investments skipped).
    # If False: tiebreak decides a winner even at bid 0.
    discard_on_all_pass: bool = False

    # AUCTION_2 requires two upcoming gems. If only one remains, skip AUCTION_2.
    skip_auction2_if_insufficient_gems: bool = False

    def __post_init__(self):
        object.__setattr__(
            self,
            "info_cards_per_player",
            self.info_cards_per_player or {3: 5, 4: 4, 5: 3}
        )
        object.__setattr__(
            self,
            "starting_cash_by_players",
            self.starting_cash_by_players or {3: 30, 4: 25, 5: 20},
        )
        object.__setattr__(
            self,
            "action_counts",
            self.action_counts
            or {
                ActionType.AUCTION_1: 12,
                ActionType.AUCTION_2: 5,
                ActionType.LOAN_10: 2,
                ActionType.LOAN_20: 2,
                ActionType.INVESTMENT_5: 2,
                ActionType.INVESTMENT_10: 2,
            },
        )


# -----------------------------
# Internal mutable state
# -----------------------------

@dataclass
class _PlayerState:
    player_id: int
    name: str
    cash: int
    gems_owned: List[Card]
    loans: List[LoanPosition]
    investments: List[InvestmentPosition]
    revealed_info: List[Card]
    unrevealed_info: List[Card]
    trinket_points: int = 0

    @property
    def unrevealed_info_count(self) -> int:
        return len(self.unrevealed_info)


@dataclass
class _EngineState:
    # decks
    gem_draw_pile: List[Card]          # facedown remainder excluding upcoming
    upcoming: List[Card]               # 0..2 face-up row
    action_draw_pile: List[Action]     # facedown
    action_discard: List[Action]       # revealed actions in order

    # public counters
    action_counts_remaining: Optional[Dict[ActionType, int]]

    # seating / tiebreak
    seating_order: Tuple[int, ...]
    tiebreak_leader_id: int

    # trinkets
    trinkets: List[TrinketState]

    # valuation
    value_chart: ValueChart
    info_counts_by_suit_at_start: Dict[Suit, int]

    # history
    past_auctions: List[AuctionResult]


# -----------------------------
# Engine
# -----------------------------

class PocketRocketsEngine:
    def __init__(
        self,
        bots: Sequence[PocketRocketsBot],
        config: EngineConfig,
        *,
        value_chart: ValueChart,
        trinkets: Sequence[TrinketObjective],
        bot_names: Optional[Sequence[str]] = None,
    ):
        if not (3 <= len(bots) <= 5):
            raise ValueError("PocketRockets supports 3–5 players.")

        self._bots: List[PocketRocketsBot] = list(bots)
        self._cfg = config
        self._rng = random.Random(config.seed)

        self._num_players = len(bots)
        starting_cash = config.starting_cash_by_players.get(self._num_players)
        if starting_cash is None:
            raise ValueError(f"No starting cash configured for {self._num_players} players.")

        # Names
        if bot_names is None:
            names = [getattr(b, "bot_name", f"Bot{i}") for i, b in enumerate(self._bots)]
        else:
            if len(bot_names) != self._num_players:
                raise ValueError("bot_names length must match bots length.")
            names = list(bot_names)

        # Initialize player states
        self._players: List[_PlayerState] = [
            _PlayerState(
                player_id=i,
                name=str(names[i]),
                cash=starting_cash,
                gems_owned=[],
                loans=[],
                investments=[],
                revealed_info=[],
                unrevealed_info=[],
                trinket_points=0,
            )
            for i in range(self._num_players)
        ]

        # Create gem deck and action deck
        gem_deck = self._make_gem_deck(gems_per_suit=config.gems_per_suit)
        action_deck = self._make_action_deck(config.action_counts)

        # Shuffle decks
        self._rng.shuffle(gem_deck)
        self._rng.shuffle(action_deck)

        # Deal info cards
        self._deal_info_cards(gem_deck, config.info_cards_per_player[self._num_players])

        # Compute info counts at start (for final gem values)
        info_counts = {s: 0 for s in Suit}
        for p in self._players:
            for c in p.unrevealed_info:
                info_counts[c.suit] += 1
            for c in p.revealed_info:
                info_counts[c.suit] += 1  # usually 0 at start
        # Initialize upcoming gems (2 if possible)
        upcoming = []
        if gem_deck:
            upcoming.append(gem_deck.pop())
        if gem_deck:
            upcoming.append(gem_deck.pop())

        # Seating and initial tiebreak leader
        seating = tuple(range(self._num_players))
        tiebreak_leader = self._rng.choice(seating)

        # Public action counts remaining (optional)
        action_counts_remaining = dict(config.action_counts)

        self._state = _EngineState(
            gem_draw_pile=gem_deck,  # remaining facedown excluding upcoming
            upcoming=upcoming,
            action_draw_pile=action_deck,
            action_discard=[],
            action_counts_remaining=action_counts_remaining,
            seating_order=seating,
            tiebreak_leader_id=tiebreak_leader,
            trinkets=[TrinketState(objective=t, claimed_by=None) for t in trinkets],
            value_chart=value_chart,
            info_counts_by_suit_at_start=info_counts,
            past_auctions=[],
        )

    # --------- deck creation ---------

    def _make_gem_deck(self, *, gems_per_suit: int) -> List[Card]:
        deck: List[Card] = []
        gid = 0
        for suit in Suit:
            for _ in range(gems_per_suit):
                deck.append(Card(id=f"G{gid}", suit=suit))
                gid += 1
        return deck

    def _make_action_deck(self, counts: Mapping[ActionType, int]) -> List[Action]:
        deck: List[Action] = []
        aid = 0
        for kind, n in counts.items():
            for _ in range(int(n)):
                deck.append(Action(id=f"A{aid}", kind=kind))
                aid += 1
        return deck

    def _deal_info_cards(self, gem_deck: List[Card], per_player: int) -> None:
        needed = self._num_players * per_player
        if len(gem_deck) < needed:
            raise ValueError("Not enough gems to deal info cards.")
        for i in range(self._num_players):
            for _ in range(per_player):
                self._players[i].unrevealed_info.append(gem_deck.pop())

    # --------- snapshot building ---------

    def _build_public_state(self) -> GamePublicState:
        players_pub: List[PlayerPublicState] = []
        for p in self._players:
            players_pub.append(
                PlayerPublicState(
                    player_id=p.player_id,
                    name=p.name,
                    cash=p.cash,
                    gems_owned=tuple(p.gems_owned),
                    loans=tuple(p.loans),
                    investments=tuple(p.investments),
                    revealed_info=tuple(p.revealed_info),
                    unrevealed_info_count=p.unrevealed_info_count,
                    trinket_points=p.trinket_points,
                )
            )

        return GamePublicState(
            num_players=self._num_players,
            players=tuple(players_pub),
            trinkets=tuple(self._state.trinkets),
            value_chart=self._state.value_chart,
            action_discard=tuple(self._state.action_discard),
            past_auctions=tuple(self._state.past_auctions),
            action_counts_remaining=(dict(self._state.action_counts_remaining) if self._state.action_counts_remaining else None),
        )

    def _build_private_state(self, player_id: int) -> PlayerPrivateState:
        p = self._players[player_id]
        return PlayerPrivateState(
            player_id=player_id,
            info_cards_unrevealed=tuple(p.unrevealed_info),
            info_cards_revealed=tuple(p.revealed_info),
        )

    def _build_context(self, turn_index: int, action: Action) -> TurnContext:
        return TurnContext(
            turn_index=turn_index,
            action=action,
            upcoming_gems=tuple(self._state.upcoming),
            biddable_pile_count=len(self._state.gem_draw_pile),
            tiebreak_leader_id=self._state.tiebreak_leader_id,
            seating_order=self._state.seating_order,
        )

    def _build_observation(self, player_id: int, turn_index: int, action: Action) -> GameObservation:
        public = self._build_public_state()
        private = self._build_private_state(player_id)
        ctx = self._build_context(turn_index, action)
        me = next(p for p in public.players if p.player_id == player_id)
        return GameObservation(public=public, private=private, context=ctx, me=me)

    # --------- turn helpers ---------

    def _refill_upcoming(self) -> None:
        while len(self._state.upcoming) < 2 and self._state.gem_draw_pile:
            self._state.upcoming.append(self._state.gem_draw_pile.pop())

    def _tie_break_winner(self, tied_ids: List[int], leader_id: int) -> int:
        """
        Implemented as: start at seat after leader, scan clockwise; leader is last in scan.
        """
        order = list(self._state.seating_order)
        leader_idx = order.index(leader_id)
        scan = order[leader_idx + 1 :] + order[: leader_idx + 1]
        tied_set = set(tied_ids)
        for pid in scan:
            if pid in tied_set:
                return pid
        # Should never happen
        return tied_ids[0]

    def _collect_bids(self, turn_index: int, action: Action) -> List[int]:
        bids: List[int] = [0] * self._num_players
        for pid, bot in enumerate(self._bots):
            obs = self._build_observation(pid, turn_index, action)
            try:
                out = bot.get_bid(obs)
                amt = int(out.bid_amount)
            except Exception:
                amt = 0

            # legality: int >= 0 and <= cash
            if amt < 0 or amt > self._players[pid].cash:
                amt = 0

            bids[pid] = amt
        return bids

    def _resolve_winner(self, bids: List[int]) -> Tuple[int, int]:
        """
        Returns (winner_id, winning_bid).
        winner_id = -1 indicates "no winner" (only possible when discard_on_all_pass=True).
        """
        max_bid = max(bids)
        tied = [pid for pid, b in enumerate(bids) if b == max_bid]

        if max_bid == 0 and self._cfg.discard_on_all_pass:
            return (-1, 0)

        if len(tied) == 1:
            return (tied[0], max_bid)

        winner = self._tie_break_winner(tied, self._state.tiebreak_leader_id)
        return (winner, max_bid)

    def _award_trinkets_if_any(self, winner_id: int) -> List[str]:
        """
        Claim any unclaimed trinkets newly satisfied by winner.
        Deterministic order: the trinkets list order.
        """
        if winner_id < 0:
            return []

        claimed_ids: List[str] = []
        p = self._players[winner_id]
        for i, ts in enumerate(self._state.trinkets):
            if ts.claimed_by is not None:
                continue
            if objective_satisfied(ts.objective, p.gems_owned):
                self._state.trinkets[i] = TrinketState(objective=ts.objective, claimed_by=winner_id)
                p.trinket_points += ts.objective.points
                claimed_ids.append(ts.objective.id)

        return claimed_ids

    def _reveal_on_win(self, winner_id: int, turn_index: int, action: Action, result: AuctionResult) -> None:
        if winner_id < 0:
            return
        p = self._players[winner_id]
        if not p.unrevealed_info:
            return

        # Ask bot which info card to reveal
        bot = self._bots[winner_id]
        obs = self._build_observation(winner_id, turn_index, action)  # post-award, pre-reveal public snapshot
        try:
            chosen_id = str(bot.choose_info_to_reveal(obs, result))
        except Exception:
            chosen_id = ""

        chosen_idx = next((i for i, c in enumerate(p.unrevealed_info) if c.id == chosen_id), None)
        if chosen_idx is None:
            chosen_idx = 0  # deterministic fallback

        card = p.unrevealed_info.pop(chosen_idx)
        p.revealed_info.append(card)

    # --------- public API ---------

    def play(self) -> Dict[str, object]:
        turn_index = 0
        self._refill_upcoming()

        started = False

        while True:
            # --- END CONDITION: game ends when there are no more gems anywhere ---
            if len(self._state.upcoming) == 0 and len(self._state.gem_draw_pile) == 0:
                break

            # --- If actions run out but gems remain, reshuffle discard into draw pile ---
            # --- This shouldn't be possible
            if len(self._state.action_draw_pile) == 0:
                if len(self._state.action_discard) == 0:
                    # Safety valve: no actions left at all; end rather than infinite loop
                    break
                self._state.action_draw_pile = self._state.action_discard[:]
                self._state.action_discard.clear()
                self._rng.shuffle(self._state.action_draw_pile)

            action = self._state.action_draw_pile.pop()
            self._state.action_discard.append(action)

            if self._state.action_counts_remaining is not None:
                self._state.action_counts_remaining[action.kind] = max(
                    0, self._state.action_counts_remaining.get(action.kind, 0) - 1
                )

            # Skip gem-dependent actions if not enough upcoming gems
            if action.kind == ActionType.AUCTION_1 and len(self._state.upcoming) < 1:
                continue
            if action.kind == ActionType.AUCTION_2 and self._cfg.skip_auction2_if_insufficient_gems and len(self._state.upcoming) < 2:
                continue

            # Call on_game_start once at first playable action
            if not started:
                for pid, bot in enumerate(self._bots):
                    try:
                        bot.on_game_start(self._build_observation(pid, turn_index, action))
                    except Exception:
                        pass
                started = True

            # Collect bids
            bids = self._collect_bids(turn_index, action)
            winner_id, winning_bid = self._resolve_winner(bids)

            # Apply effects
            auctioned_gems: List[Card] = []
            trinkets_claimed: Optional[str] = None

            new_leader = self._state.tiebreak_leader_id
            if winner_id >= 0:
                new_leader = winner_id

            if winner_id >= 0:
                # Winner pays bid immediately
                self._players[winner_id].cash -= winning_bid

            if action.kind == ActionType.AUCTION_1:
                # Sell first upcoming gem
                if self._state.upcoming:
                    gem = self._state.upcoming.pop(0)
                    auctioned_gems.append(gem)
                    if winner_id >= 0:
                        self._players[winner_id].gems_owned.append(gem)
                # Refill upcoming to 2
                self._refill_upcoming()

            elif action.kind == ActionType.AUCTION_2:
                # Sell first two upcoming gems as bundle
                gems = []
                if len(self._state.upcoming) >= 1:
                    gems.append(self._state.upcoming.pop(0))
                if len(self._state.upcoming) >= 1:
                    gems.append(self._state.upcoming.pop(0))
                auctioned_gems.extend(gems)
                if winner_id >= 0:
                    self._players[winner_id].gems_owned.extend(gems)
                self._refill_upcoming()

            elif action.kind in (ActionType.LOAN_10, ActionType.LOAN_20):
                if winner_id >= 0:
                    principal = 10 if action.kind == ActionType.LOAN_10 else 20
                    # Winner receives principal immediately, takes loan position
                    self._players[winner_id].cash += principal
                    self._players[winner_id].loans.append(
                        LoanPosition(id=f"L{turn_index}", principal=principal, winning_bid=winning_bid)
                    )
                else:
                    # all-pass -> discard loan auction (do nothing)
                    pass

            elif action.kind in (ActionType.INVESTMENT_5, ActionType.INVESTMENT_10):
                if winner_id >= 0:
                    payout = 5 if action.kind == ActionType.INVESTMENT_5 else 10
                    # Winner’s bid is "locked" on the investment (already paid from cash).
                    self._players[winner_id].investments.append(
                        InvestmentPosition(id=f"I{turn_index}", payout=payout, locked=winning_bid)
                    )
                else:
                    # all-pass -> discard investment auction (do nothing)
                    pass

            else:
                raise ValueError(f"Unknown action kind: {action.kind}")

            # Trinkets claim check after acquisition
            claimed = self._award_trinkets_if_any(winner_id)
            if claimed:
                trinkets_claimed = ",".join(claimed)

            # Build result (public)
            result = AuctionResult(
                turn_index=turn_index,
                action=action,
                winner_id=winner_id,
                winning_bid=winning_bid,
                auctioned_gems=tuple(auctioned_gems),
                new_tiebreak_leader_id=new_leader,
                trinkets_claimed=trinkets_claimed,
                bids=tuple(bids),
            )

            # Update leader + history
            self._state.tiebreak_leader_id = new_leader
            self._state.past_auctions.append(result)

            # Call on_auction_resolved for all (pre-reveal snapshot)
            for pid, bot in enumerate(self._bots):
                try:
                    bot.on_auction_resolved(self._build_observation(pid, turn_index, action), result)
                except Exception:
                    pass

            # Reveal-on-win (after callbacks, before next turn)
            self._reveal_on_win(winner_id, turn_index, action, result)

            turn_index += 1

        # End game hooks
        final_public = self._build_public_state()
        for pid, bot in enumerate(self._bots):
            try:
                # pass last known context: use a dummy action if needed
                bot.on_game_end(GameObservation(
                    public=final_public,
                    private=self._build_private_state(pid),
                    context=TurnContext(
                        turn_index=turn_index,
                        action=Action(id="END", kind=ActionType.AUCTION_1),
                        upcoming_gems=tuple(self._state.upcoming),
                        biddable_pile_count=len(self._state.gem_draw_pile),
                        tiebreak_leader_id=self._state.tiebreak_leader_id,
                        seating_order=self._state.seating_order,
                    ),
                    me=next(p for p in final_public.players if p.player_id == pid),
                ))
            except Exception:
                pass

        return self._finalize()


    def _finalize(self) -> Dict[str, object]:
        scores: List[Tuple[int, str, int]] = []
        for p in self._players:
            score = self._compute_score(p)
            scores.append((p.player_id, p.name, score))
        scores.sort(key=lambda x: x[2], reverse=True)
        winner_id = scores[0][0] if scores else -1

        return {
            "final_scores": scores,
            "winner_id": winner_id,
            "history": tuple(self._state.past_auctions),
            "final_public_state": self._build_public_state(),
        }

    def _compute_score(self, p: _PlayerState) -> int:
        """
        Scoring per your rules:
        total =
          cash_on_hand
          + value_of_owned_gems
          + investment payouts + return of locked deposits
          + trinket points
          - loan principals (repay at end)
        """
        # cash as of end-of-play already includes loan proceeds and excludes investment bids.
        total = p.cash

        # Gem values determined by initial info distribution
        # value_chart.mapping[count] => per-gem value for that suit
        gem_values: Dict[Suit, int] = {}
        for suit in Suit:
            count = self._state.info_counts_by_suit_at_start.get(suit, 0)
            mapping = self._state.value_chart.mapping
            if count < 0:
                val = 0
            elif count >= len(mapping):
                val = 0
            else:
                val = mapping[count]
            gem_values[suit] = int(val)

        for g in p.gems_owned:
            total += gem_values[g.suit]

        # Investments: add payout + return of locked deposits
        for inv in p.investments:
            total += inv.payout + inv.locked

        # Loans: repay principal
        for loan in p.loans:
            total -= loan.principal

        # Trinkets already tracked on player public state
        total += p.trinket_points

        return int(total)