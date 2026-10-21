#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""公共模块：配置加载、工具路径探测、日志、进度状态。

设计原则：
  1) 零第三方依赖（只用标准库），换电脑无需 pip install
  2) 工具路径自动探测（deno / aria2 / ffmpeg），探测不到降级运行
  3) 所有配置集中在 config.json，代码里不写死路径
"""
import os, sys, json, shutil, subprocess, platform, time, threading

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(ROOT, "config.json")
STATE_DIR = os.path.join(ROOT, ".state")
LOG_DIR = os.path.join(ROOT, "logs")
os.makedirs(STATE_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

IS_WIN = platform.system() == "Windows"


# ---------------- 配置 ----------------
_DEFAULT = {
    "output_dir": "E:/MediaLibrary",
    "channel_url": "",
    "quality": {"mode": "strict", "min_height": 1080, "prefer_audio": "opus"},
    "network": {"proxy": "http://127.0.0.1:7892", "proxy_enabled": True,
                "pot_server": "http://127.0.0.1:4416", "deno_path": "",
                "aria2_path": "", "concurrency": 16, "sleep_between_videos": 5},
    "lyrics": {"enabled": True, "languages": ["en"], "manual_only": True,
               "sub_dir_name": "lyrics"},
    "report": {"enabled": True, "filename": "媒体库清单.xlsx", "calc_difficulty": True},
    "advanced": {"keep_video": True, "player_client": "mweb,tv,web,ios",
                 "max_retries": 3, "stale_limit": 8},
}


def _merge(base, override):
    out = dict(base)
    for k, v in (override or {}).items():
        if k.startswith("_"):
            continue
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config():
    cfg = _DEFAULT
    if os.path.exists(CONFIG_PATH):
        try:
            user = json.load(open(CONFIG_PATH, encoding="utf-8"))
            cfg = _merge(_DEFAULT, user)
        except Exception as e:
            log("配置解析失败，用默认值: %s" % e)
    return cfg


# ---------------- 日志 ----------------
_log_lock = threading.Lock()
def log(msg, level="INFO"):
    line = "[%s] %s %s" % (time.strftime("%H:%M:%S"), level, msg)
    with _log_lock:
        print(line, flush=True)
        try:
            with open(os.path.join(LOG_DIR, "run.log"), "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass
    push_event(msg, level)


# ---------------- 事件总线（供 Web UI 读取进度）----------------
_EVENTS = []
def push_event(msg, level="INFO"):
    with _log_lock:
        _EVENTS.append({"t": time.time(), "msg": msg, "level": level})
        if len(_EVENTS) > 500:
            del _EVENTS[:200]

def recent_events(n=60):
    return _EVENTS[-n:]


# ---------------- 状态（断点/进度）----------------
STATE_PATH = os.path.join(STATE_DIR, "progress.json")
_sstate_lock = threading.Lock()

def read_state():
    try:
        return json.load(open(STATE_PATH, encoding="utf-8"))
    except Exception:
        return {}

def write_state(**kw):
    with _sstate_lock:
        st = read_state()
        st.update(kw)
        st["updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
        try:
            json.dump(st, open(STATE_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        except Exception:
            pass


# ---------------- 工具探测 ----------------
def _which(names):
    for n in names:
        p = shutil.which(n)
        if p:
            return p
    return ""

def find_deno(cfg):
    """deno 是 JS 运行时，用于解 YouTube 的 n challenge。找不到会显著降低可用性。"""
    p = cfg.get("network", {}).get("deno_path") or ""
    if p and os.path.exists(p):
        return p.replace("\\", "/")
    # 1) PATH
    p = _which(["deno", "deno.exe"])
    if p:
        return p.replace("\\", "/")
    # 2) 常见位置
    cands = [
        os.path.join(ROOT, "tools", "deno", "deno.exe"),
        os.path.join(ROOT, "tools", "deno.exe"),
        os.path.expanduser("~/.deno/bin/deno.exe"),
        os.path.expanduser("~/.deno/bin/deno"),
    ]
    for c in cands:
        if os.path.exists(c):
            return c.replace("\\", "/")
    return ""

def find_aria2(cfg):
    p = cfg.get("network", {}).get("aria2_path") or ""
    if p and os.path.exists(p):
        return p.replace("\\", "/")
    p = _which(["aria2c", "aria2c.exe"])
    if p:
        return p.replace("\\", "/")
    import glob
    for pat in [os.path.join(ROOT, "tools", "aria2", "*", "aria2c.exe"),
                os.path.join(ROOT, "tools", "aria2", "aria2c.exe")]:
        g = glob.glob(pat)
        if g:
            return g[0].replace("\\", "/")
    return ""

def find_ffmpeg():
    p = _which(["ffmpeg", "ffmpeg.exe"])
    if p:
        return p.replace("\\", "/")
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe().replace("\\", "/")
    except Exception:
        pass
    import glob
    for pat in [os.path.join(ROOT, "tools", "ffmpeg", "*.exe")]:
        g = glob.glob(pat)
        if g:
            return g[0].replace("\\", "/")
    return ""

def env_no_proxy():
    e = dict(os.environ)
    for k in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY"):
        e.pop(k, None)
    return e

def py():
    return sys.executable
