# PocketRocks Competition

A small, hackable Python tournament runner for ~MegaGem~ PocketRocks, a simultaneous-bid auction game with hidden information. Write a bot by implementing a tiny interface, then run round-robin style simulations to compare performance.

This repo contains:

`competition/`: the game interface, engine, simulator (tournament runner), and optional auditing tools 
`bots/`: example bots and helpers 
`run.py`: a simple entrypoint to run a local simulation 

## Game summary

3–5 players

Each turn reveals an action: auction 1 gem, auction 2 gems, loan, or investment

Everyone bids simultaneously (integer, 0 = pass)

Highest bidder wins and pays

Tie-break is deterministic using the current tie-break leader and seating order

Reveal-on-win: whenever you win an auction, you must reveal one of your secret “info” cards permanently

Gem values are determined by the initial distribution of info cards (revealed gradually over the game)

## Quickstart

Requires Python 3.10+.

`python run.py`


That should run a small tournament using the bundled bots and print a results table.

### Writing a bot

Bots implement a single class that subclasses PocketRocksBot (in competition/interface.py).

You must implement:

`bot_name` (property)

`get_bid(obs) -> Bid`

`choose_info_to_reveal(obs, result) -> str` (return a Card.id from your unrevealed info)

#### What bots can see

Each turn your bot gets a `GameObservation` with:

`public`: everything visible to all players (cash, owned gems, revealed info, trinkets, history)

`private`: your unrevealed info cards

`context`: the current action, the two upcoming gems, remaining pile size, tie-break leader, seating order

`me`: your public state convenience handle

All objects are frozen dataclasses (read-only). Attempting to mutate state should fail fast.

#### Running tournaments

The simulator runs n games, randomizes seating each game, and aggregates stats like win rate, average score, average rank, score spread, and more.

#### Typical flow:

1. Define bot entries with factories that return a fresh bot each game

2. Call the simulator

3. Print a report

If you have more than 5 bots, the simulator can run “pods” of 3–5 players sampled per game.

#### Trinkets

Each game uses 4 randomly chosen trinket objectives generated from these rules:

- 2-gem trinkets (pendants): worth 5 points, either 2 of the same suit, or 2 different suits.

- 3-gem trinkets: worth 10 points, all different suits

- 4-gem trinkets: worth 15 points, all different suits

The engine awards a trinket to the first player who satisfies its requirement; claimed trinkets remain for final scoring. This generation logic is subject to change and only temporary.

#### Determinism and seeding

Runs are deterministic given a seed. The engine uses a seed for deck order, tie-break initialization, and trinket selection.

The simulator should either derive a unique per-game seed from the simulation seed, or let you pass a seed per game. If you are evaluating bots, prefer many games (hundreds or thousands), and per-game randomization (seating, decks, trinkets).

#### Debugging and sanity checks

If results look suspicious (for example, a “pass-only” bot occasionally winning), add or enable the audit report:

- % of turns where everyone bid 0

- of wins at bid 0

- winning-bid distribution by action type

- per-bot score components (cash vs gems vs trinkets vs loans/investments)

This helps confirm whether odd outcomes come from game dynamics or from an engine rule mismatch.

## Contributing

PRs welcome for:

- stronger baseline bots

- better evaluation metrics (Elo, TrueSkill, head-to-head matrices)

- additional diagnostics and fairness checks

- speed improvements (faster simulation, fewer allocations)

- any bugs in the simulator