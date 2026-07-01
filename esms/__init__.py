"""EsMS package."""

from importlib.metadata import version, PackageNotFoundError

from .models import Battery
from .optimization import EnergyOptimizer, StochasticEnergyOptimizer
from .utils import SUGGESTED_SOLVERS, get_available_pyomo_solvers, build_batteries

try:
    __version__ = "0.3.0"
except PackageNotFoundError:
    __version__ = "dev"  # Fallback for development

__all__ = [
    "Battery",
    "EnergyOptimizer",
    "StochasticEnergyOptimizer",
    "SUGGESTED_SOLVERS",
    "get_available_pyomo_solvers",
    "build_batteries",
    "__version__",
]
