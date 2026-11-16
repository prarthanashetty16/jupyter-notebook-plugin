"""
NEXUS: Predict peak RAM and wall-clock time for Jupyter cells before execution.

An IPython extension and Python package for research-backed performance prediction.
Load with ``%load_ext nexus``.
"""

__version__ = "0.1.0.dev0"

from nexus.extension import load_ipython_extension, unload_ipython_extension

__all__ = ["__version__", "load_ipython_extension", "unload_ipython_extension"]
