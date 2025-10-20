"""Vendor-specific handlers used during HEIC parsing."""

from .apple_handler import AppleHandler
from .base_handler import VendorHandler
from .samsung_handler import SamsungHandler

__all__ = ["AppleHandler", "SamsungHandler", "VendorHandler"]
