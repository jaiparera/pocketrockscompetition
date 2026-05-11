from pathlib import Path

import pytest

from src.bots.registry import load_private_bot_specs
from src.workflows.runner import (
    ReportPaths,
    ScenarioAxes,
    StageBenchmarkConfig,
    run_staged_benchmark,
)


def _small_axes() -> ScenarioAxes:
    return ScenarioAxes(
        products_enabled_values=(True, False),
        players_per_game_values=(3, 4),
        chart_keys=("A", "B"),
    )


def _small_cfg(seed: int = 77) -> StageBenchmarkConfig:
    return StageBenchmarkConfig(
        n_games_per_scenario=6,
        seed=seed,
        value_trader_risks=(0.6, 0.8, 1.0),
        final_top_value_traders=2,
        final_max_lineups=8,
    )


def test_staged_benchmark_outputs_and_sections(tmp_path: Path):
    if not load_private_bot_specs():
        pytest.skip("private bots are required for staged benchmark")

    out = run_staged_benchmark(
        axes=_small_axes(),
        config=_small_cfg(),
        report_paths=ReportPaths(output_dir=str(tmp_path), markdown_file="benchmark_report.md"),
    )

    assert out["scenario_count"] > 0
    assert Path(out["markdown_path"]).exists()

    report_text = Path(out["markdown_path"]).read_text(encoding="utf-8")
    assert "## Stage 1 Top Bots" in report_text
    assert "## Stage 2 Top Bots" in report_text
    assert "## Stage 3 Top Bots" in report_text

    assert (tmp_path / "scenario_results.csv").exists()
    assert (tmp_path / "seat_scores.csv").exists()
    assert (tmp_path / "stage_rankings.csv").exists()
    assert (tmp_path / "final_pool_results.csv").exists()


def test_staged_benchmark_is_deterministic_for_same_seed(tmp_path: Path):
    if not load_private_bot_specs():
        pytest.skip("private bots are required for staged benchmark")

    a_dir = tmp_path / "a"
    b_dir = tmp_path / "b"

    out_a = run_staged_benchmark(
        axes=_small_axes(),
        config=_small_cfg(seed=99),
        report_paths=ReportPaths(output_dir=str(a_dir), markdown_file="benchmark_report.md"),
    )
    out_b = run_staged_benchmark(
        axes=_small_axes(),
        config=_small_cfg(seed=99),
        report_paths=ReportPaths(output_dir=str(b_dir), markdown_file="benchmark_report.md"),
    )

    assert out_a["scenario_count"] == out_b["scenario_count"]
    assert out_a["top_value_traders"] == out_b["top_value_traders"]

    csv_a = (a_dir / "stage_rankings.csv").read_text(encoding="utf-8")
    csv_b = (b_dir / "stage_rankings.csv").read_text(encoding="utf-8")
    assert csv_a == csv_b


def test_stage3_uses_value_trader_variants(tmp_path: Path):
    if not load_private_bot_specs():
        pytest.skip("private bots are required for staged benchmark")

    out = run_staged_benchmark(
        axes=_small_axes(),
        config=_small_cfg(seed=123),
        report_paths=ReportPaths(output_dir=str(tmp_path), markdown_file="benchmark_report.md"),
    )

    stage3_rows = out["stage_rankings"]["stage3"]
    assert any(str(r["bot"]).startswith("ValueTrader(") for r in stage3_rows)
