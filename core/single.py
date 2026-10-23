#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""single：单个视频下载（网页「粘贴链接即下载」的后端）

设计目标：**操作顺畅**
  1. 粘贴链接 → 立即解析出标题/时长/画质，让用户确认在下什么
  2. 默认最高画质，不需要用户懂格式 ID
  3. 边下边推进度，完成后能一键打开所在文件夹

沿用批量下载的同一套铁律：
  - 格式串禁止 /best（防 360p 降级）
  - --keep-video（防沙箱批量删除卡死）
  - 多 client 组合（防 SABR-only）
"""
import os, re, sys, json, time, shutil, subprocess, threading
from . import common

# ---------------- 单任务状态 ----------------
_TASK = {
    "running": False,
    "url": "",
    "title": "",
    "dest": "",
    "percent": 0.0,
    "speed": "",
    "eta": "",
    "stage": "",
    "file": "",
    "error": "",
    "started": 0,
}
_TASK_LOCK = threading.Lock()
_STOP = {"flag": False}


def task_state():
    with _TASK_LOCK:
        return dict(_TASK)


def stop_task():
    _STOP["flag"] = True
    with _TASK_LOCK:
        _TASK["stage"] = "正在停止..."


# ---------------- 链接解析 ----------------
ID_PATTERNS = [
    r"(?:v=|/v/|youtu\.be/|/embed/|/shorts/)([A-Za-z0-9_-]{11})",
    r"^([A-Za-z0-9_-]{11})$",
]


def extract_id(url):
    url = (url or "").strip()
    for p in ID_PATTERNS:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return ""


def base_args(cfg):
    net = cfg["network"]; adv = cfg["advanced"]
    args = [common.py(), "-m", "yt_dlp", "--no-warnings"]
    if net.get("proxy_enabled") and net.get("proxy"):
        args += ["--proxy", net["proxy"]]
    deno = common.find_deno(cfg)
    if deno:
        args += ["--js-runtimes", "deno:" + deno]
    ff = common.find_ffmpeg()
    if ff:
        args += ["--ffmpeg-location", ff]
    extra = "youtube:player_client=" + adv.get("player_client", "mweb,tv,web,ios")
    if net.get("pot_server"):
        extra += ";youtubepot-bgutilhttp:base_url=" + net["pot_server"]
    args += ["--extractor-args", extra]
    return args


def probe(cfg, url):
    """解析视频元信息 + 可用最高画质。返回 dict。"""
    vid = extract_id(url)
    if not vid:
        return {"ok": False, "error": "链接里找不到视频 ID，请检查是否完整"}
    args = base_args(cfg) + [
        "--skip-download",
        "--print", "%(title)s\t%(duration)s\t%(uploader)s\t%(view_count)s\t%(upload_date)s",
        "https://www.youtube.com/watch?v=" + vid,
    ]
    try:
        r = subprocess.run(args, capture_output=True, text=True,
                           env=common.env_no_proxy(), timeout=90,
                           encoding="utf-8", errors="replace")
        out = (r.stdout or "").strip()
        err = (r.stderr or "")
    except Exception as e:
        return {"ok": False, "error": "解析超时：%s" % str(e)[:60]}

    if "not a bot" in err:
        return {"ok": False, "error": "当前 IP 被 YouTube 限流，请换节点后重试"}
    if not out:
        last = err.strip().split("\n")[-1][:120] if err.strip() else "解析失败"
        return {"ok": False, "error": last}

    p = out.split("\t")
    title = p[0] if p else ""
    try:
        dur = float(p[1]) if len(p) > 1 and p[1] not in ("NA", "None", "") else 0
    except ValueError:
        dur = 0
    uploader = p[2] if len(p) > 2 and p[2] != "NA" else ""
    try:
        views = int(p[3]) if len(p) > 3 and p[3] not in ("NA", "None") else 0
    except ValueError:
        views = 0
    upd = p[4] if len(p) > 4 and p[4] != "NA" else ""

    # 查可用最高画质
    best_h, best_fid = 0, ""
    try:
        r2 = subprocess.run(base_args(cfg) + ["-F", "https://www.youtube.com/watch?v=" + vid],
                            capture_output=True, text=True, env=common.env_no_proxy(),
                            timeout=90, encoding="utf-8", errors="replace")
        for line in (r2.stdout or "").split("\n"):
            m = re.match(r"^(\d{2,4})\s+(?:mp4|webm)\s+(\d{2,4})x(\d{2,4})", line.strip())
            if m and int(m.group(3)) > best_h:
                best_h, best_fid = int(m.group(3)), m.group(1)
    except Exception:
        pass

    return {
        "ok": True, "id": vid, "title": title,
        "duration": int(dur),
        "duration_text": ("%d:%02d" % (int(dur)//60, int(dur) % 60)) if dur else "",
        "uploader": uploader, "views": views,
        "upload_date": ("%s-%s-%s" % (upd[:4], upd[4:6], upd[6:8])) if len(upd) == 8 else "",
        "max_height": best_h, "max_fid": best_fid,
        "url": "https://www.youtube.com/watch?v=" + vid,
    }


def safe_name(s, limit=120):
    s = re.sub(r'[\\/:*?"<>|\r\n\t]', "_", s or "")
    s = re.sub(r"\s+", " ", s).strip().strip(".")
    return s[:limit] or "video"


def start_download(cfg, url, dest_dir, min_height=None):
    """启动后台下载。返回 (ok, msg)"""
    with _TASK_LOCK:
        if _TASK["running"]:
            return False, "已有下载任务在进行，请等它完成"
        vid = extract_id(url)
        if not vid:
            return False, "链接无效"
        _TASK.update({
            "running": True, "url": url, "title": "", "dest": dest_dir,
            "percent": 0.0, "speed": "", "eta": "", "stage": "准备中",
            "file": "", "error": "", "started": time.time(),
        })
        _STOP["flag"] = False

    t = threading.Thread(target=_worker, args=(cfg, vid, dest_dir, min_height), daemon=True)
    t.start()
    return True, "已开始"


def _worker(cfg, vid, dest_dir, min_height):
    try:
        os.makedirs(dest_dir, exist_ok=True)
        adv = cfg["advanced"]
        minh = int(min_height or cfg["quality"].get("min_height") or 1080)

        # ★★ 音频必须优先 AAC(140)，不要 Opus(251)
        #  实测：AV1 + Opus 的 MP4（major_brand=isom）在 Windows 自带播放器里
        #  经常打不开 —— Opus 在 MP4 容器中的支持很差。
        #  AAC 是通用格式，任何设备/播放器/剪辑软件都认。
        #  视频仍用 AV1（同画质体积只有 H.264 的 1/3），只是音频换成 AAC。
        #  体积几乎不变：Opus 138k vs AAC 128k。
        # ★ 注意：每个候选必须完整写成「视频+音频」，
        #   不能写成 bv+A/bv+A 而让 A 里再带 "/" —— 那样会解析出只有音频的候选。
        H = "bestvideo[height>=%d]" % minh if minh >= 1080 else "bestvideo"
        M7 = "bestvideo[height>=720]"
        A1, A2 = "bestaudio[ext=m4a]", "bestaudio[acodec^=mp4a]"
        cands = []
        if minh >= 1080:
            cands += ["%s+%s" % (H, A1), "%s+%s" % (H, A2),
                      "%s+%s" % (M7, A1), "%s+%s" % (M7, A2)]
        cands += ["bestvideo+%s" % A1, "bestvideo+%s" % A2,
                  "bestvideo+bestaudio", "best"]
        fmt = "/".join(cands)

        args = base_args(cfg) + [
            "-f", fmt,
            "--merge-output-format", "mp4",
            "--no-write-subs", "--no-write-auto-subs",
            "--no-write-thumbnail", "--no-write-description",
            "--windows-filenames",
            "--newline",                       # 让进度逐行输出，便于解析
            "--progress",
            "-o", os.path.join(dest_dir, "%(title).120B [%(id)s].%(ext)s"),
            "https://www.youtube.com/watch?v=" + vid,
        ]
        if adv.get("keep_video", True):
            args.append("--keep-video")

        with _TASK_LOCK:
            _TASK["stage"] = "下载中"

        proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, encoding="utf-8", errors="replace",
                                env=common.env_no_proxy(), bufsize=1)

        last_target = ""
        for line in proc.stdout:
            if _STOP["flag"]:
                proc.terminate()
                break
            line = line.rstrip()
            if not line:
                continue
            # 目标文件名
            m = re.search(r"Destination:\s*(.+)$", line)
            if m:
                last_target = m.group(1).strip()
            # 进度
            m = re.search(r"\[download\]\s+([\d.]+)%\s+of\s+\S+\s+at\s+(\S+)\s+ETA\s+(\S+)", line)
            if m:
                with _TASK_LOCK:
                    _TASK["percent"] = float(m.group(1))
                    _TASK["speed"] = m.group(2)
                    _TASK["eta"] = m.group(3)
            elif "[download] 100%" in line:
                with _TASK_LOCK:
                    _TASK["percent"] = 100.0
            # 合并阶段
            if "[Merger]" in line or "Merging formats" in line:
                with _TASK_LOCK:
                    _TASK["stage"] = "合并音视频"
                    _TASK["percent"] = 99.0
            # 标题
            mt = re.search(r"\[youtube\]\s+%s:\s+Downloading.*?\"(.+?)\"" % vid, line)
            if mt:
                with _TASK_LOCK:
                    _TASK["title"] = mt.group(1)

        proc.wait()

        # 清理中间流（移到隔离区，不删除）
        _sweep_intermediates(dest_dir)

        # 找成品
        found = ""
        if last_target and os.path.exists(last_target):
            found = last_target
        else:
            cands = [f for f in os.listdir(dest_dir)
                     if vid in f and f.endswith(".mp4") and not re.search(r"\.f\d+\.", f)]
            if cands:
                found = os.path.join(dest_dir, cands[0])

        with _TASK_LOCK:
            if _STOP["flag"]:
                _TASK["stage"] = "已取消"
                _TASK["error"] = "用户取消"
            elif found:
                h, w = 0, 0
                try:
                    from . import download as _dl
                    info = _dl.probe_media(found)
                    h, w = info.get("height", 0), info.get("width", 0)
                except Exception:
                    pass
                note = ""
                if h and h < 1080:
                    note = "该视频源站最高只有 %dp，已按最高可用下载" % h
                # 标题优先用解析阶段拿到的；没有就从文件名去掉 [id].mp4 后缀
                clean = re.sub(r"\s*\[[A-Za-z0-9_-]{11}\]\.mp4$", "",
                               os.path.basename(found))
                _TASK.update({"stage": "完成", "file": found.replace("\\", "/"),
                              "percent": 100.0, "title": _TASK["title"] or clean,
                              "res": ("%dx%d" % (w, h)) if h else "", "note": note})
            else:
                _TASK["stage"] = "失败"
                _TASK["error"] = ("没有生成成品文件。若下载被中断（如服务重启/手动取消），"
                                  "目录里可能残留 .part 文件，已自动移到 _quarantine")
    except Exception as e:
        with _TASK_LOCK:
            _TASK["stage"] = "失败"
            _TASK["error"] = str(e)[:200]
    finally:
        with _TASK_LOCK:
            _TASK["running"] = False


def _sweep_intermediates(d):
    """把中间文件移到隔离区（只移不删）

    ★ 2026-10-23 补：原来只扫 .fXXX 分离流，漏了 .part。
      用户遇到的现象：下载中途服务重启 → 目录里留下
      "xxx.f399.mp4.part"（10MB，无音轨、无容器尾）→ 双击打不开。
      现在 .part / .ytdl 也一并移入隔离区。
    """
    q = d.rstrip("/\\") + "_quarantine"
    pats = (r"\.f\d+\.(mp4|webm|m4a)$", r"\.part$", r"\.ytdl$")
    for f in os.listdir(d):
        if any(re.search(p, f) for p in pats):
            try:
                os.makedirs(q, exist_ok=True)
                dst = os.path.join(q, f)
                if os.path.exists(dst):
                    dst = os.path.join(q, "dup_" + f)
                shutil.move(os.path.join(d, f), dst)
            except Exception:
                pass