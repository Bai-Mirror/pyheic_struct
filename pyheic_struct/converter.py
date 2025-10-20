"""High-level conversion helpers for Motion Photos."""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Optional, Union

import pillow_heif

from .builder import HEICBuilder
from .handlers import VendorHandler, get_handler_by_name, resolve_handler
from .heic_file import HEICFile
from .targets import AppleTargetAdapter, TargetAdapter


HandlerHint = Union[str, VendorHandler, None]


def _select_handler(
    heic_file: HEICFile,
    vendor_hint: HandlerHint,
    target_adapter: TargetAdapter,
) -> VendorHandler:
    """Resolve the vendor handler to operate on this file."""
    handler: VendorHandler

    if isinstance(vendor_hint, VendorHandler):
        handler = vendor_hint
    elif isinstance(vendor_hint, str):
        if vendor_hint.lower() == "auto":
            handler = heic_file.handler or resolve_handler(heic_file)
        else:
            handler = get_handler_by_name(vendor_hint)
    else:
        handler = heic_file.handler or resolve_handler(heic_file)

    if not handler.__class__.matches(heic_file):
        print(
            f"Warning: Handler '{handler.name}' did not positively match heuristics for this file. "
            "Proceeding anyway."
        )

    if not handler.supports_target(target_adapter):
        raise ValueError(
            f"Handler '{handler.name}' does not support target '{target_adapter.name}'."
        )

    heic_file.handler = handler
    return handler


def convert_motion_photo(
    source: str | os.PathLike,
    *,
    vendor_hint: HandlerHint = None,
    target_adapter: TargetAdapter | None = None,
    output_still: Optional[str | os.PathLike] = None,
    output_video: Optional[str | os.PathLike] = None,
    inject_content_id_into_mov: bool = True,
) -> tuple[Path, Optional[Path]]:
    """
    Convert a Motion Photo HEIC into a target-compatible HEIC(+MOV) 组合。

    Parameters
    ----------
    source:
        输入 HEIC 文件路径。
    vendor_hint:
        可选的厂商提示，支持 handler 名称（如 ``"samsung"``）、``VendorHandler`` 实例
        或 ``"auto"``（默认行为）。
    target_adapter:
        目标生态适配器。默认使用 :class:`AppleTargetAdapter`。
    output_still:
        可选的输出 HEIC 路径，默认 ``<source>_apple_compatible.HEIC``。
    output_video:
        可选的输出 MOV 路径，默认 ``<source>_apple_compatible.MOV``。
    inject_content_id_into_mov:
        是否在 MOV 文件中写入 ``ContentIdentifier``。

    Returns
    -------
    (Path, Optional[Path])
        返回生成的 HEIC 路径以及 MOV 路径（若生成）。
    """

    target_adapter = target_adapter or AppleTargetAdapter()

    source_path = Path(source)
    if not source_path.is_file():
        raise FileNotFoundError(f"HEIC file not found: {source_path}")

    base = source_path.with_suffix("")
    heic_path = Path(output_still) if output_still else Path(f"{base}_apple_compatible.HEIC")
    mov_output_path = Path(output_video) if output_video else Path(f"{base}_apple_compatible.MOV")
    temp_flat_path = Path(f"{base}_temp_flat.HEIC")

    print(f"--- Converting {source_path.name} using target '{target_adapter.name}' ---")

    original_heic_file = HEICFile(str(source_path))
    handler = _select_handler(original_heic_file, vendor_hint, target_adapter)

    print(f"Detected handler: {handler.name}")

    video_data = handler.extract_motion_video(original_heic_file)
    if video_data:
        print("Embedded motion photo data detected.")
    else:
        print("No embedded motion photo data found via handler.")

    print("Reconstructing primary image using vendor handler...")
    pil_image = handler.reconstruct_primary_image(original_heic_file)
    if pil_image is None:
        raise RuntimeError("Failed to reconstruct primary image using pillow-heif.")

    new_content_id = str(uuid.uuid4()).upper()
    print(f"Generated ContentIdentifier: {new_content_id}")

    mov_path: Optional[Path]
    if video_data:
        print(f"Saving extracted video data to {mov_output_path}...")
        mov_output_path.write_bytes(video_data)
        target_adapter.post_process_mov(
            mov_output_path,
            new_content_id,
            inject_content_id_into_mov,
        )
        mov_path = mov_output_path
    else:
        mov_path = None
        print("Info: No motion photo data will be exported as MOV.")

    try:
        print(f"Saving temporary flat HEIC file to {temp_flat_path}...")
        pillow_heif.register_heif_opener()
        pil_image.save(
            temp_flat_path,
            format="HEIF",
            quality=95,
            save_as_brand="mif1",
        )
        print("Successfully created temporary flat HEIC.")
    except Exception as exc:
        if temp_flat_path.exists():
            temp_flat_path.unlink()
        raise RuntimeError(f"Failed to save temporary HEIC file: {exc}") from exc

    try:
        print("Loading temporary flat HEIC for metadata transformation...")
        flat_heic_file = HEICFile(str(temp_flat_path))

        handler.prepare_flat_heic(
            original_heic=original_heic_file,
            flat_heic=flat_heic_file,
            content_id=new_content_id,
            target_adapter=target_adapter,
        )

        target_adapter.apply_to_flat_heic(flat_heic_file, new_content_id)

        print("Rebuilding flat HEIC with new metadata...")
        builder = HEICBuilder(flat_heic_file)
        builder.write(str(heic_path))

    finally:
        if temp_flat_path.exists():
            temp_flat_path.unlink()
            print(f"Cleaned up temporary file: {temp_flat_path}")

    print("--- Conversion complete ---")
    print(f"New HEIC: {heic_path}")
    if mov_path:
        print(f"New MOV:  {mov_path}")
    print("\n" + "=" * 40 + "\n")

    return heic_path, mov_path


def convert_samsung_motion_photo(
    source: str | os.PathLike,
    *,
    output_still: Optional[str | os.PathLike] = None,
    output_video: Optional[str | os.PathLike] = None,
    inject_content_id_into_mov: bool = True,
) -> tuple[Path, Optional[Path]]:
    """
    Backwards-compatible Samsung 转换入口，等价于 `vendor_hint="samsung"`。
    """
    return convert_motion_photo(
        source,
        vendor_hint="samsung",
        output_still=output_still,
        output_video=output_video,
        inject_content_id_into_mov=inject_content_id_into_mov,
    )
