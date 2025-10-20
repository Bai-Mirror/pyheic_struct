"""Target adapters for rebuilding HEIC/Motion Photo outputs."""

from .apple import AppleTargetAdapter
from .base import TargetAdapter

__all__ = ["AppleTargetAdapter", "TargetAdapter"]
