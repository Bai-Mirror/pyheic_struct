"""Utilities for parsing and rebuilding HEIC/HEIF structures."""

from importlib import metadata

from .builder import HEICBuilder
from .converter import convert_samsung_motion_photo
from .heic_file import HEICFile
from .heic_types import ItemInfoEntryBox, ItemInfoBox, ItemLocationBox

try:  # pragma: no cover - best effort metadata
    __version__ = metadata.version("pyheic-struct")
except metadata.PackageNotFoundError:  # pragma: no cover - local checkout
    __version__ = "0.0.0"

__all__ = [
    "convert_samsung_motion_photo",
    "HEICBuilder",
    "HEICFile",
    "ItemInfoBox",
    "ItemInfoEntryBox",
    "ItemLocationBox",
    "__version__",
]
