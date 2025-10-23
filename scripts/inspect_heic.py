# pyheic_struct/inspect_heic.py

import sys
import pprint # 用于漂亮地打印字典

from pyheic_struct import HEICFile

def inspect_file(filename: str):
    print(f"--- 正在侦察: {filename} ---")
    
    try:
        heic_file = HEICFile(filename)
    except Exception as e:
        print(f"CRITICAL: 文件解析失败: {e}")
        return

    # 1. 打印厂商信息 (ftyp)
    if heic_file._ftyp_box:
        print(f"\n[ftyp] 厂商信息:")
        print(f"  {heic_file._ftyp_box.raw_data}")
    
    # 2. 打印主图像 ID (pitm)
    primary_id = heic_file.get_primary_item_id()
    print(f"\n[pitm] 主图像 Item ID:")
    print(f"  {primary_id}")

    # 3. 打印所有项目 (iinf)
    print(f"\n[iinf] 文件中的所有项目:")
    heic_file.list_items() # 这个方法会自己打印

    # 4. 打印项目位置 (iloc) - 这是我们调试的关键！ (已修改)
    if heic_file._iloc_box:
        print(f"\n[iloc] 项目位置 (片段) - 包含绝对偏移量:")
        locations = heic_file._iloc_box.locations
        
        # 打印所有位置及其详细的 extents
        for loc in locations:
            # 打印摘要
            print(f"  {loc}") 
            # 打印关键的 extents (偏移量, 长度)
            if loc.extents:
                for extent in loc.extents:
                    print(f"    -> (offset={extent[0]}, length={extent[1]})")
            else:
                print("    -> (No extents found)")
    
    # 5. 打印项目关联 (iref)
    if heic_file._iref_box:
        print(f"\n[iref] 项目关联:")
        pprint.pprint(heic_file._iref_box.references)

    # 6. 查找 'mpvd' 盒 (三星特定)
    mpvd_box = heic_file.find_box('mpvd') #
    if mpvd_box:
        print(f"\n[mpvd] 动态照片盒 (三星):")
        print(f"  找到了 'mpvd' 盒，位于偏移量: {mpvd_box.offset}")
    else:
        print(f"\n[mpvd] 未找到 'mpvd' 盒 (这是 Apple 文件的预期行为)")

    # --- START NEW INSPECTION ---
    # 7. 打印项目属性 (iprp / ipma) - 这是我们缺失的知识！
    if heic_file._iprp_box and heic_file._iprp_box.ipma:
        print(f"\n[ipma] 项目属性关联:")
        
        ipma = heic_file._iprp_box.ipma
        
        # 打印主 ID 的属性
        if primary_id and primary_id in ipma.entries:
            print(f"  主 ID ({primary_id}) 关联的属性索引:")
            pprint.pprint(ipma.entries[primary_id].associations)
        
        # 尝试打印 "shifted" ID (三星)
        if primary_id:
            shifted_id = primary_id << 16
            if shifted_id in ipma.entries:
                print(f"  三星 Shifted ID ({shifted_id}) 关联的属性索引:")
                pprint.pprint(ipma.entries[shifted_id].associations)
        
        print(f"\n  (ipma 完整转储 - 前 5 项):")
        count = 0
        for item_id, entry in ipma.entries.items():
            if count >= 5:
                print("  ...")
                break
            print(f"  - Item {item_id}: {entry.associations}")
            count += 1
    else:
        print(f"\n[ipma] 未找到 'ipma' 盒。")
        
    if heic_file._iprp_box and heic_file._iprp_box.ipco:
        print(f"\n[ipco] 属性容器 (前 10 个属性盒):")
        count = 0
        for prop_box in heic_file._iprp_box.ipco.children:
            if count >= 10:
                print("  ...")
                break
            print(f"  - (索引 {count+1}) : {prop_box}") # 索引是 1-based
            count += 1
    else:
        print(f"\n[ipco] 未找到 'ipco' 盒。")
    # --- END NEW INSPECTION ---

    print(f"\n--- 侦察完毕: {filename} ---")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python scripts/inspect_heic.py <文件名>")
        print("例如: python scripts/inspect_heic.py examples/samsung.heic")
    else:
        inspect_file(sys.argv[1])
