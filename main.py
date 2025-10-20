# pyheic_struct/main.py
import os
import uuid
import subprocess
import pillow_heif  # <--- (1) 导入 pillow_heif 用于转码
from heic_file import HEICFile
from heic_types import ItemInfoEntryBox # <--- 添加这一行
from builder import HEICBuilder 
from handlers.base_handler import VendorHandler
from handlers.samsung_handler import SamsungHandler

def convert_samsung_to_apple(samsung_file_path: str):
    """
    (V17) 执行一个完整的两步转码：
    1.  [转码] 使用 pillow_heif 将三星的 "网格" 图像转码为一个 "扁平" 图像。
    2.  [注入] 使用我们的 HEICBuilder 将 UUID 和 *正确* 的 Apple ftyp 注入到这个新的扁平文件中。
    """
    if not os.path.exists(samsung_file_path):
        print(f"Error: File not found: {samsung_file_path}")
        return
        
    base_filename = os.path.splitext(samsung_file_path)[0]
    output_heic_path = f"{base_filename}_apple_compatible.HEIC"
    output_mov_path = f"{base_filename}_apple_compatible.MOV"
    temp_flat_heic_path = f"{base_filename}_temp_flat.HEIC" # <--- 临时文件

    print(f"--- Converting {samsung_file_path} to Apple format (V17 Fix) ---")
    
    # --- 步骤 1: 从原始三星文件中提取所有需要的数据 ---
    
    print(f"Loading original file: {samsung_file_path}")
    original_heic_file = HEICFile(samsung_file_path)

    # 1a. 提取视频数据
    video_data = original_heic_file.get_motion_photo_data()
    # (如果找不到，手动检查 mpvd)
    if not video_data:
        if not original_heic_file.handler or isinstance(original_heic_file.handler, VendorHandler):
            print("Vendor not auto-detected. Manually checking for Samsung 'mpvd' box...")
            mpvd_box = original_heic_file.find_box('mpvd')
            if mpvd_box:
                original_heic_file.handler = SamsungHandler()
                video_data = original_heic_file.get_motion_photo_data() # 再次尝试
    
    # 1b. 提取图像像素 (转码网格)
    print("Reconstructing grid image from Samsung file...")
    pil_image = original_heic_file.reconstruct_primary_image()
    if not pil_image:
        print("CRITICAL: Failed to reconstruct primary image using pillow_heif.")
        return
        
    # 1c. 生成 UUID
    new_content_id = str(uuid.uuid4()).upper()
    print(f"Generated ContentIdentifier: {new_content_id}")

    # --- 步骤 2: 处理 .MOV 文件 (这部分已经可以工作) ---
    if video_data:
        print(f"Saving extracted video data to {output_mov_path}...")
        with open(output_mov_path, 'wb') as f_mov:
            f_mov.write(video_data)
        
        try:
            print("Attempting to inject ContentIdentifier into .MOV file (requires exiftool)...")
            subprocess.run([
                'exiftool',
                f'-QuickTime:ContentIdentifier={new_content_id}',
                '-overwrite_original',
                output_mov_path
            ], check=True, capture_output=True, text=True)
            print("Successfully injected ContentIdentifier into .MOV.")
        except Exception as e:
            print(f"Warning: Could not inject ContentIdentifier into .MOV. ")
            print(f"  (This is normal if 'exiftool' is not installed.) Error: {e}")
    else:
        print("Info: No motion photo data found. Only a still HEIC will be created.")

    # --- 步骤 3: [转码] 创建一个临时的、扁平的 HEIC 文件 ---
    try:
        print(f"Saving temporary flat HEIC file to {temp_flat_heic_path}...")
        pillow_heif.register_heif_opener()
        
        # 将内存中的 PIL 图像保存为一个新的、扁平的 HEIC 文件
        pil_image.save(
            temp_flat_heic_path,
            format="HEIF",
            quality=95,
            save_as_brand="mif1" # 存为一个基础的 'mif1' 品牌
        )
        print("Successfully created temporary flat HEIC.")
        
    except Exception as e:
        print(f"CRITICAL: Failed to save temporary HEIC file: {e}")
        if os.path.exists(temp_flat_heic_path):
            os.remove(temp_flat_heic_path)
        return

    # --- 步骤 4: [注入] 加载扁平文件，并执行我们的元数据手术 ---
    try:
        print(f"Loading temporary flat HEIC for metadata injection...")
        flat_heic_file = HEICFile(temp_flat_heic_path)
        
        # 4a. (重要!) 修改 'ftyp' 盒以 *完全匹配* 苹果 Live Photo
        if flat_heic_file._ftyp_box:
            # --- START V15 FIX ---
            # 使用从 apple.HEIC 侦察日志中提取的 *正确* 字符串
            # 它包含了我们缺失的 'MiHB' 品牌
            print("Modifying 'ftyp' box to be Apple compatible (heic, MiHB, MiHE...)...")
            apple_ftyp_raw_data = b'heic\x00\x00\x00\x00mif1MiHBMiHEMiPrmiafheictmap'
            flat_heic_file._ftyp_box.raw_data = apple_ftyp_raw_data
            flat_heic_file._ftyp_box.size = len(apple_ftyp_raw_data) + 8 # (40 + 8 = 48)
            # --- END V15 FIX ---
        else:
            print("Error: Temporary HEIC file has no 'ftyp' box. Aborting.")
            os.remove(temp_flat_heic_path)
            return
        
        # 4b. (V12 / V17 FIX) 纠正 pillow_heif 产生的 'shifted' ID
        print("Checking for shifted IDs in temporary file (V17 Full Fix)...")
        if flat_heic_file._iinf_box and flat_heic_file._iloc_box and flat_heic_file._iprp_box:
            
            # 1. 找出 iloc 中的 "正确" ID (e.g., {1, 2, 3, 4})
            # (我们假设 iloc 是正确的，因为 pillow-heif 似乎只搞错了其他盒)
            correct_ids = {loc.item_id for loc in flat_heic_file._iloc_box.locations}
            
            # 2. 修复 'iinf' (infe boxes)
            iinf_children_to_fix = [
                c for c in flat_heic_file._iinf_box.children 
                if isinstance(c, ItemInfoEntryBox) and (c.item_id >> 16) in correct_ids
            ]
            
            # 我们需要建立一个映射表, e.g., {65536: 1}
            shifted_id_map = {} 

            if iinf_children_to_fix:
                print(f"  Found {len(iinf_children_to_fix)} shifted 'infe' boxes. Fixing them...")
                for infe_box in iinf_children_to_fix:
                    unshifted_id = infe_box.item_id >> 16
                    # 检查 unshifted_id 是否真的在 correct_ids 中，以防万一
                    if unshifted_id in correct_ids:
                        shifted_id_map[infe_box.item_id] = unshifted_id # 存映射
                        print(f"  - Fixing 'infe' ID {infe_box.item_id} -> {unshifted_id}")
                        infe_box.item_id = unshifted_id
                    
                # 同时修复 iinf_box.entries 中的缓存
                for entry in flat_heic_file._iinf_box.entries:
                    if entry.item_id in shifted_id_map:
                        entry.item_id = shifted_id_map[entry.item_id]
            else:
                 print("  'infe' boxes seem correct. No shift detected.")

            # --- START V17 FIX ---

            # 3. 修复 'ipma' (属性)
            if flat_heic_file._iprp_box.ipma:
                ipma_entries = flat_heic_file._iprp_box.ipma.entries
                # 找出所有 "shifted" 的字典键
                keys_to_fix = [k for k in ipma_entries if k in shifted_id_map]
                
                if keys_to_fix:
                    print(f"  Found {len(keys_to_fix)} shifted 'ipma' entries. Fixing them...")
                    for shifted_key in keys_to_fix:
                        correct_key = shifted_id_map[shifted_key]
                        print(f"  - Fixing 'ipma' key {shifted_key} -> {correct_key}")
                        
                        # 替换字典的键 (e.g., {65536: ...} -> {1: ...})
                        entry_data = ipma_entries.pop(shifted_key) 
                        entry_data.item_id = correct_key # 确保条目内部的 ID 也被更新
                        ipma_entries[correct_key] = entry_data
                else:
                    print(f"  'ipma' entries seem correct. (Keys: {list(ipma_entries.keys())})")
            
            # 4. 修复 'iref' (引用)
            if flat_heic_file._iref_box:
                iref_refs = flat_heic_file._iref_box.references
                refs_fixed = 0
                for ref_type in iref_refs: # e.g., 'thmb', 'dimg'
                    # 找出所有 "shifted" 的字典键
                    keys_to_fix = [k for k in iref_refs[ref_type] if k in shifted_id_map]
                    if keys_to_fix:
                        refs_fixed += len(keys_to_fix)
                        for shifted_key in keys_to_fix:
                            correct_key = shifted_id_map[shifted_key]
                            print(f"  - Fixing 'iref' key [{ref_type}] {shifted_key} -> {correct_key}")
                            # 替换字典的键
                            iref_refs[ref_type][correct_key] = iref_refs[ref_type].pop(shifted_key)
                
                if refs_fixed > 0:
                    print(f"  Fixed {refs_fixed} 'iref' entries.")
                else:
                    print("  'iref' entries seem correct.")
            
            # --- END V17 FIX ---
            
        # 4c. 注入 ContentIdentifier (UUID)
        if flat_heic_file.set_content_identifier(new_content_id):
            print(f"Successfully set ContentIdentifier in flat HEIC.")
        else:
            print("Error: Failed to set ContentIdentifier in flat HEIC.")
            os.remove(temp_flat_heic_path)
            return

        # 4d. (V13 FIX) 移除与 Apple 结构冲突的项
        # (保持注释状态，因为这可能是导致损坏的原因，或者 V17 已使其不再必要)
        # items_to_remove = [2, 3, 4] 
        # print(f"Applying V13 Fix: Removing conflicting items {items_to_remove}...")
        # for item_id in items_to_remove:
        #     flat_heic_file.remove_item_by_id(item_id)

        # 4e. [构建] 使用我们的 HEICBuilder 重建这个*扁平*文件
        print("Rebuilding flat HEIC with new metadata...")
        builder = HEICBuilder(flat_heic_file)
        builder.write(output_heic_path)

    except Exception as e:
        print(f"CRITICAL: HEICBuilder failed during final rebuild: {e}")
    finally:
        # 5. 清理
        if os.path.exists(temp_flat_heic_path):
            os.remove(temp_flat_heic_path)
            print(f"Cleaned up temporary file: {temp_flat_heic_path}")
            
    print(f"--- Conversion complete ---")
    print(f"New HEIC: {output_heic_path}")
    if video_data:
        print(f"New MOV:  {output_mov_path}") # <-- 修复了一个小的打印错误，使其指向 .MOV
    print("\n" + "="*40 + "\n")

def main():
    samsung_file = 'samsung.heic'
    convert_samsung_to_apple(samsung_file)

if __name__ == "__main__":
    main()