"""Load the pure modules without pulling in Home Assistant.

The integration package's __init__ imports homeassistant, so a normal
`from custom_components.ev_charge_planner.planner import ...` would require the whole
of HA to be installed just to test a hundred lines of arithmetic.

Instead we register a synthetic parent package with an empty __init__ and load the
pure modules into it by path. Relative imports between them (planner, const,
price_adapters, car_adapters) still resolve, because they resolve against the
synthetic package. Nothing here touches the real integration package.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

PKG = "_ev_charge_planner_pure"
SRC = Path(__file__).resolve().parents[1] / "custom_components" / "ev_charge_planner"

if PKG not in sys.modules:
    package = types.ModuleType(PKG)
    package.__path__ = [str(SRC)]
    sys.modules[PKG] = package


def load(name: str):
    """Import one module of the integration in isolation."""
    full = f"{PKG}.{name}"
    if full in sys.modules:
        return sys.modules[full]
    spec = importlib.util.spec_from_file_location(full, SRC / f"{name}.py")
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise ImportError(f"cannot load {name} from {SRC}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[full] = module
    spec.loader.exec_module(module)
    return module


# Order matters only in that dependencies must be importable; load() is lazy enough
# that importing the leaves pulls in what they need.
const = load("const")
planner = load("planner")
price_adapters = load("price_adapters")
car_adapters = load("car_adapters")
