SamsungToLivePhoto（Windows 版）
================================

该压缩包包含一个通过 PyInstaller 构建的可执行文件 `SamsungToLivePhoto.exe`，用于把三星运动照片转换为 Apple Live Photo（HEIC + MOV）。

使用方式
--------
1. 解压压缩包，例如解压到 `C:\Tools\SamsungToLivePhoto`。
2. 确保已安装 [ExifTool](https://exiftool.org/)。如果不想写入 MOV 的 ContentIdentifier，可在命令中添加 `--skip-mov-tag`。
3. 打开 PowerShell 或 CMD，执行如下命令：

   ```
   cd C:\Tools\SamsungToLivePhoto
   .\SamsungToLivePhoto.exe "C:\path\to\motion_photo.HEIC" --output-dir "C:\path\to\output"
   ```

4. 程序会在输出目录生成 Apple 兼容的 HEIC 与 MOV 文件。

常见选项
--------
- `--heic-name` / `--mov-name`：自定义输出文件名。
- `--skip-mov-tag`：跳过对 MOV 写入 ContentIdentifier（无需 ExifTool）。

注意事项
--------
- 可执行文件首次运行可能被 Windows Defender SmartScreen 拦截，可选择“仍要运行”继续。
- 该工具为命令行程序，请在终端（PowerShell/CMD）中使用。
- 如遇到“找不到 DLL”或依赖问题，请确认压缩包完整解压且未被杀毒软件隔离。*** End Patch
