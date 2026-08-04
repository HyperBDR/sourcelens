"""Compatibility facade for the LensNode agent runtime package."""

import sys
from types import ModuleType

from . import runtime as _runtime


class _RuntimeFacade(ModuleType):
    """Keep package-level monkeypatches visible to the runtime module."""

    def __setattr__(self, name, value):
        """Update runtime symbols when callers patch the legacy facade."""

        super().__setattr__(name, value)
        if name in vars(_runtime):
            setattr(_runtime, name, value)


for _name, _value in vars(_runtime).items():
    if not _name.startswith("__"):
        globals()[_name] = _value

sys.modules[__name__].__class__ = _RuntimeFacade
