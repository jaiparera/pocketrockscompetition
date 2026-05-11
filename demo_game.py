from src.bots.registry import resolve_bot_specs
from src.competition.contracts import ValueChart
from src.competition.engine import EngineConfig, PocketRocketsEngine


def main() -> None:
    specs = resolve_bot_specs(bot_sources=["public"], include_private=False)[:3]
    bots = [s.factory() for s in specs]
    names = [s.name for s in specs]
    out = PocketRocketsEngine(
        bots=bots,
        config=EngineConfig(seed=42, products_enabled=True),
        value_chart=ValueChart(mapping=[0, 4, 8, 12, 16, 20]),
        bot_names=names,
    ).play()
    print("final_scores")
    for pid, name, score in out["final_scores"]:
        print(f"{pid},{name},{score}")
    print(f"winner_id,{out['winner_id']}")
    print(f"turns,{len(out['history'])}")


if __name__ == "__main__":
    main()

