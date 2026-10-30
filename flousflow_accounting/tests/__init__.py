"""Expose tests from the merged source addons to Odoo's test loader."""

import importlib
import importlib.util
import pkgutil
from types import ModuleType

from .. import legacy


for addon in pkgutil.iter_modules(legacy.__path__):
    if not addon.ispkg:
        continue

    tests_package_name = f"{legacy.__name__}.{addon.name}.tests"
    if importlib.util.find_spec(tests_package_name) is None:
        continue

    tests_package = importlib.import_module(tests_package_name)
    for imported_name, imported_module in vars(tests_package).items():
        if imported_name.startswith("test_") and isinstance(imported_module, ModuleType):
            # Odoo's loader discovers only test_* modules exported by this package.
            # Add a unique alias because many source addons use the same test filename.
            alias = f"test_{addon.name}_{imported_name.removeprefix('test_')}"
            globals()[alias] = imported_module
