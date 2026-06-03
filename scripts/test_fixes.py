"""
测试脚本：验证 code review 中发现的 bug 修复情况。

验证项目：
  Bug 1: remove_item_by_id 偏移量修正
  Bug 2: 同类型 iref 子 box 不再覆盖
  Bug 4: if→elif（无运行时影响，语法改进）
  Bug 5: get_grid_layout 冗余查找消除
  Bug 6: get_thumbnail_data 双次扫描合并
"""
import sys
import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from pyheic_struct import HEICFile

EXAMPLE_DIR = ROOT_DIR / "examples"

HEIC_FILES = [
    "apple.HEIC",
    "apple_samsung_compatible.heic",
    "samsung.heic",
    "samsung_apple_compatible.HEIC",
]

def separator(title: str):
    print(f"\n{'─' * 60}\n  {title}\n{'─' * 60}")


def test_parse_and_references(filepath: str) -> dict:
    """测试解析并检查 references 字典 (验证 Bug 2: setdefault)"""
    print(f"\n  [Bug 2 验证] 解析 references 字典...")
    heic = HEICFile(filepath)

    primary_id = heic.get_primary_item_id()
    print(f"  主图像 ID: {primary_id}")

    if not heic._iref_box:
        print("  ⚠ 无 iref box，跳过 references 检查")
        return {"primary_id": primary_id}

    refs = heic._iref_box.references
    print(f"  引用类型: {list(refs.keys())}")

    for ref_type, entries in refs.items():
        print(f"  [{ref_type}] 条目数: {len(entries)}")
        for from_id, to_ids in entries.items():
            print(f"    from_id={from_id} → to_ids={to_ids}")
        # Bug 2 验证：如果同类型有多个条目，说明 setdefault 生效
        if len(entries) > 1:
            print(f"    ✅ 同类型多条目已完整保留 (setdefault 生效)")
        elif len(entries) == 1:
            print(f"    ℹ 该类型仅有 1 个条目 (无法区分修复前后)")
        else:
            print(f"    ⚠ 该类型无条目")

    result = {"primary_id": primary_id}

    # 记录 thmb/dimg 用于后续测试
    if 'thmb' in refs:
        first_thmb = next(iter(refs['thmb'].items()), None)
        if first_thmb:
            result['thmb_from_id'] = first_thmb[0]
            result['thmb_to_ids'] = first_thmb[1]
    if 'dimg' in refs:
        first_dimg = next(iter(refs['dimg'].items()), None)
        if first_dimg:
            result['dimg_from_id'] = first_dimg[0]
            result['dimg_to_ids'] = first_dimg[1]

    return result


def test_thumbnail(filepath: str) -> bool:
    """测试缩略图提取 (验证 Bug 4/6: elif 和合并条件)"""
    print(f"\n  [Bug 4/6 验证] 提取缩略图...")
    heic = HEICFile(filepath)
    data = heic.get_thumbnail_data()
    if data:
        print(f"  ✅ 缩略图提取成功: {len(data)} bytes")
        return True
    else:
        print(f"  ℹ 无缩略图 (文件可能不含 thmb 引用)")
        return False


def test_grid_layout(filepath: str) -> bool:
    """测试网格布局 (验证 Bug 5: 冗余字典查找消除)"""
    print(f"\n  [Bug 5 验证] 获取网格布局...")
    heic = HEICFile(filepath)
    tiles = heic.get_grid_layout()
    if tiles:
        print(f"  ✅ 网格图块: {tiles} (共 {len(tiles)} 个)")
        return True
    else:
        print(f"  ℹ 无网格布局 (文件非网格图像)")
        return False


def test_remove_item(filepath: str, refs_info: dict):
    """测试 remove_item_by_id (验证 Bug 1: 偏移量修正)"""
    print(f"\n  [Bug 1 验证] remove_item_by_id...")

    # 选一个可删除的非主 item
    target_id = refs_info.get('thmb_from_id')
    if not target_id:
        target_id = refs_info.get('dimg_from_id')
    if not target_id:
        # 尝试从 references 中找一个
        print("  ℹ 没有合适的非主 item 可删除，跳过 Bug 1 验证")
        return

    print(f"  将删除 item ID: {target_id}")

    # 删除前：重新解析文件，记录状态
    heic = HEICFile(filepath)
    irig_box = heic._iref_box
    if not irig_box:
        print("  ⚠ 无 iref box，跳过")
        return

    children_before = len(irig_box.children)
    refs_keys_before = {}
    for rt, entries in irig_box.references.items():
        refs_keys_before[rt] = set(entries.keys())

    print(f"  删除前: children={children_before}, references keys={refs_keys_before}")

    # 执行删除
    heic.remove_item_by_id(target_id)

    # 删除后：验证
    children_after = len(irig_box.children)
    refs_keys_after = {}
    for rt, entries in irig_box.references.items():
        refs_keys_after[rt] = set(entries.keys())

    print(f"  删除后: children={children_after}, references keys={refs_keys_after}")

    # Bug 1 验证：from_id 为 target_id 的子 box 是否被正确移除
    if target_id in refs_keys_before.get('thmb', set()) or target_id in refs_keys_before.get('dimg', set()):
        found_in_key = any(target_id in keys for keys in refs_keys_after.values())
        if not found_in_key:
            print(f"  ✅ item {target_id} 已从 references 键中移除")
            # children 应该也减少了
            if children_after < children_before:
                print(f"  ✅ children 列表同步减少 (Bug 1 偏移量修正生效)")
            else:
                print(f"  ⚠ children 未减少 — 可能 child 未从 children 中移除")
        else:
            print(f"  ❌ item {target_id} 仍在 references 中")
    elif target_id in refs_info.get('thmb_to_ids', []):
        to_cleaned = True
        for rt, entries in irig_box.references.items():
            for fid, tids in entries.items():
                if target_id in tids:
                    to_cleaned = False
                    break
        if to_cleaned:
            print(f"  ✅ to_id {target_id} 已从所有引用列表中清理")
        else:
            print(f"  ❌ to_id {target_id} 仍在引用列表中")
    else:
        print(f"  ℹ 无法判定移除效果（target_id 不在已知引用中）")


def main():
    print("=" * 70)
    print("  pyheic_struct Code Review Bug 修复验证")
    print("=" * 70)

    results = {}
    for filename in HEIC_FILES:
        filepath = str(EXAMPLE_DIR / filename)
        if not os.path.exists(filepath):
            print(f"\n⚠ SKIP: {filename} (文件不存在)")
            continue

        separator(f"测试: {filename} ({os.path.getsize(filepath):,} bytes)")
        try:
            refs_info = test_parse_and_references(filepath)
            ok_thumb = test_thumbnail(filepath)
            ok_grid = test_grid_layout(filepath)
            test_remove_item(filepath, refs_info)

            results[filename] = {
                "refs": refs_info,
                "thumbnail": ok_thumb,
                "grid": ok_grid,
            }
        except Exception as e:
            print(f"\n  ❌ 测试失败: {e}")
            import traceback
            traceback.print_exc()
            results[filename] = {"error": str(e)}

    # 汇总
    separator("测试汇总")
    print(f"\n  {'文件':<40} {'解析':<8} {'缩略图':<8} {'网格':<8}")
    print(f"  {'─' * 40} {'─' * 8} {'─' * 8} {'─' * 8}")
    for filename, info in results.items():
        if "error" in info:
            print(f"  {filename:<40} {'❌ 失败':<8} {'-':<8} {'-':<8}")
            continue
        refs_ok = "✅" if info["refs"].get("primary_id") else "⚠"
        thumb_ok = "✅" if info["thumbnail"] else "—"
        grid_ok = "✅" if info["grid"] else "—"
        print(f"  {filename:<40} {refs_ok:<8} {thumb_ok:<8} {grid_ok:<8}")

    print(f"\n  ✅ 测试完成。")
    print(f"  Bug 1 (remove_item_by_id 偏移量): 需查看具体文件日志")
    print(f"  Bug 2 (setdefault 覆盖): 查看多条目引用类型条目数")
    print(f"  Bug 4/6 (elif/合并条件): 缩略图提取成功即验证通过")
    print(f"  Bug 5 (冗余查找): 网格布局成功即验证通过")


if __name__ == "__main__":
    main()
