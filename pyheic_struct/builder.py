# pyheic_struct/builder.py

import struct
from .heic_file import HEICFile
from .heic_types import ItemLocationBox

class HEICBuilder:
    def __init__(self, heic_file: HEICFile):
        self.heic_file = heic_file
        self.mdat_box = heic_file.get_mdat_box()
        self.meta_box = heic_file.find_box('meta')
        self.iloc_box = heic_file._iloc_box
        
        if not self.mdat_box:
            raise ValueError("Cannot build: 'mdat' box not found.")
        if not self.meta_box:
            raise ValueError("Cannot build: 'meta' box not found.")
        if not self.iloc_box:
            raise ValueError("Cannot build: 'iloc' box not found.")
            
        # 存储 'mdat' 的 *原始* 偏移量。这是至关重要的。
        self.original_mdat_offset = self.mdat_box.offset
        
        # 分离元数据和数据
        self.top_level_meta_boxes = [b for b in self.heic_file.boxes if b.type != 'mdat']

    def _calculate_meta_offset_delta(self) -> int:
        """(V14) 辅助函数：计算 'meta' 盒的偏移增量"""
        ftyp_box = self.heic_file._ftyp_box
        if not ftyp_box:
            ftyp_box = next((b for b in self.top_level_meta_boxes if b.type == 'ftyp'), None)
        
        new_meta_offset = ftyp_box.size if ftyp_box else 0 
        original_meta_offset = self.meta_box.offset
        return new_meta_offset - original_meta_offset

    def _rebuild_iloc_with_delta(self, mdat_offset_delta: int):
        """(V14) 辅助函数：使用给定的 delta 重建 iloc"""
        print(f"  ... Rebuilding 'iloc' using mdat_delta: {mdat_offset_delta}")
        meta_offset_delta = self._calculate_meta_offset_delta()
        try:
            self.iloc_box.rebuild_iloc_content(
                mdat_offset_delta=mdat_offset_delta,
                original_mdat_offset=self.original_mdat_offset,
                original_mdat_size=self.mdat_box.size,
                meta_offset_delta=meta_offset_delta,
                original_meta_offset=self.meta_box.offset,
                original_meta_size=self.meta_box.size
            )
        except Exception as e:
            print(f"CRITICAL: Failed to rebuild 'iloc' box content: {e}")
            raise # 抛出异常以停止构建

    def _calculate_final_meta_size(self) -> int:
        """(V14) 辅助函数：递归构建所有元数据盒以获取其最终大小"""
        current_offset = 0
        for box in self.top_level_meta_boxes:
            # build_box() 会递归计算所有子盒的最终大小
            final_box_data = box.build_box()
            current_offset += len(final_box_data)
        return current_offset

    def write(self, output_path: str):
        """
        (V14) 使用一个多遍系统来解决 'iloc' 重建引起的循环依赖问题。
        """
        
        # --- Pass 1: 初步布局计算 ---
        # (在 'iloc' 重建 *之前* 计算一次大小)
        print("--- Builder Pass 1: Preliminary Layout ---")
        preliminary_meta_size = self._calculate_final_meta_size()
        preliminary_mdat_offset = preliminary_meta_size
        preliminary_mdat_delta = preliminary_mdat_offset - self.original_mdat_offset
        
        print(f"Original mdat offset: {self.original_mdat_offset}")
        print(f"Preliminary mdat offset: {preliminary_mdat_offset}")
        print(f"Preliminary offset delta: {preliminary_mdat_delta}")

        # --- Pass 2: 初步重建 'iloc' ---
        # (使用 *初步的* delta 重建 iloc，这会改变 'iloc' 的大小)
        print("\n--- Builder Pass 2: Preliminary 'iloc' Rebuild ---")
        self._rebuild_iloc_with_delta(preliminary_mdat_delta)
        print(" 'iloc' preliminary rebuild complete.")

        # --- Pass 3: 最终布局计算 ---
        # (现在 'iloc' 有了最终大小，我们 *再次* 计算 meta 的总大小)
        print("\n--- Builder Pass 3: Final Layout Calculation ---")
        final_meta_size = self._calculate_final_meta_size()
        final_mdat_offset = final_meta_size
        final_mdat_delta = final_mdat_offset - self.original_mdat_offset

        print(f"Final meta size (actual): {final_meta_size}")
        print(f"Final mdat offset (actual): {final_mdat_offset}")
        print(f"Final offset delta (actual): {final_mdat_delta}")

        # --- Pass 4: 最终重建 'iloc' ---
        # (使用 *最终的、正确*的 delta 再次重建 iloc)
        if final_mdat_delta != preliminary_mdat_delta:
            print("\n--- Builder Pass 4: Final 'iloc' Rebuild (Correcting Delta) ---")
            self._rebuild_iloc_with_delta(final_mdat_delta)
            print(" 'iloc' final rebuild complete.")
        else:
            print("\n--- Builder Pass 4: Skipped (Preliminary delta was correct) ---")

        # --- Pass 5: 写入文件 ---
        print("\n--- Builder Pass 5: Rebuild & Write ---")
        
        # 只有在 'iloc' 重建成功后，我们才打开（并创建）输出文件
        with open(output_path, 'wb') as f:
            
            current_offset = 0
            for box in self.top_level_meta_boxes:
                final_box_data = box.build_box()
                f.write(final_box_data)
                current_offset += len(final_box_data)
                print(f"Wrote '{box.type}' (final size: {len(final_box_data)})")
            
            # 完整性检查
            if current_offset != final_mdat_offset:
                print(f"WARNING: Final meta size ({current_offset}) does not match"
                      f" calculated mdat offset ({final_mdat_offset})!")

            # 写入 'mdat' 盒 (头部 + 数据)
            mdat_data = self.mdat_box.raw_data
            mdat_size = 8 + len(mdat_data) # 8-byte header
            
            print(f"Writing 'mdat' (final size: {mdat_size}) at offset {current_offset}...")
            
            if mdat_size > 4294967295:
                f.write(struct.pack('>I', 1))
                f.write(b'mdat')
                f.write(struct.pack('>Q', mdat_size))
            else:
                f.write(struct.pack('>I', mdat_size))
                f.write(b'mdat')
            
            f.write(mdat_data)

        print(f"\nSuccessfully rebuilt file at: {output_path}")
