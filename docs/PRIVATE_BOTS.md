# Private Bots

Put secret strategy code in:

- `local/private_bots/registry.py`
- `local/private_bots/*.py`
- optional artifacts like `local/private_bots/model_bias.txt`

`run_mixed.py` and `benchmark.py` can include these private bots. Public runs never depend on them.

## Registry shape

```python
from dataclasses import dataclass
from typing import Callable
from src.competition.contracts import PocketRocketsBot
from local.private_bots.my_secret_bot import MySecretBot

@dataclass(frozen=True)
class BotSpec:
    name: str
    factory: Callable[[], PocketRocketsBot]

PRIVATE_BOTS = [
    BotSpec("SecretBotV1", lambda: MySecretBot()),
]
```
