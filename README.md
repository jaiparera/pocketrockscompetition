# PocketRocksCompetition

`src`-only Python toolkit for building PocketRocks bots with products-era rules.

## Commands

- `python run_public.py`: sample bots only
- `python run_mixed.py`: sample + private bots (if present)
- `python benchmark.py`: repeated evaluation with seat split summaries
- `python demo_game.py`: quick local game smoke run
- `python -m pytest -q`: test suite

## Repo Contract

- Canonical imports are `src.competition.*` and `src.bots.*`.
- Public committed bots live in `src/bots/samples`.
- Private secret bots live in `local/private_bots` (gitignored).
- Bot interface remains two-function:
  - `choose_bid(obs) -> int`
  - `choose_card(obs, result) -> str`

## Minimal Bot Development Examples

### 1) Handcrafted heuristic
Use `TemplateBot(mode="heuristic")` and tune `max_risk_fraction`.

### 2) Stats-style model
Use `TemplateBot(mode="stats")` and tune `stats_weight` to react to suit count signals.

### 3) Model-backed policy
Use `TemplateBot(mode="model", model_path="local/private_bots/model_bias.txt")`.
The template loads a small inference artifact if present and applies it as bid bias.

See [`docs/PRIVATE_BOTS.md`](./docs/PRIVATE_BOTS.md) for local registry wiring.
