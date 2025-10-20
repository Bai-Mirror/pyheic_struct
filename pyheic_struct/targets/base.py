from __future__ import annotations

from abc import ABC
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..heic_file import HEICFile


class TargetAdapter(ABC):
    """
    定义将 HEIC/Motion Photo 转换到目标生态所需的钩子。
    """

    name: str = "generic"

    def apply_to_flat_heic(self, flat_heic: HEICFile, content_id: str) -> None:
        """
        在最终写出前，针对目标生态对 HEIC 做品牌/元数据调整。
        """
        return None

    def post_process_mov(self, mov_path: Path, content_id: str, inject_content_id: bool) -> None:
        """
        针对导出的 MOV 文件执行额外处理（如写入 ContentIdentifier）。
        """
        return None
