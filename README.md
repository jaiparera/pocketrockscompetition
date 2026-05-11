# PocketRocksCompetition

`src`-only Python toolkit for building PocketRocks bots with products-era rules.

## Commands

- `python run_public.py`: sample bots only
- `python run_mixed.py`: sample + private bots (if present)
- `python benchmark.py`: repeated evaluation with seat split summaries
- `python demo_game.py`: quick local game smoke run
- `python play_pygame.py`: local human-vs-bots playable game (3-5 players)
- `python -m pytest -q`: test suite

## Local Play Setup

1. Install dependencies:
   - `pip install -r requirements.txt`
2. Launch local play:
   - `python play_pygame.py`

Notes:
- The playable mode always tries to load both public and private bots.
- If `local/private_bots/registry.py` is missing or empty, it falls back to public bots automatically.
- The table uses PocketRocks player-facing terms: resources, value display, products, and priority marker.
- The UI shows per-turn bid reveals, recent event log entries, revealed resources by suit, and player inventory/private resource context.
- Lobby supports selecting which bots fill each non-human seat.
- Lobby has a Products mode toggle; active products are shown on the table when enabled.
- Value chart is visible in-table during play.

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
