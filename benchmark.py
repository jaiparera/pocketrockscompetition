import argparse
from statistics import mean

from src.workflows.runner import (
    ReportPaths,
    StageBenchmarkConfig,
    WorkflowConfig,
    benchmark_with_seat_splits,
    render_report,
    run_staged_benchmark,
)


def run_simple() -> None:
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


def run_staged() -> None:
    out = run_staged_benchmark(
        config=StageBenchmarkConfig(),
        report_paths=ReportPaths(output_dir="local/benchmark_outputs", markdown_file="benchmark_report.md"),
    )
    print(f"staged_benchmark_output_dir,{out['output_dir']}")
    print(f"staged_benchmark_report,{out['markdown_path']}")
    print(f"scenario_count,{out['scenario_count']}")
    print(f"top_value_traders,{'|'.join(out['top_value_traders'])}")


def main() -> None:
    parser = argparse.ArgumentParser(description="PocketRocks benchmark runner")
    parser.add_argument("--simple", action="store_true", help="run legacy single-config benchmark mode")
    args = parser.parse_args()

    if args.simple:
        run_simple()
        return
    run_staged()


if __name__ == "__main__":
    main()
