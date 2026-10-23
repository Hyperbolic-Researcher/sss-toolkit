#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""folder_picker.py —— 弹 Windows 原生「选择文件夹」对话框

★ 为什么不用 tkinter：
  WorkBuddy 托管的 Python 3.13 环境**没有编译 tkinter**（ModuleNotFoundError），
  pip 装不了，需要重装 Python 才有。所以改用 ctypes 直接调 Win32 API。

使用 Shell 的 SHBrowseForFolderW：
  - 纯标准库，零额外依赖
  - 原生对话框，和"另存为"里的选目录一致
  - 返回绝对路径

用法：python folder_picker.py ["初始目录"]
 stdout：选中的绝对路径（取消则空行）
"""
import sys, os, ctypes
from ctypes import wintypes

ole32 = ctypes.windll.ole32
shell32 = ctypes.windll.shell32

BIF_RETURNONLYFSDIRS = 0x00000001   # 只允许选文件系统目录
BIF_NEWDIALOGSTYLE = 0x00000040     # 新版对话框（可新建文件夹、可输入路径）
BIF_EDITBOX = 0x00000010            # 带输入框
BIF_USENEWUI = BIF_NEWDIALOGSTYLE | BIF_EDITBOX

MAX_PATH = 260


class BROWSEINFOW(ctypes.Structure):
    _fields_ = [
        ("hwndOwner", wintypes.HWND),
        ("pidlRoot", ctypes.c_void_p),
        ("pszDisplayName", wintypes.LPWSTR),
        ("lpszTitle", wintypes.LPCWSTR),
        ("ulFlags", wintypes.UINT),
        ("lpfn", ctypes.c_void_p),
        ("lParam", wintypes.LPARAM),
        ("iImage", ctypes.c_int),
    ]


def pick_folder(title="选择下载保存目录", initial=""):
    # 初始化 COM（Shell 对话框需要）
    try:
        ole32.CoInitialize(None)
    except Exception:
        pass

    display = ctypes.create_unicode_buffer(MAX_PATH)
    bi = BROWSEINFOW()
    bi.hwndOwner = None
    bi.pidlRoot = None
    bi.pszDisplayName = ctypes.cast(display, wintypes.LPWSTR)
    bi.lpszTitle = title
    bi.ulFlags = BIF_RETURNONLYFSDIRS | BIF_USENEWUI
    bi.lpfn = None
    bi.lParam = 0
    bi.iImage = 0

    shell32.SHBrowseForFolderW.restype = ctypes.c_void_p
    pidl = shell32.SHBrowseForFolderW(ctypes.byref(bi))
    if not pidl:
        return ""

    try:
        path_buf = ctypes.create_unicode_buffer(MAX_PATH)
        ok = shell32.SHGetPathFromIDListW(ctypes.c_void_p(pidl), path_buf)
        return path_buf.value if ok else ""
    finally:
        try:
            ole32.CoTaskMemFree(ctypes.c_void_p(pidl))
        except Exception:
            pass
        try:
            ole32.CoUninitialize()
        except Exception:
            pass


def main():
    init = sys.argv[1] if len(sys.argv) > 1 else ""
    try:
        p = pick_folder(initial=init)
    except Exception as e:
        sys.stderr.write("picker error: %s\n" % e)
        p = ""
    print((p or "").replace("\\", "/"), flush=True)


if __name__ == "__main__":
    main()