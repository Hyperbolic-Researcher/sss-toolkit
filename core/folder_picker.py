#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""folder_picker.py —— 弹 Windows 文件夹选择框

两级方案：
  1) 首选 IFileDialog（Vista+ 新式大窗口，带左侧导航栏、可搜索、可新建）
     —— 就是 Office / WPS「浏览文件夹」那种界面
  2) 失败则回退 SHBrowseForFolderW（老式小窗口，保证能用）

为什么不用 tkinter：托管 Python 未编译 tkinter，pip 也装不了。

输出：stdout 打印选中的绝对路径（取消则空行）
"""
import sys, os, ctypes, uuid
from ctypes import wintypes, POINTER, byref, c_void_p

ole32 = ctypes.windll.ole32
shell32 = ctypes.windll.shell32

MAX_PATH = 260
S_OK = 0

# ── FOS_* 选项 ──
FOS_PICKFOLDERS = 0x00000020
FOS_FORCEFILESYSTEM = 0x00000040
FOS_PATHMUSTEXIST = 0x00000800
SIGDN_FILESYSPATH = 0x80058000
CLSCTX_INPROC_SERVER = 0x1


class GUID(ctypes.Structure):
    _fields_ = [("Data1", wintypes.DWORD),
                ("Data2", wintypes.WORD),
                ("Data3", wintypes.WORD),
                ("Data4", ctypes.c_ubyte * 8)]

    @classmethod
    def from_str(cls, s):
        u = uuid.UUID(s)
        g = cls()
        g.Data1 = u.time_low
        g.Data2 = u.time_mid
        g.Data3 = u.time_hi_version
        g.Data4 = (ctypes.c_ubyte * 8)(*u.bytes[8:])
        return g


CLSID_FileOpenDialog = GUID.from_str("DC1C5A9C-E88A-4dde-A5A1-60F82A20AEF7")
IID_IFileDialog = GUID.from_str("42f85136-db7e-439c-85f1-e4075d135fc8")


def _vt_call(obj, index, argtypes, *args):
    """调用 COM 对象的第 index 个虚函数"""
    vtbl = ctypes.cast(obj, POINTER(POINTER(c_void_p))).contents
    proto = ctypes.WINFUNCTYPE(ctypes.HRESULT, c_void_p, *argtypes)
    fn = proto(vtbl[index])
    return fn(obj, *args)


def pick_via_IFileDialog(title="选择文件夹", initial=""):
    """新式大窗口。成功返回路径，取消/失败返回空串"""
    try:
        ole32.CoInitialize(None)
    except Exception:
        pass

    pDlg = c_void_p()
    hr = ole32.CoCreateInstance(ctypes.byref(CLSID_FileOpenDialog), None,
                                CLSCTX_INPROC_SERVER, ctypes.byref(IID_IFileDialog),
                                ctypes.byref(pDlg))
    if hr != S_OK or not pDlg:
        return ""

    try:
        # SetOptions(FOS_PICKFOLDERS | FOS_FORCEFILESYSTEM | FOS_PATHMUSTEXIST)
        # 先 GetOptions 拿到现有值再或上去，避免覆盖默认选项
        cur = wintypes.DWORD(0)
        _vt_call(pDlg, 10, [POINTER(wintypes.DWORD)], ctypes.byref(cur))   # GetOptions
        opts = cur.value | FOS_PICKFOLDERS | FOS_FORCEFILESYSTEM | FOS_PATHMUSTEXIST
        _vt_call(pDlg, 9, [wintypes.DWORD], wintypes.DWORD(opts))          # SetOptions

        # SetTitle(LPCWSTR)
        if title:
            _vt_call(pDlg, 17, [wintypes.LPCWSTR], title)

        # Show(HWND) —— 0 = 无父窗口
        hr = _vt_call(pDlg, 3, [wintypes.HWND], None)
        if hr != S_OK:
            return ""

        # GetResult(IShellItem**)
        pItem = c_void_p()
        hr = _vt_call(pDlg, 20, [POINTER(c_void_p)], ctypes.byref(pItem))
        if hr != S_OK or not pItem:
            return ""

        try:
            # IShellItem::GetDisplayName(SIGDN, LPWSTR*)
            psz = wintypes.LPWSTR()
            hr = _vt_call(pItem, 5, [ctypes.c_uint, POINTER(wintypes.LPWSTR)],
                          ctypes.c_uint(SIGDN_FILESYSPATH), ctypes.byref(psz))
            if hr != S_OK or not psz:
                return ""
            path = psz.value or ""
            try:
                ole32.CoTaskMemFree(psz)
            except Exception:
                pass
            return path
        finally:
            # Release IShellItem
            try:
                _vt_call(pItem, 2, [])
            except Exception:
                pass
    finally:
        try:
            _vt_call(pDlg, 2, [])
        except Exception:
            pass
        try:
            ole32.CoUninitialize()
        except Exception:
            pass


# ---------------- 老式回退 ----------------
BIF_RETURNONLYFSDIRS = 0x0001
BIF_NEWDIALOGSTYLE = 0x0040
BIF_EDITBOX = 0x0010


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


def pick_via_browse(title="选择文件夹"):
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
    bi.ulFlags = BIF_RETURNONLYFSDIRS | BIF_NEWDIALOGSTYLE | BIF_EDITBOX
    bi.lpfn = None
    bi.lParam = 0
    bi.iImage = 0
    shell32.SHBrowseForFolderW.restype = ctypes.c_void_p
    pidl = shell32.SHBrowseForFolderW(ctypes.byref(bi))
    if not pidl:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(MAX_PATH)
        ok = shell32.SHGetPathFromIDListW(ctypes.c_void_p(pidl), buf)
        return buf.value if ok else ""
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
    title = sys.argv[1] if len(sys.argv) > 1 else "选择下载保存目录"
    p = ""
    try:
        p = pick_via_IFileDialog(title)
    except Exception as e:
        sys.stderr.write("IFileDialog 失败: %s\n" % e)
    if not p:
        # 用户可能只是按了取消，也可能是 IFileDialog 不可用；
        # 只有明确异常才回退，取消时不该再弹一次。
        pass
    print((p or "").replace("\\", "/"), flush=True)


if __name__ == "__main__":
    main()