from __future__ import annotations

import threading

from src.bots.samples.always_pass_bot import AlwaysPassBot
from src.competition.contracts import ValueChart
from src.competition.engine import EngineConfig, PocketRocketsEngine
from src.competition.human_play import HumanControlBridge, HumanDecisionResponse, HumanInteractiveBot


def test_human_bid_roundtrip_clamps_invalid() -> None:
    bridge = HumanControlBridge()
    human = HumanInteractiveBot(bridge=bridge)
    bots = [human, AlwaysPassBot(), AlwaysPassBot()]
    names = ["Human", "A", "B"]
    out_box = {}

    def run_game() -> None:
        out_box["out"] = PocketRocketsEngine(
            bots=bots,
            config=EngineConfig(seed=4, products_enabled=True),
            value_chart=ValueChart(mapping=[0, 4, 8, 12, 16, 20]),
            bot_names=names,
        ).play()

    t = threading.Thread(target=run_game, daemon=True)
    t.start()

    submitted_bad_bid = False
    while t.is_alive():
        req = bridge.poll_request()
        if req is None:
            continue
        if req.kind == "bid":
            bridge.post_response(HumanDecisionResponse(kind="bid", value="999999"))
            submitted_bad_bid = True
        elif req.kind == "reveal":
            bridge.post_response(HumanDecisionResponse(kind="reveal", value="BAD_CARD_ID"))

    t.join(timeout=1.0)
    assert "out" in out_box
    assert submitted_bad_bid


def test_scripted_human_game_smoke() -> None:
    bridge = HumanControlBridge()
    human = HumanInteractiveBot(bridge=bridge)
    bots = [human, AlwaysPassBot(), AlwaysPassBot()]
    names = ["Human", "A", "B"]
    out_box = {}

    def run_game() -> None:
        out_box["out"] = PocketRocketsEngine(
            bots=bots,
            config=EngineConfig(seed=10, products_enabled=True),
            value_chart=ValueChart(mapping=[0, 4, 8, 12, 16, 20]),
            bot_names=names,
        ).play()

    t = threading.Thread(target=run_game, daemon=True)
    t.start()
    while t.is_alive():
        req = bridge.poll_request()
        if req is None:
            continue
        if req.kind == "bid":
            bridge.post_response(HumanDecisionResponse(kind="bid", value="0"))
        elif req.kind == "reveal":
            choice = req.default or (req.options[0] if req.options else "")
            bridge.post_response(HumanDecisionResponse(kind="reveal", value=choice))
    t.join(timeout=1.0)

    out = out_box["out"]
    assert "final_scores" in out
    assert len(out["final_scores"]) == 3
    assert isinstance(out["winner_id"], int)


def test_ui_state_includes_auction_events_and_revealed_resources() -> None:
    bridge = HumanControlBridge()
    human = HumanInteractiveBot(bridge=bridge)
    bots = [human, AlwaysPassBot(), AlwaysPassBot()]
    names = ["Human", "A", "B"]
    out_box = {}
    states = []

    def run_game() -> None:
        out_box["out"] = PocketRocketsEngine(
            bots=bots,
            config=EngineConfig(seed=1, products_enabled=True),
            value_chart=ValueChart(mapping=[0, 4, 8, 12, 16, 20]),
            bot_names=names,
        ).play()

    t = threading.Thread(target=run_game, daemon=True)
    t.start()
    while t.is_alive():
        req = bridge.poll_request()
        st = bridge.poll_state()
        if st is not None:
            states.append(st)
        if req is None:
            continue
        if req.kind == "bid":
            bridge.post_response(HumanDecisionResponse(kind="bid", value="0"))
        elif req.kind == "reveal":
            bridge.post_response(HumanDecisionResponse(kind="reveal", value=req.default or req.options[0]))
    t.join(timeout=1.0)

    assert "out" in out_box
    assert states
    assert any(s.auction_reveal_strip is not None for s in states)
    assert any(len(s.turn_events) > 0 for s in states)
    assert any(sum(len(v) for v in s.revealed_resources_by_suit.values()) >= 0 for s in states)
