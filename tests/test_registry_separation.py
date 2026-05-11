from src.bots.registry import load_private_bot_specs, resolve_bot_specs


def test_public_only_never_loads_private():
    specs = resolve_bot_specs(bot_sources=["public"], include_private=False)
    assert specs
    assert all("Secret" not in s.name for s in specs)


def test_missing_private_registry_is_clean():
    private_specs = load_private_bot_specs()
    assert isinstance(private_specs, list)

