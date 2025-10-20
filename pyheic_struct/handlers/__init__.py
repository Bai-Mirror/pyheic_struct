"""Vendor-specific handlers and registry utilities."""

from __future__ import annotations

from typing import Iterable, Type

from .apple_handler import AppleHandler
from .base_handler import VendorHandler
from .samsung_handler import SamsungHandler

HANDLER_REGISTRY: tuple[Type[VendorHandler], ...] = (
    SamsungHandler,
    AppleHandler,
)


def iter_handlers() -> Iterable[Type[VendorHandler]]:
    """Return every registered vendor handler class."""
    return HANDLER_REGISTRY


def get_handler_by_name(name: str) -> VendorHandler:
    """Instantiate a handler by its declared ``name`` attribute."""
    lowered = name.lower()
    for handler_cls in HANDLER_REGISTRY:
        if handler_cls.name == lowered:
            return handler_cls()
    raise ValueError(f"Unknown vendor handler: {name}")


def resolve_handler(heic_file) -> VendorHandler:
    """
    Auto-detect a handler based on file heuristics.

    Handlers are queried by ascending ``priority`` value.
    """
    for handler_cls in sorted(HANDLER_REGISTRY, key=lambda cls: cls.priority):
        if handler_cls.matches(heic_file):
            return handler_cls()
    return VendorHandler()


__all__ = [
    "AppleHandler",
    "SamsungHandler",
    "VendorHandler",
    "get_handler_by_name",
    "iter_handlers",
    "resolve_handler",
]
