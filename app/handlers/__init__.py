"""Event handler auto-discovery."""

import importlib
import pkgutil


def discover_handlers(package: str = "app.handlers") -> list[str]:
    """Import every non-underscore submodule so ``@on`` decorators run."""
    pkg = importlib.import_module(package)
    imported: list[str] = []
    for m in sorted(pkgutil.iter_modules(pkg.__path__), key=lambda m: m.name):
        if m.name.startswith("_"):
            continue
        full = f"{package}.{m.name}"
        importlib.import_module(full)
        imported.append(full)
    return imported
