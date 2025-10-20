from __future__ import annotations

from abc import ABC
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from ..heic_file import HEICFile
    from ..targets.base import TargetAdapter


class VendorHandler(ABC):
    """
    Base class for vendor-specific Motion Photo 适配逻辑。

    设计理念：
    - `matches` 用于自动检测厂商；
    - `extract_motion_video` 负责读取嵌入式视频；
    - `prepare_flat_heic` 提供对中间平面 HEIC 的修复机会；
    - 其余钩子可在必要时扩展。
    """

    #: 供配置或日志使用的处理器名称。
    name: str = "generic"

    #: 自动检测时的优先级（值越小越优先）。
    priority: int = 100

    @classmethod
    def matches(cls, heic_file: HEICFile) -> bool:
        """
        判断当前 handler 是否适用于给定 HEIC 文件。

        子类应实现轻量级检测逻辑（如检查 `ftyp` 品牌、特定 Box）。
        """
        return False

    def find_motion_photo_offset(self, heic_file: HEICFile) -> int | None:
        """
        返回嵌入式 Motion Photo 视频数据的偏移量。
        默认实现返回 None，表明不存在嵌入视频。
        """
        return None

    def extract_motion_video(self, heic_file: HEICFile) -> Optional[bytes]:
        """
        读取嵌入式视频数据。若无法定位则返回 None。
        """
        offset = self.find_motion_photo_offset(heic_file)
        if offset is None:
            return None

        with open(heic_file.filepath, "rb") as file_obj:
            file_obj.seek(offset)
            return file_obj.read()

    def reconstruct_primary_image(self, heic_file: HEICFile):
        """
        还原主图像。默认委托给 `HEICFile.reconstruct_primary_image`。
        """
        return heic_file.reconstruct_primary_image()

    def prepare_flat_heic(
        self,
        original_heic: HEICFile,
        flat_heic: HEICFile,
        *,
        content_id: str,
        target_adapter: TargetAdapter,
    ) -> None:
        """
        针对厂商特有结构（如偏移表、Shifted IDs）进行修复或补丁。
        默认实现为空操作。
        """
        return None

    def supports_target(self, target_adapter: TargetAdapter) -> bool:
        """
        用于声明 Handler 是否支持目标适配器。默认支持所有目标。
        """
        return True
