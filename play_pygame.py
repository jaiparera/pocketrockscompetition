from __future__ import annotations

import sys
import threading
import time
import random
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from src.bots.registry import resolve_bot_specs
from src.competition.contracts import ValueChart
from src.competition.engine import EngineConfig, PocketRocketsEngine
from src.competition.human_play import (
    HumanControlBridge,
    HumanDecisionRequest,
    HumanDecisionResponse,
    HumanInteractiveBot,
    ResourceCardView,
    TurnEvent,
    UiPlayerState,
    UiState,
    build_bot_lineup,
)

try:
    import pygame
except ImportError as exc:
    raise SystemExit("pygame is required. Install dependencies with: pip install -r requirements.txt") from exc


@dataclass
class GameRuntime:
    bridge: HumanControlBridge
    thread: Optional[threading.Thread] = None
    done: bool = False


W, H = 1520, 900
BG = (13, 19, 33)
PANEL = (18, 28, 48)
PANEL_2 = (24, 35, 59)
BORDER = (55, 78, 108)
TEXT = (219, 231, 245)
MUTED = (141, 165, 193)
EMERALD = (46, 204, 113)
AMBER = (245, 191, 79)
CYAN = (56, 189, 248)
RED = (239, 83, 80)

SUIT_COLORS = {
    "RUBY": (214, 76, 76),
    "SAPPHIRE": (72, 137, 232),
    "EMERALD": (64, 188, 104),
    "AMETHYST": (166, 120, 235),
    "DIAMOND": (240, 240, 240),
}
SUIT_NAMES = {
    "RUBY": "Brick",
    "SAPPHIRE": "Wood",
    "EMERALD": "Ore",
    "AMETHYST": "Sheep",
    "DIAMOND": "Wheat",
}


def start_game(players: int, bot_names: List[str], products_enabled: bool) -> GameRuntime:
    bridge = HumanControlBridge()
    human = HumanInteractiveBot(bridge=bridge, player_label="Human")
    specs = resolve_bot_specs(bot_sources=["public", "private"], include_private=True)
    by_name = {s.name: s for s in specs}
    chosen = []
    for name in bot_names:
        if name in by_name:
            chosen.append(by_name[name].factory())
    if len(chosen) < players - 1:
        fallback = [s.factory() for s in specs]
        chosen.extend(build_bot_lineup(fallback, seats_needed=(players - 1 - len(chosen))))
    lineup = [human] + chosen[: players - 1]
    names = ["Human"] + bot_names[: players - 1]
    runtime = GameRuntime(bridge=bridge)

    def worker() -> None:
        PocketRocketsEngine(
            bots=lineup,
            config=EngineConfig(seed=random.randrange(1_000_000_000), products_enabled=products_enabled),
            value_chart=ValueChart(mapping=[0, 4, 8, 12, 16, 20]),
            bot_names=names,
        ).play()
        runtime.done = True

    runtime.thread = threading.Thread(target=worker, daemon=True)
    runtime.thread.start()
    return runtime


def draw_text(screen, font, x: int, y: int, text: str, color=TEXT):
    screen.blit(font.render(text, True, color), (x, y))


def draw_panel(screen, rect, title: str, font, title_color=CYAN):
    pygame.draw.rect(screen, PANEL, rect, border_radius=12)
    pygame.draw.rect(screen, BORDER, rect, width=1, border_radius=12)
    draw_text(screen, font, rect.x + 10, rect.y + 8, title, title_color)


def draw_resource_card(screen, rect, card: ResourceCardView, small_font, back=False):
    fill = (38, 52, 80) if back else SUIT_COLORS.get(card.suit, (150, 150, 150))
    pygame.draw.rect(screen, fill, rect, border_radius=8)
    pygame.draw.rect(screen, (20, 20, 20), rect, width=1, border_radius=8)
    label = "?" if back else SUIT_NAMES.get(card.suit, card.suit)[:3]
    draw_text(screen, small_font, rect.x + 7, rect.y + 8, label, (17, 20, 28))
    draw_text(screen, small_font, rect.x + 7, rect.y + rect.h - 21, card.card_id[-3:], (17, 20, 28))


def signed_money(value: int) -> str:
    if value > 0:
        return f"+${value}"
    if value < 0:
        return f"-${abs(value)}"
    return "$0"


def draw_value_chart(screen, rect: pygame.Rect, values: Tuple[int, ...], font, small_font) -> None:
    pygame.draw.rect(screen, PANEL_2, rect, border_radius=8)
    pygame.draw.rect(screen, BORDER, rect, width=1, border_radius=8)
    draw_text(screen, font, rect.x + 8, rect.y + 6, "Value Chart")
    if not values:
        return

    left = rect.x + 34
    right = rect.x + rect.w - 14
    top = rect.y + 26
    bottom = rect.y + rect.h - 30
    width = right - left
    height = bottom - top

    pygame.draw.line(screen, MUTED, (left, top), (left, bottom), 1)
    pygame.draw.line(screen, MUTED, (left, bottom), (right, bottom), 1)

    max_value = max(values) if max(values) > 0 else 1
    bar_count = len(values)
    slot_w = max(16, width // max(1, bar_count))
    bar_w = max(10, int(slot_w * 0.65))

    for i, value in enumerate(values):
        bar_h = int((value / max_value) * (height - 8))
        x = left + i * slot_w + (slot_w - bar_w) // 2
        y = bottom - bar_h
        color = CYAN if i > 0 else MUTED
        pygame.draw.rect(screen, color, pygame.Rect(x, y, bar_w, bar_h), border_radius=3)
        draw_text(screen, small_font, x + 2, bottom + 5, str(i), MUTED)
        draw_text(screen, small_font, x + 1, max(top + 2, y - 15), str(value), TEXT)

    draw_text(screen, small_font, rect.x + 8, bottom + 5, "revealed count -> payout", MUTED)


def draw_action_banner(screen, rect: pygame.Rect, action_kind: str, font, small_font) -> None:
    if action_kind.startswith("AUCTION"):
        fill = (29, 78, 216)
    elif action_kind.startswith("LOAN"):
        fill = (190, 24, 93)
    elif action_kind.startswith("INVESTMENT"):
        fill = (5, 150, 105)
    else:
        fill = PANEL_2
    pygame.draw.rect(screen, fill, rect, border_radius=10)
    pygame.draw.rect(screen, AMBER, rect, width=2, border_radius=10)
    draw_text(screen, font, rect.x + 12, rect.y + 10, f"CURRENT ACTION: {action_kind}", (245, 245, 245))
    if action_kind == "AUCTION_1":
        sub = "Highest bidder wins the FIRST resource"
    elif action_kind == "AUCTION_2":
        sub = "Highest bidder wins FIRST + SECOND resources"
    elif action_kind.startswith("LOAN"):
        sub = "Winner receives loan principal now"
    elif action_kind.startswith("INVESTMENT"):
        sub = "Winner locks bid for endgame payout"
    else:
        sub = ""
    if sub:
        draw_text(screen, small_font, rect.x + 12, rect.y + 42, sub, (230, 240, 255))


def _pattern_slots(pattern: Optional[str]) -> List[Tuple[str, Tuple[int, int, int]]]:
    if pattern == "same2":
        return [("?", (173, 127, 255)), ("?", (173, 127, 255))]
    if pattern == "same3":
        return [("?", (173, 127, 255)), ("?", (173, 127, 255)), ("?", (173, 127, 255))]
    if pattern == "different3":
        return [("?", (67, 177, 255)), ("?", (67, 177, 255)), ("?", (67, 177, 255))]
    if pattern == "different4":
        return [("?", (67, 177, 255)), ("?", (67, 177, 255)), ("?", (67, 177, 255)), ("?", (67, 177, 255))]
    if pattern == "twoPairs4":
        return [("?", (245, 191, 79)), ("?", (245, 191, 79)), ("?", (245, 191, 79)), ("?", (245, 191, 79))]
    return []


def draw_product_requirements(screen, x: int, y: int, requirement: Dict[str, int], pattern: Optional[str], small_font) -> None:
    slots: List[Tuple[str, Tuple[int, int, int]]] = []
    if requirement:
        for suit_name, n in requirement.items():
            for _ in range(n):
                slots.append((SUIT_NAMES.get(suit_name, suit_name), SUIT_COLORS.get(suit_name, MUTED)))
    else:
        slots = _pattern_slots(pattern)
    for i, (label, color) in enumerate(slots[:6]):
        rx = x + i * 28
        pygame.draw.rect(screen, color, pygame.Rect(rx, y, 24, 30), border_radius=5)
        pygame.draw.rect(screen, (20, 20, 20), pygame.Rect(rx, y, 24, 30), width=1, border_radius=5)
        draw_text(screen, small_font, rx + 7, y + 8, "?" if label == "?" else label[0], (20, 20, 20))


def main() -> None:
    pygame.init()
    screen = pygame.display.set_mode((W, H))
    pygame.display.set_caption("PocketRocks Local Table")
    clock = pygame.time.Clock()
    h1 = pygame.font.SysFont("consolas", 24, bold=True)
    h2 = pygame.font.SysFont("consolas", 18, bold=True)
    body = pygame.font.SysFont("consolas", 16)
    small = pygame.font.SysFont("consolas", 14)

    mode = "lobby"
    selected_players = 3
    products_enabled = True
    specs = resolve_bot_specs(bot_sources=["public", "private"], include_private=True)
    bot_names_all = [s.name for s in specs] or ["AlwaysPass"]
    selected_bot_indices = [i % len(bot_names_all) for i in range(4)]
    runtime: Optional[GameRuntime] = None
    state: Optional[UiState] = None
    pending: Optional[HumanDecisionRequest] = None
    bid_value = 0
    status_line = ""
    flash_until_by_player: Dict[int, float] = {}
    lobby_focus = 0
    reveal_focus_index = 0

    while True:
        now = time.time()
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit(0)
            if event.type == pygame.KEYDOWN:
                if mode == "lobby":
                    active_seat_rows = selected_players - 1
                    # 0: player count, 1: products toggle, 2..(1+active_seat_rows): bot seats, last: start
                    lobby_focus_max = 2 + active_seat_rows
                    if event.key == pygame.K_UP:
                        lobby_focus = max(0, lobby_focus - 1)
                    elif event.key == pygame.K_DOWN:
                        lobby_focus = min(lobby_focus_max, lobby_focus + 1)
                    elif event.key == pygame.K_LEFT:
                        if lobby_focus == 0:
                            selected_players = max(3, selected_players - 1)
                        elif lobby_focus >= 2 and lobby_focus <= 1 + active_seat_rows:
                            seat_idx = lobby_focus - 2
                            if seat_idx < selected_players - 1:
                                selected_bot_indices[seat_idx] = (selected_bot_indices[seat_idx] - 1) % len(bot_names_all)
                    elif event.key == pygame.K_RIGHT:
                        if lobby_focus == 0:
                            selected_players = min(5, selected_players + 1)
                        elif lobby_focus >= 2 and lobby_focus <= 1 + active_seat_rows:
                            seat_idx = lobby_focus - 2
                            if seat_idx < selected_players - 1:
                                selected_bot_indices[seat_idx] = (selected_bot_indices[seat_idx] + 1) % len(bot_names_all)
                    elif event.key == pygame.K_RETURN:
                        if lobby_focus == lobby_focus_max:
                            chosen_names = [bot_names_all[selected_bot_indices[i]] for i in range(selected_players - 1)]
                            runtime = start_game(selected_players, chosen_names, products_enabled)
                            state = None
                            pending = None
                            bid_value = 0
                            status_line = ""
                            mode = "game"
                        elif lobby_focus == 1:
                            products_enabled = not products_enabled
                elif mode == "game" and pending:
                    if pending.kind == "bid":
                        if event.key == pygame.K_LEFT:
                            bid_value = max(pending.minimum, bid_value - 1)
                        elif event.key == pygame.K_RIGHT:
                            bid_value = min(pending.maximum, bid_value + 1)
                        elif event.key == pygame.K_RETURN and runtime:
                            runtime.bridge.post_response(HumanDecisionResponse(kind="bid", value=str(bid_value)))
                            pending = None
                            status_line = "Bid submitted."
                    elif pending.kind == "reveal":
                        options_len = len(pending.options)
                        if options_len > 0:
                            if event.key == pygame.K_LEFT:
                                reveal_focus_index = max(0, reveal_focus_index - 1)
                            elif event.key == pygame.K_RIGHT:
                                reveal_focus_index = min(options_len - 1, reveal_focus_index + 1)
                            elif event.key == pygame.K_UP:
                                reveal_focus_index = max(0, reveal_focus_index - 3)
                            elif event.key == pygame.K_DOWN:
                                reveal_focus_index = min(options_len - 1, reveal_focus_index + 3)
                            elif event.key == pygame.K_RETURN and runtime:
                                runtime.bridge.post_response(HumanDecisionResponse(kind="reveal", value=pending.options[reveal_focus_index]))
                                pending = None
                                status_line = "Reveal submitted."
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                x, y = event.pos
                if mode == "lobby":
                    col_x = 110
                    row0_y = 170
                    if col_x <= x <= col_x + 360 and row0_y <= y <= row0_y + 48:
                        if x < col_x + 85:
                            selected_players = max(3, selected_players - 1)
                        elif x > col_x + 275:
                            selected_players = min(5, selected_players + 1)
                    toggle_y = row0_y + 58
                    if col_x <= x <= col_x + 360 and toggle_y <= y <= toggle_y + 48:
                        products_enabled = not products_enabled
                    start_y = toggle_y + 58 + ((selected_players - 1) * 52) + 16
                    if col_x <= x <= col_x + 360 and start_y <= y <= start_y + 52:
                        chosen_names = [bot_names_all[selected_bot_indices[i]] for i in range(selected_players - 1)]
                        runtime = start_game(selected_players, chosen_names, products_enabled)
                        state = None
                        pending = None
                        bid_value = 0
                        status_line = ""
                        mode = "game"
                        lobby_focus = 0
                    for i in range(selected_players - 1):
                        row_y = toggle_y + 58 + i * 52
                        if col_x <= x <= col_x + 360 and row_y <= y <= row_y + 38:
                            if x < col_x + 60:
                                selected_bot_indices[i] = (selected_bot_indices[i] - 1) % len(bot_names_all)
                            elif x > col_x + 300:
                                selected_bot_indices[i] = (selected_bot_indices[i] + 1) % len(bot_names_all)
                elif mode == "game" and runtime and pending:
                    if pending.kind == "bid":
                        if 1040 <= x <= 1090 and 780 <= y <= 820:
                            bid_value = max(pending.minimum, bid_value - 1)
                        if 1100 <= x <= 1150 and 780 <= y <= 820:
                            bid_value = min(pending.maximum, bid_value + 1)
                        if 1160 <= x <= 1310 and 780 <= y <= 820:
                            runtime.bridge.post_response(HumanDecisionResponse(kind="bid", value=str(bid_value)))
                            pending = None
                            status_line = "Bid submitted."
                    elif pending.kind == "reveal":
                        for i, card_id in enumerate(pending.options):
                            bx = 1020 + (i % 3) * 100
                            by = 740 + (i // 3) * 60
                            if bx <= x <= bx + 90 and by <= y <= by + 48:
                                runtime.bridge.post_response(HumanDecisionResponse(kind="reveal", value=card_id))
                                pending = None
                                status_line = f"Revealed {card_id}"
                                break
                    if runtime.done and 1330 <= x <= 1475 and 845 <= y <= 885:
                        mode = "lobby"

        if mode == "game" and runtime:
            while True:
                new_state = runtime.bridge.poll_state()
                if new_state is None:
                    break
                if state and new_state.auction_reveal_strip and (
                    state.auction_reveal_strip is None
                    or new_state.auction_reveal_strip.turn_index != state.auction_reveal_strip.turn_index
                ):
                    for pid in new_state.auction_reveal_strip.bids_by_player.keys():
                        flash_until_by_player[int(pid)] = now + 0.45
                state = new_state
            req = runtime.bridge.poll_request()
            if req is not None:
                pending = req
                if req.kind == "bid":
                    bid_value = req.minimum
                    status_line = f"Your decision: bid ${req.minimum}..${req.maximum}"
                else:
                    status_line = "Your decision: reveal one private resource publicly."
                    reveal_focus_index = 0

        screen.fill(BG)

        if mode == "lobby":
            draw_text(screen, h1, 80, 80, "PocketRocks Local Play", AMBER)
            draw_text(screen, body, 80, 120, "Visual table mode with resources, value display, products, and priority marker.")
            col_x = 110
            row0_y = 170
            row_w = 360
            row_h = 48
            active_seat_rows = selected_players - 1
            lobby_focus_max = 2 + active_seat_rows

            # Row 0: player count control
            pygame.draw.rect(screen, PANEL, pygame.Rect(col_x, row0_y, row_w, row_h), border_radius=10)
            pygame.draw.rect(screen, BORDER, pygame.Rect(col_x, row0_y, row_w, row_h), width=1, border_radius=10)
            pygame.draw.rect(screen, (40, 64, 105) if lobby_focus == 0 else PANEL_2, pygame.Rect(col_x + 8, row0_y + 5, 72, 38), border_radius=8)
            pygame.draw.rect(screen, (40, 64, 105) if lobby_focus == 0 else PANEL_2, pygame.Rect(col_x + row_w - 80, row0_y + 5, 72, 38), border_radius=8)
            draw_text(screen, h2, col_x + 36, row0_y + 13, "-")
            draw_text(screen, h2, col_x + row_w - 52, row0_y + 13, "+")
            draw_text(screen, body, col_x + 96, row0_y + 15, f"Players: {selected_players}", CYAN)

            # Row 1: products toggle
            toggle_y = row0_y + 58
            toggle_color = (104, 74, 30) if products_enabled else PANEL_2
            if lobby_focus == 1:
                toggle_color = (132, 98, 44) if products_enabled else (40, 64, 105)
            pygame.draw.rect(screen, toggle_color, pygame.Rect(col_x, toggle_y, row_w, row_h), border_radius=10)
            pygame.draw.rect(screen, BORDER, pygame.Rect(col_x, toggle_y, row_w, row_h), width=1, border_radius=10)
            draw_text(screen, h2, col_x + 12, toggle_y + 13, f"Products Mode: {'ON' if products_enabled else 'OFF'}")

            draw_text(screen, body, col_x, toggle_y + 62, "Choose bots for open seats:", CYAN)
            for i in range(selected_players - 1):
                row_y = toggle_y + 92 + i * 52
                pygame.draw.rect(screen, PANEL, pygame.Rect(col_x, row_y, row_w, 38), border_radius=8)
                pygame.draw.rect(screen, BORDER, pygame.Rect(col_x, row_y, row_w, 38), width=1, border_radius=8)
                focused = lobby_focus == (2 + i)
                pygame.draw.rect(screen, (40, 64, 105) if focused else PANEL_2, pygame.Rect(col_x, row_y, 52, 38), border_radius=8)
                pygame.draw.rect(screen, (40, 64, 105) if focused else PANEL_2, pygame.Rect(col_x + row_w - 52, row_y, 52, 38), border_radius=8)
                draw_text(screen, h2, col_x + 18, row_y + 9, "<")
                draw_text(screen, h2, col_x + row_w - 34, row_y + 9, ">")
                draw_text(screen, body, col_x + 64, row_y + 10, f"Seat {i+2}: {bot_names_all[selected_bot_indices[i]]}")

            start_y = toggle_y + 92 + ((selected_players - 1) * 52) + 16
            pygame.draw.rect(screen, (40, 130, 84) if lobby_focus == lobby_focus_max else (24, 97, 64), pygame.Rect(col_x, start_y, row_w, 52), border_radius=10)
            pygame.draw.rect(screen, BORDER, pygame.Rect(col_x, start_y, row_w, 52), width=1, border_radius=10)
            draw_text(screen, h2, col_x + 12, start_y + 16, "Start Local Match")
            draw_text(screen, small, col_x, start_y + 64, "Keyboard: Up/Down focus. Left/Right adjust. Enter: toggle/start.", MUTED)
        else:
            left = pygame.Rect(20, 20, 560, 860)
            center = pygame.Rect(590, 20, 420, 860)
            right = pygame.Rect(1020, 20, 480, 860)
            draw_panel(screen, left, "Players", h2)
            draw_panel(screen, center, "Action Area", h2)
            draw_panel(screen, right, "Value Display + Products", h2)

            if state:
                draw_text(screen, body, center.x + 18, center.y + 45, f"Turn: {state.turn_index}")
                draw_action_banner(screen, pygame.Rect(center.x + 18, center.y + 66, center.w - 36, 64), state.action_kind, body, small)
                draw_text(screen, body, center.x + 18, center.y + 138, f"Priority marker: P{state.priority_marker_id}", AMBER)
                draw_text(screen, body, center.x + 18, center.y + 161, f"Resource deck: {state.resource_deck_count}")
                draw_text(screen, body, center.x + 18, center.y + 184, f"Action deck: {state.action_deck_count}")
                draw_text(screen, body, center.x + 18, center.y + 207, f"Products mode: {'ON' if state.products_enabled else 'OFF'}", AMBER if state.products_enabled else MUTED)
                draw_text(screen, body, center.x + 18, center.y + 232, "Resources up for auction:", CYAN)
                for i, card in enumerate(state.resources_up_for_auction):
                    ordinal = "First" if i == 0 else "Second" if i == 1 else f"#{i+1}"
                    draw_text(screen, small, center.x + 18 + i * 75, center.y + 246, ordinal, MUTED)
                    draw_resource_card(screen, pygame.Rect(center.x + 18 + i * 75, center.y + 262, 64, 88), card, small)

                y = left.y + 45
                for p in state.players:
                    box = pygame.Rect(left.x + 12, y, left.w - 24, 150)
                    color = PANEL_2
                    if p.player_id == state.priority_marker_id:
                        color = (64, 54, 26)
                    if flash_until_by_player.get(p.player_id, 0) > now:
                        color = (50, 78, 129)
                    pygame.draw.rect(screen, color, box, border_radius=10)
                    pygame.draw.rect(screen, BORDER, box, width=1, border_radius=10)
                    draw_text(screen, body, box.x + 10, box.y + 8, f"P{p.player_id} {p.name}", AMBER if p.player_id == state.priority_marker_id else TEXT)
                    draw_text(screen, small, box.x + 10, box.y + 32, f"Cash: ${p.cash}")
                    net = p.investment_payout_total - p.loan_principal_total
                    draw_text(screen, small, box.x + 120, box.y + 32, f"Paper: {signed_money(net)}", CYAN)
                    draw_text(screen, small, box.x + 260, box.y + 32, f"Products: ${p.product_value_total}", AMBER)
                    draw_text(screen, small, box.x + 10, box.y + 56, f"Private resources: {p.unrevealed_info_count} hidden / {p.revealed_info_count} revealed")
                    draw_text(screen, small, box.x + 10, box.y + 76, "Inventory:")
                    for i, card in enumerate(p.inventory_resources[:7]):
                        draw_resource_card(screen, pygame.Rect(box.x + 85 + i * 34, box.y + 72, 30, 42), card, small)
                    if p.player_id == state.me_player_id:
                        draw_text(screen, small, box.x + 10, box.y + 124, "Your private resources:")
                        for i, card in enumerate(p.private_resources[:8]):
                            draw_resource_card(screen, pygame.Rect(box.x + 185 + i * 34, box.y + 118, 30, 42), card, small)
                    y += 160

                draw_text(screen, body, right.x + 16, right.y + 45, "Revealed resources by suit", CYAN)
                sx = right.x + 20
                sy = right.y + 75
                for suit_name, cards in state.revealed_resources_by_suit.items():
                    draw_text(screen, small, sx, sy, f"{SUIT_NAMES.get(suit_name, suit_name)}: {len(cards)}", SUIT_COLORS.get(suit_name, TEXT))
                    for i, c in enumerate(cards[:6]):
                        draw_resource_card(screen, pygame.Rect(sx + 100 + i * 34, sy - 4, 30, 42), c, small)
                    sy += 52

                draw_value_chart(screen, pygame.Rect(right.x + 16, right.y + 360, 448, 130), state.value_chart, body, small)
                draw_text(screen, body, right.x + 16, right.y + 505, "Products to claim", AMBER)
                py = right.y + 532
                for prod in state.active_products[:5]:
                    req = ", ".join(f"{SUIT_NAMES.get(k, k)}x{v}" for k, v in prod.requirement.items()) or "Pattern"
                    owner = f"P{prod.claimed_by_player_id}" if prod.claimed_by_player_id is not None else "Unclaimed"
                    color = EMERALD if prod.claimed_by_player_id is not None else MUTED
                    draw_text(screen, small, right.x + 16, py, f"{prod.name} (${prod.payout}) [{owner}] {req}", color)
                    draw_product_requirements(screen, right.x + 18, py + 18, dict(prod.requirement), prod.pattern, small)
                    py += 48

                draw_text(screen, body, center.x + 18, center.y + 370, "Auction reveal strip", AMBER)
                strip: Optional[TurnEvent] = state.auction_reveal_strip
                if strip:
                    draw_text(screen, small, center.x + 18, center.y + 396, strip.summary)
                    bx = center.x + 18
                    by = center.y + 422
                    for pid, bid in strip.bids_by_player.items():
                        color = EMERALD if pid == strip.winner_id else MUTED
                        if pid in strip.tied_player_ids and len(strip.tied_player_ids) > 1:
                            color = AMBER
                        draw_text(screen, small, bx, by, f"P{pid}: ${bid}", color)
                        bx += 90
                    reveal_text = SUIT_NAMES.get(strip.revealed_resource.suit, strip.revealed_resource.suit) if strip.revealed_resource else "-"
                    draw_text(screen, small, center.x + 18, center.y + 448, f"Reveal: {reveal_text}")
                    draw_text(screen, small, center.x + 18, center.y + 470, f"Claims: {', '.join(strip.product_claim_ids) if strip.product_claim_ids else '-'}")

                draw_text(screen, body, center.x + 18, center.y + 520, "Turn event log (newest first)", CYAN)
                log_y = center.y + 548
                for ev in reversed(state.turn_events[-6:]):
                    draw_text(screen, small, center.x + 18, log_y, ev.summary)
                    log_y += 22

                if state.game_over and state.final_scores:
                    draw_text(screen, h2, center.x + 18, center.y + 680, "Final money ranking", AMBER)
                    yy = center.y + 712
                    for pid, name, score in state.final_scores:
                        draw_text(screen, body, center.x + 18, yy, f"P{pid} {name}: ${score}")
                        yy += 25

            draw_text(screen, body, center.x + 18, center.y + center.h - 26, state.status_text if state else status_line, CYAN)
            if pending:
                if pending.kind == "bid":
                    draw_text(screen, body, right.x + 16, right.y + right.h - 26, f"Bid panel: range ${pending.minimum}..${pending.maximum}")
                    pygame.draw.rect(screen, PANEL_2, pygame.Rect(1040, 780, 50, 40), border_radius=8)
                    pygame.draw.rect(screen, PANEL_2, pygame.Rect(1100, 780, 50, 40), border_radius=8)
                    pygame.draw.rect(screen, (24, 97, 64), pygame.Rect(1160, 780, 150, 40), border_radius=8)
                    draw_text(screen, h2, 1060, 788, "-", TEXT)
                    draw_text(screen, h2, 1120, 788, "+", TEXT)
                    draw_text(screen, body, 1168, 790, f"Confirm ${bid_value}", TEXT)
                    draw_text(screen, small, 1028, 830, "Keyboard: Left/Right adjust bid, Enter confirms.", MUTED)
                else:
                    draw_text(screen, body, right.x + 16, right.y + right.h - 26, "Reveal chooser: this becomes public in value display.")
                    me = next((p for p in state.players if p.player_id == state.me_player_id), None) if state else None
                    by_card_id = {c.card_id: c for c in (me.private_resources if me else ())}
                    for i, card_id in enumerate(pending.options):
                        bx = 1020 + (i % 3) * 100
                        by = 740 + (i // 3) * 60
                        card = by_card_id.get(card_id, ResourceCardView(card_id=card_id, suit="RUBY"))
                        suit_color = SUIT_COLORS.get(card.suit, PANEL_2)
                        pygame.draw.rect(screen, suit_color, pygame.Rect(bx, by, 90, 48), border_radius=8)
                        pygame.draw.rect(screen, (20, 20, 20), pygame.Rect(bx, by, 90, 48), width=1, border_radius=8)
                        if i == reveal_focus_index:
                            pygame.draw.rect(screen, AMBER, pygame.Rect(bx - 2, by - 2, 94, 52), width=2, border_radius=9)
                        draw_text(screen, small, bx + 6, by + 6, SUIT_NAMES.get(card.suit, card.suit), (20, 20, 20))
                        draw_text(screen, small, bx + 6, by + 24, card_id[-4:], (20, 20, 20))
                    draw_text(screen, small, 1028, 830, "Keyboard: arrows move selection, Enter reveals.", MUTED)

            if runtime and runtime.done:
                pygame.draw.rect(screen, (40, 64, 105), pygame.Rect(1330, 845, 145, 40), border_radius=8)
                draw_text(screen, body, 1340, 857, "Back to Lobby")

        pygame.display.flip()
        clock.tick(60)


if __name__ == "__main__":
    main()
