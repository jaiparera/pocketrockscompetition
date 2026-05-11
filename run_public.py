from src.workflows.runner import WorkflowConfig, render_report, run_simulation


def main() -> None:
    config = WorkflowConfig(
        bot_sources=["public"],
        include_private=False,
        n_games=300,
        seed=7,
        players_per_game=3,
        chart_keys=["A", "B", "C"],
        products_enabled=True,
    )
    result = run_simulation(config)
    print(render_report(result))


if __name__ == "__main__":
    main()

