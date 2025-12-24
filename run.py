from competition.simulator import run_pocketrocks_simulation, print_pocketrocks_report, BotEntry
from time import time

# -----------------------------
# Convenience: factories for the simulator
# -----------------------------

from bots.always_pass_bot import AlwaysPassBot
from bots.random_bid_bot import RandomBidBot
from bots.greedy_trinket_bot import GreedyTrinketBot
from bots.value_trader_bot import ValueTraderBot

def make_bot_entries_for_sim() -> list["BotEntry"]:
    return [
        BotEntry("AlwaysPass", lambda: AlwaysPassBot()),
        BotEntry("RandomBid", lambda: RandomBidBot()),
        BotEntry("GreedyTrinket", lambda: GreedyTrinketBot()),
        BotEntry("ValueTraderRisk10", lambda: ValueTraderBot(risk=0.10)),
        BotEntry("ValueTraderRisk20", lambda: ValueTraderBot(risk=0.20)),
        BotEntry("ValueTraderRisk30", lambda: ValueTraderBot(risk=0.30)),
        BotEntry("ValueTraderRisk40", lambda: ValueTraderBot(risk=0.40)),
        BotEntry("ValueTraderRisk50", lambda: ValueTraderBot(risk=0.50)),
        BotEntry("ValueTraderRisk70", lambda: ValueTraderBot(risk=0.70)),
    ]

entries = make_bot_entries_for_sim()
n_games = 500
print("3 player report")
res = run_pocketrocks_simulation(entries, n_games=n_games, players_per_game=3)                     # uses len(entries); must be 3–5
print_pocketrocks_report(res)

print("4 player report")
res = run_pocketrocks_simulation(entries, n_games=n_games, players_per_game=4)                     # uses len(entries); must be 3–5
print_pocketrocks_report(res)

print("5 player report")
res = run_pocketrocks_simulation(entries, n_games=n_games, players_per_game=5)                     # uses len(entries); must be 3–5
print_pocketrocks_report(res)