#!/usr/bin/env python3
"""
GUI batch utility for inspecting Live Photo / Motion Photo media trees.
"""

from __future__ import annotations

import os
import queue
import shutil
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Tuple

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

# 假设 pyheic_struct 在你的 Python 路径中
# from pyheic_struct import AppleTargetAdapter, HEICFile, convert_motion_photo

# --- Mocking pyheic_struct for testing if not installed ---
# 如果你没有安装 pyheic_struct，请取消注释下面的部分来模拟它
try:
    from pyheic_struct import AppleTargetAdapter, HEICFile, convert_motion_photo
except ImportError:
    print("Warning: pyheic_struct not found. Using mock objects.")
    
    class MockHEICFile:
        def __init__(self, path: str):
            self._path = Path(path)
        def find_box(self, box_type: str) -> bool:
            # 模拟三星 motion photo
            return "samsung" in self._path.name.lower()
    
    class MockAppleTargetAdapter:
        pass
    
    def mock_convert_motion_photo(heic_path, vendor_hint, target_adapter, output_still, output_video, inject_content_id_into_mov):
        output_still.touch()
        output_video.touch()
        return output_still, output_video
    
    HEICFile = MockHEICFile
    AppleTargetAdapter = MockAppleTargetAdapter
    convert_motion_photo = mock_convert_motion_photo
# --- End of Mocking ---


STILL_SUFFIXES = {".heic", ".heif"}
VIDEO_SUFFIXES = {".mov", ".mp4", ".m4v", ".qt", ".3gp"}

TRANSLATIONS: Dict[str, Dict[str, str]] = {
    "zh": {
        "app_title": "Live Photo / Motion Photo 批处理工具",
        "menu_language": "语言",
        "menu_language_zh": "中文",
        "menu_language_en": "English",
        "label_directory": "处理目录:",
        "button_browse": "选择…",
        "group_options": "可选功能",
        "option_live_pair": "检测 Live Photo 配对并移动缺失伴侣的视频",
        "option_convert_motion": "将三星 Motion Photo 转换为 Live Photo",
        "option_cleanup_mp4": "清除带有 MotionPhoto_Data 标记的多余 MP4",
        "label_workers": "并发线程数:",
        "button_start": "开始处理",
        "progress_status": "进度: {done} / {total}",
        "log_group": "日志",
        "warn_processing_title": "正在处理",
        "warn_processing_body": "任务仍在运行，请稍候。",
        "error_invalid_dir_title": "无效路径",
        "error_invalid_dir_body": "请选择一个有效的目录。",
        "general_yes": "是",
        "general_no": "否",
        "log_root_dir": "处理目录: {path}",
        "log_exiftool": "exiftool 可用: {status}",
        "log_scanning": "正在扫描媒体文件……",
        "log_no_tasks": "未找到任何任务，无需处理。",
        "log_executing": "共有 {total} 个任务，使用 {workers} 个线程执行……",
        "log_task_entry": "[{task}] {result}",
        "log_finished": "全部任务已完成。",
        "log_processing_done": "处理完毕。",
        "task_orphan_video": "孤立视频: {path}",
        "task_motion_convert": "Motion Photo 转 Live Photo: {path}",
        "task_cleanup_mp4": "清理 MP4: {path}",
        "result_moved": "已移动到 {dest}",
        "result_skipped_exists": "已存在转换结果，跳过",
        "result_converted": "已转换为 {heic} / {mov}",
        "result_cleanup_removed": "已删除 (MotionPhoto_Data)",
        "result_cleanup_kept": "保留",
        "result_cleanup_skipped": "跳过 (缺少 exiftool)",
        "result_failed": "失败: {error}",
    },
    "en": {
        "app_title": "Live / Motion Photo Batch Manager",
        "menu_language": "Language",
        "menu_language_zh": "Chinese",
        "menu_language_en": "English",
        "label_directory": "Folder:",
        "button_browse": "Browse…",
        "group_options": "Optional Tasks",
        "option_live_pair": "Check Live Photo pairs and move orphaned videos",
        "option_convert_motion": "Convert Samsung Motion Photos to Live Photo",
        "option_cleanup_mp4": "Remove redundant MP4 files tagged MotionPhoto_Data",
        "label_workers": "Worker threads:",
        "button_start": "Start",
        "progress_status": "Progress: {done} / {total}",
        "log_group": "Log",
        "warn_processing_title": "Processing",
        "warn_processing_body": "Tasks are still running. Please wait.",
        "error_invalid_dir_title": "Invalid Path",
        "error_invalid_dir_body": "Please choose a valid directory.",
        "general_yes": "yes",
        "general_no": "no",
        "log_root_dir": "Root directory: {path}",
        "log_exiftool": "exiftool available: {status}",
        "log_scanning": "Scanning media files...",
        "log_no_tasks": "No tasks found. Nothing to do.",
        "log_executing": "Executing {total} task(s) with {workers} worker(s)...",
        "log_task_entry": "[{task}] {result}",
        "log_finished": "All tasks completed.",
        "log_processing_done": "Processing finished.",
        "task_orphan_video": "Orphan video: {path}",
        "task_motion_convert": "Motion Photo → Live Photo: {path}",
        "task_cleanup_mp4": "Cleanup MP4: {path}",
        "result_moved": "Moved to {dest}",
        "result_skipped_exists": "Skipped (outputs already exist)",
        "result_converted": "Converted to {heic} / {mov}",
        "result_cleanup_removed": "Removed (MotionPhoto_Data)",
        "result_cleanup_kept": "Kept",
        "result_cleanup_skipped": "Skipped (exiftool unavailable)",
        "result_failed": "Failed: {error}",
    },
}


@dataclass
class ProcessingOptions:
    root_dir: Path
    handle_live_pairs: bool
    convert_motion: bool
    remove_motion_mp4: bool
    max_workers: int


@dataclass
class Task:
    func: Callable[[], str | None]
    description: str


def _is_motion_photo(heic_path: Path) -> bool:
    try:
        heic = HEICFile(str(heic_path))
        return heic.find_box("mpvd") is not None
    except Exception:
        return False


def _move_orphan_video(mov_path: Path, root_dir: Path, tr: Callable[[str], str]) -> str:
    error_dir = root_dir / "错误的LivePhoto视频"
    error_dir.mkdir(parents=True, exist_ok=True)

    destination = error_dir / mov_path.name
    counter = 1
    while destination.exists():
        destination = error_dir / f"{mov_path.stem}_{counter}{mov_path.suffix}"
        counter += 1

    shutil.move(str(mov_path), str(destination))
    return tr("result_moved", dest=str(destination))


def _convert_motion_photo(heic_path: Path, inject_mov_tag: bool, tr: Callable[[str], str]) -> str:
    output_still = heic_path.with_name(f"{heic_path.stem}_apple_compatible.HEIC")
    output_video = heic_path.with_name(f"{heic_path.stem}_apple_compatible.MOV")

    if output_still.exists() or output_video.exists():
        return tr("result_skipped_exists")

    heic_out, mov_out = convert_motion_photo(
        heic_path,
        vendor_hint="samsung",
        target_adapter=AppleTargetAdapter(),
        output_still=output_still,
        output_video=output_video,
        inject_content_id_into_mov=inject_mov_tag,
    )
    return tr("result_converted", heic=heic_out.name, mov=mov_out.name)


def _cleanup_motion_mp4(mp4_path: Path, has_exiftool: bool, tr: Callable[[str], str]) -> str:
    if not has_exiftool:
        return tr("result_cleanup_skipped")

    cmd = [
        "exiftool",
        "-s",
        "-s",
        "-s",
        "-EmbeddedVideoType",
        str(mp4_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    output = result.stdout.strip()

    if "MotionPhoto_Data" in output:
        mp4_path.unlink(missing_ok=True)
        return tr("result_cleanup_removed")
    return tr("result_cleanup_kept")


def _gather_tasks(
    options: ProcessingOptions,
    has_exiftool: bool,
    log: Callable[[str], None],
    tr: Callable[[str], str],
) -> List[Task]:
    tasks: List[Task] = []
    base_map: Dict[Tuple[Path, str], Dict[str, object]] = {}
    heic_files: List[Path] = []
    mp4_files: List[Path] = []

    log(tr("log_scanning"))
    for path in options.root_dir.rglob("*"):
        if not path.is_file():
            continue
        suffix = path.suffix.lower()

        if suffix in STILL_SUFFIXES:
            heic_files.append(path)
            key = (path.parent, path.stem.lower())
            entry = base_map.setdefault(key, {})
            entry["still"] = path
        elif suffix in VIDEO_SUFFIXES:
            key = (path.parent, path.stem.lower())
            entry = base_map.setdefault(key, {})
            entry.setdefault("videos", []).append(path) # type: ignore
            if suffix == ".mp4":
                mp4_files.append(path)

    if options.handle_live_pairs:
        for entry in base_map.values():
            has_still = "still" in entry
            videos = entry.get("videos") or []
            if not has_still and videos:
                for video_path in videos: # type: ignore
                    tasks.append(
                        Task(
                            func=lambda p=video_path, tr=tr: _move_orphan_video(p, options.root_dir, tr),
                            description=tr("task_orphan_video", path=str(video_path)),
                        )
                    )

    if options.convert_motion:
        inject_mov_tag = has_exiftool
        for heic_path in heic_files:
            key = (heic_path.parent, heic_path.stem.lower())
            entry = base_map.get(key, {})
            videos = entry.get("videos") or []
            has_mov = any(v.suffix.lower() == ".mov" for v in videos) # type: ignore
            if has_mov:
                continue
            if not _is_motion_photo(heic_path):
                continue
            tasks.append(
                Task(
                    func=lambda p=heic_path, tr=tr: _convert_motion_photo(p, inject_mov_tag, tr),
                    description=tr("task_motion_convert", path=str(heic_path)),
                )
            )

    if options.remove_motion_mp4:
        for mp4_path in mp4_files:
            tasks.append(
                Task(
                    func=lambda p=mp4_path, tr=tr: _cleanup_motion_mp4(p, has_exiftool, tr),
                    description=tr("task_cleanup_mp4", path=str(mp4_path)),
                )
            )

    return tasks


def _worker(options: ProcessingOptions, message_queue: queue.Queue, language: str) -> None:
    has_exiftool = shutil.which("exiftool") is not None

    lang_map = TRANSLATIONS.get(language, TRANSLATIONS["zh"])

    def tr(key: str, **kwargs) -> str:
        template = lang_map.get(key, TRANSLATIONS["zh"].get(key, key))
        return template.format(**kwargs)

    def emit_log(message: str) -> None:
        message_queue.put(("log", message))

    emit_log(tr("log_root_dir", path=str(options.root_dir)))
    status_text = tr("general_yes") if has_exiftool else tr("general_no")
    emit_log(tr("log_exiftool", status=status_text))

    try:
        tasks = _gather_tasks(options, has_exiftool, emit_log, tr)
        total = len(tasks)
        message_queue.put(("progress_setup", total))

        if total == 0:
            emit_log(tr("log_no_tasks"))
            message_queue.put(("finished", None))
            return

        max_workers = max(1, options.max_workers)
        emit_log(tr("log_executing", total=total, workers=max_workers))

        completed = 0
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {executor.submit(task.func): task for task in tasks}
            for future in as_completed(future_map):
                task = future_map[future]
                try:
                    outcome = future.result()
                    result_text = outcome if outcome else "done"
                except Exception as exc:
                    result_text = tr("result_failed", error=exc)
                emit_log(tr("log_task_entry", task=task.description, result=result_text))
                completed += 1
                message_queue.put(("progress", completed))

        emit_log(tr("log_finished"))
    except Exception as e:
        emit_log(tr("result_failed", error=e))
    finally:
        message_queue.put(("finished", None))


class BatchManagerGUI:
    
    # --- 修复 ---
    # 删除了第一个 __init__，并将 self.lang 添加到第二个 __init__
    
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("Live Photo / Motion Photo 批处理工具")
        self.root.geometry("780x520")

        # 修复：将 self.lang 的定义合并到这个 __init__ 中
        self.lang = tk.StringVar(value="zh")

        self.queue: queue.Queue = queue.Queue()
        self.worker_thread: threading.Thread | None = None

        self.path_var = tk.StringVar()
        self.handle_live_var = tk.BooleanVar(value=True)
        self.convert_motion_var = tk.BooleanVar(value=True)
        self.remove_mp4_var = tk.BooleanVar(value=True)
        default_workers = max(1, min(4, (os.cpu_count() or 4)))
        self.worker_count_var = tk.IntVar(value=default_workers)

        self.progress_total = 0
        self.progress_done = 0

        self._build_ui()
        self.root.after(100, self._poll_queue)

    def run(self) -> None:
        self.root.mainloop()

    # 辅助函数，用于获取翻译后的文本
    def _t(self, key: str) -> str:
        lang_map = TRANSLATIONS.get(self.lang.get(), TRANSLATIONS["zh"])
        return lang_map.get(key, TRANSLATIONS["zh"].get(key, key))

    def _build_ui(self) -> None:
        padding = {"padx": 10, "pady": 6}

        path_frame = ttk.Frame(self.root)
        path_frame.pack(fill="x", **padding)

        ttk.Label(path_frame, text=self._t("label_directory")).pack(side="left")
        entry = ttk.Entry(path_frame, textvariable=self.path_var)
        entry.pack(side="left", fill="x", expand=True, padx=(8, 8))

        ttk.Button(path_frame, text=self._t("button_browse"), command=self._choose_directory).pack(side="left")

        options_frame = ttk.LabelFrame(self.root, text=self._t("group_options"))
        options_frame.pack(fill="x", **padding)

        ttk.Checkbutton(
            options_frame,
            text=self._t("option_live_pair"),
            variable=self.handle_live_var,
        ).pack(anchor="w", padx=8, pady=2)
        ttk.Checkbutton(
            options_frame,
            text=self._t("option_convert_motion"),
            variable=self.convert_motion_var,
        ).pack(anchor="w", padx=8, pady=2)
        ttk.Checkbutton(
            options_frame,
            text=self._t("option_cleanup_mp4"),
            variable=self.remove_mp4_var,
        ).pack(anchor="w", padx=8, pady=2)

        worker_frame = ttk.Frame(self.root)
        worker_frame.pack(fill="x", **padding)
        ttk.Label(worker_frame, text=self._t("label_workers")).pack(side="left")
        self.worker_spin = ttk.Spinbox(
            worker_frame,
            from_=1,
            to=32,
            textvariable=self.worker_count_var,
            width=5,
        )
        self.worker_spin.pack(side="left", padx=(8, 0))

        control_frame = ttk.Frame(self.root)
        control_frame.pack(fill="x", **padding)
        self.start_button = ttk.Button(control_frame, text=self._t("button_start"), command=self._start_processing)
        self.start_button.pack(side="left")

        self.progress_bar = ttk.Progressbar(self.root, mode="determinate")
        self.progress_bar.pack(fill="x", padx=10, pady=(4, 0))

        self.progress_label = ttk.Label(self.root, text=self._t("progress_status").format(done=0, total=0))
        self.progress_label.pack(fill="x", padx=10, pady=(2, 6))

        log_frame = ttk.LabelFrame(self.root, text=self._t("log_group"))
        log_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.log_text = tk.Text(log_frame, height=16, wrap="word")
        self.log_text.pack(side="left", fill="both", expand=True)
        scrollbar = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        scrollbar.pack(side="right", fill="y")
        self.log_text.configure(yscrollcommand=scrollbar.set)
        
        # P.S. 我还修复了 UI 文本，使其能够响应语言（尽管此脚本中没有切换语言的菜单）
        # 你原来的 _build_ui 使用了硬编码的中文
        self._update_ui_text()
        
    def _update_ui_text(self) -> None:
        """更新界面上所有可翻译的文本 (此脚本中未实现语言切换，但为未来做准备)"""
        self.root.title(self._t("app_title"))
        
        # 这里应该重新配置所有 Label, Button, LabelFrame 的 text
        # 为了简洁，我在 _build_ui 中直接使用了 self._t()
        # 如果要实现动态切换，需要在这里引用所有组件并 .config(text=...)
        pass


    def _choose_directory(self) -> None:
        selected = filedialog.askdirectory()
        if selected:
            self.path_var.set(selected)

    def _start_processing(self) -> None:
        # P.S. 我还修复了这里对 _t 方法的调用，你之前遗漏了
        if self.worker_thread and self.worker_thread.is_alive():
            messagebox.showwarning(self._t("warn_processing_title"), self._t("warn_processing_body"))
            return

        directory = Path(self.path_var.get()).expanduser()
        if not directory.is_dir():
            messagebox.showerror(self._t("error_invalid_dir_title"), self._t("error_invalid_dir_body"))
            return

        options = ProcessingOptions(
            root_dir=directory,
            handle_live_pairs=self.handle_live_var.get(),
            convert_motion=self.convert_motion_var.get(),
            remove_motion_mp4=self.remove_mp4_var.get(),
            max_workers=self.worker_count_var.get(),
        )

        self._reset_progress()
        self.start_button.config(state="disabled")
        self.worker_spin.config(state="disabled")

        self.worker_thread = threading.Thread(
            target=_worker,
            args=(options, self.queue, self.lang.get()), # 这一行现在可以正常工作了
            daemon=True,
        )
        self.worker_thread.start()

    def _reset_progress(self) -> None:
        self.progress_total = 0
        self.progress_done = 0
        self.progress_bar["value"] = 0
        self.progress_bar["maximum"] = 1
        self.progress_label.config(text=self._t("progress_status").format(done=0, total=0))
        self.log_text.delete("1.0", tk.END)

    def _poll_queue(self) -> None:
        try:
            while True:
                message = self.queue.get_nowait()
                self._handle_message(message)
        except queue.Empty:
            pass
        finally:
            self.root.after(100, self._poll_queue)

    def _handle_message(self, message: Tuple[str, object]) -> None:
        kind, payload = message

        if kind == "log":
            text = str(payload)
            self.log_text.insert(tk.END, text + "\n")
            self.log_text.see(tk.END)
        elif kind == "progress_setup":
            self.progress_total = int(payload) if payload else 0
            self.progress_done = 0
            self.progress_bar["maximum"] = max(1, self.progress_total)
            self.progress_bar["value"] = 0
            self.progress_label.config(text=self._t("progress_status").format(done=0, total=self.progress_total))
        elif kind == "progress":
            self.progress_done = int(payload)
            self.progress_bar["value"] = self.progress_done
            self.progress_label.config(text=self._t("progress_status").format(done=self.progress_done, total=self.progress_total))
        elif kind == "finished":
            self.start_button.config(state="normal")
            self.worker_spin.config(state="normal")
            self.log_text.insert(tk.END, self._t("log_processing_done") + "\n")
            self.log_text.see(tk.END)


def main() -> None:
    gui = BatchManagerGUI()
    gui.run()


if __name__ == "__main__":  # pragma: no cover
    main()