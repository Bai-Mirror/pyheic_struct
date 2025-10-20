# pyheic-struct

`pyheic-struct` 是一个用于解析、分析以及重建 HEIC/HEIF 文件的 Python 库，专注于不同厂商（如三星、苹果）在实现上的差异。项目同时提供命令行工具与可复用的 API，可嵌入其他项目，帮助你处理跨平台的动态照片与静态 HEIC 内容。

## 功能特点

- **HEIC 结构解析**：读取 `ftyp`、`meta`、`iloc`、`iinf`、`iprp` 等核心盒信息，便于调试与分析。
- **网格图像重建**：支持将三星网格化存储的主图像还原为标准平面图像。
- **元数据安全重建**：通过 `HEICBuilder` 自动处理偏移量与引用更新，生成结构正确的新 HEIC 文件。
- **跨厂商兼容转换**：提供 `convert_samsung_motion_photo` 高阶函数，将三星动态照片转换为苹果可识别的 HEIC + MOV 组合，并可选择性写入 `ContentIdentifier`。
- **命令行工具**：内置 CLI，可直接在终端运行转换任务。

## 使用方式

### 安装

```bash
pip install .
```

### 命令行

```bash
pyheic-struct samsung.heic \
  --output-heic samsung_fixed.HEIC \
  --output-mov samsung_fixed.MOV
```

常用参数：
- `--output-heic`：指定生成的 HEIC 文件路径
- `--output-mov`：指定生成的 MOV 文件路径
- `--skip-mov-tag`：跳过对 MOV 写入 `ContentIdentifier`（无需 exiftool）

### 作为库使用

```python
from pyheic_struct import (
    HEICFile,
    HEICBuilder,
    convert_samsung_motion_photo,
)

# 解析 HEIC 结构
heic = HEICFile("samsung.heic")
print(heic.get_primary_item_id())

# 执行三星 -> 苹果动态照片转换
heic_path, mov_path = convert_samsung_motion_photo("samsung.heic")
print("新 HEIC：", heic_path)
print("新 MOV：", mov_path)
```

## 开发调试

```bash
python -m pyheic_struct path/to/samsung.heic
python inspect_heic.py samsung_apple_compatible.HEIC
```

项目要求 Python 3.10 及以上版本。欢迎根据实际需求扩展解析器或加入更多厂商的兼容逻辑。
