"""Load the Loam API module directly so tests don't need Home Assistant installed."""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys

API_PATH = Path(__file__).parents[1] / "custom_components" / "loam" / "api.py"


def _load_api_module():
    spec = spec_from_file_location("loam_api", API_PATH)
    module = module_from_spec(spec)
    sys.modules["loam_api"] = module
    spec.loader.exec_module(module)
    return module


_load_api_module()
