from __future__ import annotations

from typing import TYPE_CHECKING

from .base_handler import VendorHandler
from ..heic_types import ItemInfoEntryBox

if TYPE_CHECKING:
    from ..heic_file import HEICFile
    from ..targets.base import TargetAdapter


class SamsungHandler(VendorHandler):
    """Handles Samsung-specific HEIC features, like the embedded mpvd box."""

    name = "samsung"
    priority = 10

    @classmethod
    def matches(cls, heic_file: HEICFile) -> bool:
        brands = heic_file.get_compatible_brands()
        if any("samsung" in brand for brand in brands):
            return True
        # 三星 Motion Photo 通常包含 mpvd 盒
        if heic_file.find_box("mpvd"):
            return True
        return False

    def find_motion_photo_offset(self, heic_file: HEICFile) -> int | None:
        """
        Searches for the 'mpvd' box which contains the video data.
        """
        mpvd_box = heic_file.find_box("mpvd")
        if mpvd_box:
            print(f"Samsung 'mpvd' box found at offset {mpvd_box.offset}")
            # 视频数据在 8 字节头部之后开始
            return mpvd_box.offset + 8

        print("Samsung HEIC detected, but no 'mpvd' box found.")
        return None

    def prepare_flat_heic(
        self,
        original_heic: HEICFile,
        flat_heic: HEICFile,
        *,
        content_id: str,
        target_adapter: TargetAdapter,
    ) -> None:
        """
        修复三星特有的 shifted Item IDs、ipma/ipco/iref 引用等问题。
        """
        if not (flat_heic._iinf_box and flat_heic._iloc_box and flat_heic._iprp_box):
            return

        correct_ids = {loc.item_id for loc in flat_heic._iloc_box.locations}
        iinf_children_to_fix = [
            child
            for child in flat_heic._iinf_box.children
            if isinstance(child, ItemInfoEntryBox) and (child.item_id >> 16) in correct_ids
        ]

        shifted_id_map: dict[int, int] = {}

        if iinf_children_to_fix:
            print(f"  Found {len(iinf_children_to_fix)} shifted 'infe' boxes. Mapping IDs for reference...")
            for infe_box in iinf_children_to_fix:
                unshifted_id = infe_box.item_id >> 16
                if unshifted_id in correct_ids:
                    shifted_id_map[infe_box.item_id] = unshifted_id
                    print(f"  - Mapping 'infe' ID {infe_box.item_id} -> {unshifted_id}")
        else:
            print("  'infe' boxes seem correct. No shift detected.")

        if shifted_id_map and flat_heic._iprp_box.ipma:
            ipma_entries = flat_heic._iprp_box.ipma.entries
            keys_to_fix = [key for key in ipma_entries if key in shifted_id_map]

            if keys_to_fix:
                print(f"  Found {len(keys_to_fix)} shifted 'ipma' entries. Fixing them...")
                for shifted_key in keys_to_fix:
                    correct_key = shifted_id_map[shifted_key]
                    print(f"  - Fixing 'ipma' key {shifted_key} -> {correct_key}")
                    entry_data = ipma_entries.pop(shifted_key)
                    entry_data.item_id = correct_key
                    ipma_entries[correct_key] = entry_data
            else:
                print(f"  'ipma' entries seem correct. (Keys: {list(ipma_entries.keys())})")

        if shifted_id_map and flat_heic._iref_box:
            iref_refs = flat_heic._iref_box.references
            refs_fixed = 0
            for ref_type in list(iref_refs.keys()):
                keys_to_fix = [key for key in iref_refs[ref_type] if key in shifted_id_map]
                if keys_to_fix:
                    refs_fixed += len(keys_to_fix)
                    for shifted_key in keys_to_fix:
                        correct_key = shifted_id_map[shifted_key]
                        print(f"  - Fixing 'iref' key [{ref_type}] {shifted_key} -> {correct_key}")
                        iref_refs[ref_type][correct_key] = iref_refs[ref_type].pop(shifted_key)

            if refs_fixed > 0:
                print(f"  Fixed {refs_fixed} 'iref' entries.")
            else:
                print("  'iref' entries seem correct.")
