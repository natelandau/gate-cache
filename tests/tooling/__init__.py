"""Tooling test suite."""

from functools import cache
from importlib.util import module_from_spec, spec_from_file_location
from types import ModuleType

from tests.conftest import ROOT


def load_script(relative: str) -> ModuleType:
    """Import a repository file that is not in a package, such as duties.py or a script."""
    path = ROOT / relative
    spec = spec_from_file_location(path.stem, path)
    assert spec is not None
    assert spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@cache
def load_duties() -> ModuleType:
    """Import duties.py so the tests can read its suite paths."""
    return load_script("duties.py")
