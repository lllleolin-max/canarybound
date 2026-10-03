"""Conservative delayed binary outcome evidence; see docs/MATH.md."""
from .core import (CanaryBoundError, Manifest, Status, analyze, fingerprint,
                   make_manifest, stream_bounds)

__all__ = ["CanaryBoundError", "Manifest", "Status", "analyze", "fingerprint",
           "make_manifest", "stream_bounds"]
__version__ = "0.1.0"
