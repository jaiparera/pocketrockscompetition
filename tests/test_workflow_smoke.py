from src.workflows.runner import WorkflowConfig, benchmark_with_seat_splits, render_report, run_simulation


def test_public_run_smoke():
    cfg = WorkflowConfig(
        bot_sources=["public"],
        include_private=False,
        n_games=10,
        seed=1,
        players_per_game=3,
        chart_keys=["A"],
    )
    res = run_simulation(cfg)
    text = render_report(res)
    assert "name,games,wins" in text


def test_benchmark_deterministic_summary():
    cfg = WorkflowConfig(
        bot_sources=["public"],
        include_private=False,
        n_games=6,
        seed=12,
        players_per_game=3,
        chart_keys=["A", "B"],
    )
    a = benchmark_with_seat_splits(cfg)
    b = benchmark_with_seat_splits(cfg)
    assert render_report(a["summary"]) == render_report(b["summary"])

