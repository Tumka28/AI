import importlib
import pkgutil

import bot_v


def test_every_module_imports():
    failures = {}
    for mod in pkgutil.walk_packages(bot_v.__path__, "bot_v."):
        try:
            importlib.import_module(mod.name)
        except Exception as exc:  # pragma: no cover - only on failure
            failures[mod.name] = repr(exc)
    assert failures == {}
