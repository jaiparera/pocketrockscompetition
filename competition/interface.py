"""
PocketRockets Bot Competition Interface (v1)

This file defines the *only* API contestants need to implement a PocketRockets bot.
The tournament engine will import your bot class and call the required methods.

Key ideas:
- Bots receive a read-only GameObservation each turn.
- Bots output a single integer bid for the current auction (0 = pass).
- If the bot wins an auction, the engine will call choose_info_to_reveal().
- All objects are immutable (frozen dataclasses) so bots can’t accidentally
  mutate engine state.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import Dict, FrozenSet, Iterable, List, Mapping, Optional, Sequence, Tuple
from abc import ABC, abstractmethod


# -----------------------------
# Core domain types
# -----------------------------

class Suit(Enum):
    RUBY = auto()
    SAPPHIRE = auto()
    EMERALD = auto()
    AMETHYST = auto()
    DIAMOND = auto()


@dataclass(frozen=True)
class Card:
    """The same structure is used for info cards and owned gems."""
    id: str
    suit: Suit


class ActionType(str, Enum):
    AUCTION_1 = "AUCTION_1"
    AUCTION_2 = "AUCTION_2"
    LOAN_10 = "LOAN_10"
    LOAN_20 = "LOAN_20"
    INVESTMENT_5 = "INVESTMENT_5"
    INVESTMENT_10 = "INVESTMENT_10"


@dataclass(frozen=True)
class Action:
    """The revealed action card for the current turn (or a historical one)."""
    id: str
    kind: ActionType


@dataclass(frozen=True)
class LoanPosition:
    """A loan card owned by a player. Principal must be repaid at game end."""
    id: str
    principal: int  # y in rules (10 or 20)
    winning_bid: int  # x paid when won (publicly known after resolution)


@dataclass(frozen=True)
class InvestmentPosition:
    """An investment card owned by a player."""
    id: str
    payout: int      # y in rules (5 or 10)
    locked: int      # x paid/locked when won (publicly known after resolution)
    
@dataclass(frozen=True)
class ValueChart:
    """
    A mapping from the number of gems in the info pile at the end of the game to their dollar value.
    """
    mapping: list[int]

@dataclass(frozen=True)
class TrinketObjective:
    """
    Bonus trinket objective. Worth points if claimed.
    The engine decides claim timing (first to satisfy).
    """
    id: str
    points: int  # 5, 10, 15 (per rules)
    required_cards: Tuple[Card, ...]

    # Public-facing text for humans (bots shouldn't parse this):
    display_text: str = ""


@dataclass(frozen=True)
class TrinketState:
    """Public state of a trinket objective."""
    objective: TrinketObjective
    claimed_by: Optional[int]  # player_id or None


@dataclass(frozen=True)
class PlayerPublicState:
    """
    Information visible to *all* players about a player.
    """
    player_id: int
    name: str
    cash: int

    # Owned cards/positions are public after acquisition.
    gems_owned: Tuple[Card, ...]
    loans: Tuple[LoanPosition, ...]
    investments: Tuple[InvestmentPosition, ...]

    # Info cards:
    revealed_info: Tuple[Card, ...]  # stays revealed
    unrevealed_info_count: int          # inferred in tabletop, explicit here

    # Convenience: total points from claimed trinkets (public because claimed is public)
    trinket_points: int


@dataclass(frozen=True)
class PlayerPrivateState:
    """
    Information visible only to this bot (its own private info cards).
    """
    player_id: int
    info_cards_unrevealed: Tuple[Card, ...]  # the *actual* unrevealed info cards you hold
    info_cards_revealed: Tuple[Card, ...]    # your revealed info cards (subset of public)


@dataclass(frozen=True)
class TurnContext:
    """
    What is happening right now.
    """
    turn_index: int
    action: Action

    # The "upcoming gems" row. Always length 0..2.
    # Index 0 is the next gem used for AUCTION_1_GEM or first of AUCTION_2_GEMS.
    upcoming_gems: Tuple[Card, ...]

    # Remaining gem cards in the facedown biddable pile (not including upcoming_gems).
    biddable_pile_count: int

    # Tiebreak leader: if bids tie, the winner is the tied player closest clockwise
    # from this leader excluding the leader. The winner becomes the new leader.
    tiebreak_leader_id: int

    # Player order in clockwise seating, starting at player 0 (engine-defined).
    # Use this together with tiebreak_leader_id for tie reasoning.
    seating_order: Tuple[int, ...]


@dataclass(frozen=True)
class GamePublicState:
    """
    Fully public game state snapshot (the bot sees this every turn).
    """
    num_players: int
    players: Tuple[PlayerPublicState, ...]
    trinkets: Tuple[TrinketState, ...]
    value_chart: ValueChart

    # History can be useful for learning patterns. This is public.
    # The engine may include only action kinds and outcomes (not hidden deck order).
    action_discard: Tuple[Action, ...]  # revealed actions so far (in order)
    past_auctions:  Tuple[AuctionResult, ...]

    # Optional: if the tournament specifies an exact action deck composition,
    # the engine can expose counts remaining; otherwise it will be None.
    action_counts_remaining: Optional[Mapping[ActionType, int]] = None


@dataclass(frozen=True)
class GameObservation:
    """
    What the engine passes to a bot.
    """
    public: GamePublicState
    private: PlayerPrivateState
    context: TurnContext

    # Convenience: your public state (same object as in public.players)
    me: PlayerPublicState = None  # set by engine when constructing, safe to assume present


# -----------------------------
# Bot outputs and events
# -----------------------------

@dataclass(frozen=True)
class Bid:
    """
    A simultaneous bid for the current auction.
    bid_amount must be an integer >= 0.
    0 means "pass".

    The engine enforces legality; illegal bids are treated as 0 (or disqualified),
    depending on tournament settings.
    """
    bid_amount: int


@dataclass(frozen=True)
class AuctionResult:
    """
    Public resolution of the current action.
    """
    turn_index: int
    action: Action
    winner_id: int
    winning_bid: int

    # What was auctioned (if applicable):
    auctioned_gems: Tuple[Card, ...]        # length 0,1,2

    # The updated tiebreak leader after this resolution (public)
    new_tiebreak_leader_id: int
    # If the winner claimed a trinket, it is here
    trinkets_claimed: Optional[str]
    bids: Optional[Tuple[int, ...]] = None 


# -----------------------------
# Bot base class (contestants implement)
# -----------------------------

class PocketRocketsBot(ABC):
    """
    Contestants: subclass PocketRocketsBot and implement required methods.

    The engine will:
    - Instantiate your bot once per game.
    - Call on_game_start() once with your initial observation (turn_index may be 0).
    - For each non-skipped turn, call get_bid() for a Bid.
    - Resolve the auction.
    - Call on_auction_resolved() with AuctionResult and updated observation.
    - If you won, call choose_info_to_reveal() (must return a Card.id from your unrevealed info).
    - Continue until game end, then call on_game_end().
    """

    @property
    @abstractmethod
    def bot_name(self) -> str:
        """A short display name used in logs/scoreboards."""
        raise NotImplementedError

    # ---- lifecycle hooks ----

    def on_game_start(self, obs: GameObservation) -> None:
        """Called once at the beginning. Optional to override."""
        return None

    @abstractmethod
    def get_bid(self, obs: GameObservation) -> Bid:
        """
        Called on each turn to request a simultaneous bid.
        Must be fast and deterministic within time limits set by the tournament.
        """
        raise NotImplementedError

    def on_auction_resolved(self, obs: GameObservation, result: AuctionResult) -> None:
        """Called after each turn resolution with the new state. Optional to override."""
        return None

    @abstractmethod
    def choose_info_to_reveal(self, obs: GameObservation, result: AuctionResult) -> str:
        """
        Called only if you won the auction for this turn.
        Return the id of one of your unrevealed info cards (Card.id) to reveal permanently.
        """
        raise NotImplementedError

    def on_game_end(self, obs: GameObservation) -> None:
        """Called once at the end. Optional to override."""
        return None


# -----------------------------
# Helper utilities (safe to use)
# -----------------------------

def get_player(public: GamePublicState, player_id: int) -> PlayerPublicState:
    for p in public.players:
        if p.player_id == player_id:
            return p
    raise KeyError(f"player_id {player_id} not found")


def legal_max_bid(obs: GameObservation) -> int:
    """
    Conservative legality rule: you must be able to pay the bid immediately.
    (Loans pay out after paying; investments lock after paying.)
    """
    return max(0, obs.me.cash)


def count_gems(cards: Iterable[Card]) -> Dict[Suit, int]:
    out: Dict[Suit, int] = {s: 0 for s in Suit}
    for c in cards:
        out[c.suit] += 1
    return out


def objective_satisfied(obj: TrinketObjective, gems_owned: Sequence[Card]) -> bool:
    """
    A pure helper for bots. The engine is the final authority on claiming.
    """
    counts = count_gems(gems_owned)
    trinket_counts = count_gems(obj.required_cards)

    for k, v in trinket_counts.items():
        if k not in counts or counts[k] < v:
            return False

    return True