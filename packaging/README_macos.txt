SamsungToLivePhoto（macOS 版）
==============================

该压缩包包含一个通过 PyInstaller 构建的可执行文件 `SamsungToLivePhoto`，用于将三星运动照片转换成 Apple Live Photo（HEIC + MOV）。

使用方式
--------
1. 解压 `SamsungToLivePhoto-macos.tar.gz`，例如：

   ```bash
   tar -xzf SamsungToLivePhoto-macos.tar.gz
   ```

   解压后会得到 `SamsungToLivePhoto` 可执行文件。

2. 首次从网络下载的文件可能被标记为隔离，可运行：

   ```bash
   xattr -dr com.apple.quarantine SamsungToLivePhoto
   ```

3. 确保已安装 [ExifTool](https://exiftool.org/)。在 macOS 上可通过 Homebrew 安装：

   ```bash
   brew install exiftool
   ```

   若不需要向 MOV 写入 ContentIdentifier，可在命令中添加 `--skip-mov-tag`。

4. 在终端中执行：

   ```bash
   ./SamsungToLivePhoto /path/to/motion_photo.HEIC --output-dir /path/to/output
   ```

常见选项
--------
- `--heic-name` / `--mov-name`：自定义输出文件名。
- `--skip-mov-tag`：跳过对 MOV 写入 ContentIdentifier（无需 ExifTool）。

注意事项
--------
- 该工具为命令行程序，需要在终端中运行。
- 若运行时报错缺少动态库，请确认压缩包完整解压且未被安全工具隔离。*** End Patch
