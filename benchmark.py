from statistics import mean

from src.workflows.runner import WorkflowConfig, benchmark_with_seat_splits, render_report


def main() -> None:
    config = WorkflowConfig(
        bot_sources=["public", "private"],
        include_private=True,
        n_games=200,
        seed=101,
        players_per_game=3,
        chart_keys=["A", "B", "C", "D", "E"],
        products_enabled=True,
    )
    data = benchmark_with_seat_splits(config)
    print(render_report(data["summary"]))
    print("\nseat,bot,avg_score")
    for bot_name, seat_map in sorted(data["seat_means"].items()):
        for seat, avg_score in sorted(seat_map.items()):
            print(f"{seat},{bot_name},{avg_score:.2f}")
    all_scores = []
    for st in data["summary"].per_bot.values():
        all_scores.extend(st.scores)
    if all_scores:
        print(f"\noverall_score_mean,{mean(all_scores):.2f}")


if __name__ == "__main__":
    main()

