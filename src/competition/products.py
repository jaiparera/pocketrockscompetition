from __future__ import annotations

import random
from itertools import combinations
from typing import Dict, List, Mapping, Optional, Sequence

from .contracts import ActiveProduct, OwnedProduct, ProductDefinition, Suit

DEFAULT_PRODUCTS_PER_GAME = 4


def empty_requirement() -> Dict[Suit, int]:
    return {s: 0 for s in Suit}


def build_product_catalog() -> List[ProductDefinition]:
    catalog: List[ProductDefinition] = []
    suits = list(Suit)

    any_same2 = empty_requirement()
    any_same2[suits[0]] = 2
    any_same3 = empty_requirement()
    any_same3[suits[0]] = 3
    any_diff3 = empty_requirement()
    any_diff3[suits[0]] = 1
    any_diff3[suits[1]] = 1
    any_diff3[suits[2]] = 1
    any_diff4 = empty_requirement()
    any_diff4[suits[0]] = 1
    any_diff4[suits[1]] = 1
    any_diff4[suits[2]] = 1
    any_diff4[suits[3]] = 1
    any_two_pairs = empty_requirement()
    any_two_pairs[suits[0]] = 2
    any_two_pairs[suits[1]] = 2

    catalog.extend(
        [
            ProductDefinition("prod-any-same2", "Any Pair", any_same2, 5, "same2"),
            ProductDefinition("prod-any-same3", "Three of a Kind", any_same3, 10, "same3"),
            ProductDefinition("prod-any-different3", "Three Different", any_diff3, 5, "different3"),
            ProductDefinition("prod-any-different4", "Four Different", any_diff4, 10, "different4"),
            ProductDefinition("prod-any-two-pairs4", "Two Pairs", any_two_pairs, 15, "twoPairs4"),
        ]
    )

    for suit in suits:
        req = empty_requirement()
        req[suit] = 2
        catalog.append(ProductDefinition(f"prod-spec-same2-{suit.name}", f"Pair of {suit.name}", req, 5))

    for combo in combinations(suits, 2):
        req = empty_requirement()
        for suit in combo:
            req[suit] = 1
        key = "-".join(s.name for s in combo)
        catalog.append(ProductDefinition(f"prod-spec-diff2-{key}", f"Pair {key}", req, 5))

    for combo in combinations(suits, 3):
        req = empty_requirement()
        for suit in combo:
            req[suit] = 1
        key = "-".join(s.name for s in combo)
        catalog.append(ProductDefinition(f"prod-spec-diff3-{key}", f"Set {key}", req, 10))

    return catalog


PRODUCT_CATALOG: List[ProductDefinition] = build_product_catalog()


def select_products_for_game(
    catalog: Sequence[ProductDefinition],
    *,
    rng: random.Random,
    per_game: int = DEFAULT_PRODUCTS_PER_GAME,
) -> List[ActiveProduct]:
    if not catalog or per_game <= 0:
        return []
    seen: Dict[str, ProductDefinition] = {}
    for p in catalog:
        if p.id not in seen:
            seen[p.id] = p
    base = list(seen.values())
    rng.shuffle(base)
    selected = base[: min(per_game, len(base))]
    return [
        ActiveProduct(
            id=p.id,
            name=p.name,
            requirement=dict(p.requirement),
            payout=p.payout,
            pattern=p.pattern,
            claimed_by_player_id=None,
        )
        for p in selected
    ]


def owned_from_active(product: ActiveProduct) -> OwnedProduct:
    return OwnedProduct(
        id=product.id,
        name=product.name,
        requirement=dict(product.requirement),
        payout=product.payout,
        pattern=product.pattern,
    )


def _meets_requirement(requirement: Mapping[Suit, int], counts: Mapping[Suit, int]) -> bool:
    for suit, needed in requirement.items():
        if needed > 0 and counts.get(suit, 0) < needed:
            return False
    return True


def _meets_pattern(product: ProductDefinition, counts: Mapping[Suit, int]) -> bool:
    all_suits = list(Suit)
    if product.pattern == "same2":
        return any(counts.get(s, 0) >= 2 for s in all_suits)
    if product.pattern == "same3":
        return any(counts.get(s, 0) >= 3 for s in all_suits)
    if product.pattern == "different3":
        return sum(1 for s in all_suits if counts.get(s, 0) > 0) >= 3
    if product.pattern == "different4":
        return sum(1 for s in all_suits if counts.get(s, 0) > 0) >= 4
    if product.pattern == "twoPairs4":
        return sum(1 for s in all_suits if counts.get(s, 0) >= 2) >= 2
    return _meets_requirement(product.requirement, counts)


def claim_eligible_products_for_winner(
    active_products: List[ActiveProduct],
    winner_id: int,
    winner_resource_counts: Mapping[Suit, int],
) -> List[ActiveProduct]:
    claimed: List[ActiveProduct] = []
    for idx, product in enumerate(active_products):
        if product.claimed_by_player_id is not None:
            continue
        if not _meets_pattern(product, winner_resource_counts):
            continue
        updated = ActiveProduct(
            id=product.id,
            name=product.name,
            requirement=dict(product.requirement),
            payout=product.payout,
            pattern=product.pattern,
            claimed_by_player_id=winner_id,
        )
        active_products[idx] = updated
        claimed.append(updated)
    return claimed

