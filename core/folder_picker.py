#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""folder_picker.py —— 弹出 Windows 原生文件夹选择框，把路径打印到 stdout

为什么单独一个进程：
  tkinter 的对话框必须在主线程且有图形上下文，放在 web 服务的后台线程里会崩。
  用独立子进程弹窗、主进程读 stdout，最稳。

用法：python folder_picker.py ["初始目录"]
 stdout 输出：选中的绝对路径（取消则输出空行）
"""
import sys, os

try:
    import tkinter as tk
    from tkinter import filedialog
except Exception as e:
    print("", flush=True)
    sys.stderr.write("tkinter 不可用: %s\n" % e)
    sys.exit(1)


def main():
    init = sys.argv[1] if len(sys.argv) > 1 else ""
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    root.update()
    try:
        path = filedialog.askdirectory(
            title="选择下载保存目录",
            initialdir=init if init and os.path.isdir(init) else os.path.expanduser("~"),
            mustexist=False,
        )
    except Exception:
        path = ""
    root.destroy()
    print((path or "").replace("\\", "/"), flush=True)


if __name__ == "__main__":
    main()