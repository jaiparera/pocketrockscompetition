from pathlib import Path

from src.bots.template_bot import TemplateBot, TemplateConfig
from src.competition.contracts import Bid, GameObservation, PocketRocketsBot, ValueChart
from src.competition.engine import EngineConfig, PocketRocketsEngine


class _Passive(PocketRocketsBot):
    @property
    def bot_name(self) -> str:
        return "Passive"

    def get_bid(self, obs: GameObservation) -> Bid:
        return Bid(0)

    def choose_info_to_reveal(self, obs, result) -> str:
        return obs.private.info_cards_unrevealed[0].id if obs.private.info_cards_unrevealed else obs.private.info_cards_revealed[0].id


def _run_template(template: TemplateBot):
    bots = [template, _Passive(), _Passive()]
    out = PocketRocketsEngine(
        bots=bots,
        config=EngineConfig(seed=9, products_enabled=True),
        value_chart=ValueChart([0, 4, 8, 12, 16, 20]),
        bot_names=[b.bot_name for b in bots],
    ).play()
    assert "final_scores" in out


def test_template_heuristic_mode():
    _run_template(TemplateBot(TemplateConfig(mode="heuristic")))


def test_template_stats_mode():
    _run_template(TemplateBot(TemplateConfig(mode="stats", stats_weight=0.35)))


def test_template_model_mode_with_stub_artifact(tmp_path: Path):
    model_path = tmp_path / "model_bias.txt"
    model_path.write_text("2.0", encoding="utf-8")
    _run_template(TemplateBot(TemplateConfig(mode="model", model_path=str(model_path))))

