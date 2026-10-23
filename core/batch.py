#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""batch：频道批量下载任务（按勾选 + 多输出）

流程：
  1. 只下载前端勾选的视频（only_ids）
  2. 下完后按需派生「无音轨」「音频」
  3. 全程可通过 batch_state() 查进度

设计取舍：
  - 清晰度不设门槛，统一按最高（用户 2026-10-23 明确要求）
  - 派生用 ffmpeg -c copy，不重新编码画面
"""
import os, re, glob, time, threading, subprocess
from . import common
from . import download as dl

_B = {
    "running": False,
    "stage": "",
    "total": 0,
    "done": 0,
    "outputs": [],
    "detail": "",
    "error": "",
    "started": 0,
    "elapsed": 0,
}
_LOCK = threading.Lock()
_STOP = {"flag": False}


def state():
    with _LOCK:
        d = dict(_B)
        d["elapsed"] = int(time.time() - d["started"]) if d["started"] else 0
        return d


def stop():
    _STOP["flag"] = True
    with _LOCK:
        _B["detail"] = "正在停止…"


def find_output(out_dir, vid):
    """在输出目录找某个视频的成品 mp4（排除中间流/派生文件）"""
    for f in glob.glob(os.path.join(out_dir, "*[[]%s[]].mp4" % vid)):
        b = os.path.basename(f)
        if re.search(r"\.f\d+(-\d+)?\.", b):
            continue
        if b.endswith("_无音轨.mp4"):
            continue
        return f
    return ""


def ffmpeg_make(ff, src, dst, video=True):
    if not ff:
        return False
    if video:
        cmd = [ff, "-y", "-i", src, "-an", "-c:v", "copy", "-movflags", "+faststart", dst]
    else:
        cmd = [ff, "-y", "-i", src, "-vn", "-c:a", "copy", dst]
    try:
        subprocess.run(cmd, capture_output=True, text=True, timeout=1800,
                       encoding="utf-8", errors="replace")
        if os.path.exists(dst) and os.path.getsize(dst) > 10000:
            return True
        # ★ copy 失败兜底：源音频是 Opus 时无法直接塞进 m4a，必须转码
        if not video:
            subprocess.run([ff, "-y", "-i", src, "-vn", "-c:a", "aac", "-b:a", "192k", dst],
                           capture_output=True, text=True, timeout=1800,
                           encoding="utf-8", errors="replace")
            return os.path.exists(dst) and os.path.getsize(dst) > 10000
        return False
    except Exception:
        return False


def start(cfg, ids, outputs):
    """启动批量下载。返回 (ok, msg)"""
    with _LOCK:
        if _B["running"]:
            return False, "已有批量任务在进行"
        if not ids:
            return False, "没有勾选任何视频"
        ids = [x for x in ids if re.fullmatch(r"[A-Za-z0-9_-]{11}", x)]
        if not ids:
            return False, "勾选的视频 ID 无效"
        outs = [o for o in (outputs or []) if o in ("video", "noaudio", "audio")]
        if not outs:
            outs = ["video"]
        _B.update({
            "running": True, "stage": "准备中", "total": len(ids), "done": 0,
            "outputs": outs, "detail": "", "error": "", "started": time.time(),
        })
        _STOP["flag"] = False
    threading.Thread(target=_worker, args=(cfg, ids, outs), daemon=True).start()
    return True, "已开始"


def _worker(cfg, ids, outs):
    out_dir = cfg["output_dir"]
    try:
        # ── 1. 下载 ──
        with _LOCK:
            _B["stage"] = "下载视频"
            _B["detail"] = "共 %d 个" % len(ids)

        # ★ 进度不能只靠 download 的 progress_cb —— 它只在"整轮结束"时回调一次，
        #   少量视频时很久都不动（实测 2 个视频 2 分钟进度还是 0/2）。
        #   改为独立线程每 2 秒扫一次归档，实时反映已完成数。
        _mon = threading.Event()

        def _monitor():
            idset = set(ids)
            while not _mon.wait(2):
                try:
                    done = len(dl.load_archive(out_dir) & idset)
                    with _LOCK:
                        _B["done"] = done
                        if done >= _B["total"]:
                            _B["stage"] = "下载完成"
                except Exception:
                    pass

        # ★ 把本次勾选的清单落到目标目录，供后续「抓歌词 / 生成 Excel」使用。
        #   否则用户换了保存目录后，这两个功能会因为找不到 videos.txt 而报"清单为空"。
        #   若目录已有清单，则合并去重（保留原有条目）。
        try:
            # ★ 必须先建目录：用户可能选一个还没建的新文件夹，
            #   而 os.makedirs 原本在 dl.download() 内部才执行，
            #   导致这里 open(...,'w') 直接 Errno 2（实测踩过）。
            os.makedirs(out_dir, exist_ok=True)
            vl = os.path.join(out_dir, "videos.txt")
            exist = {}
            if os.path.exists(vl):
                for line in open(vl, encoding="utf-8", errors="replace"):
                    q = line.strip().split("|")
                    if len(q) >= 4 and re.fullmatch(r"[A-Za-z0-9_-]{11}", q[0]):
                        exist[q[0]] = line.strip()
            for vid in ids:
                exist.setdefault(vid, "%s||0|" % vid)
            with open(vl, "w", encoding="utf-8") as f:
                for line in exist.values():
                    f.write(line + "\n")
            common.log("已写入清单 %d 条 -> %s" % (len(exist), vl))
        except Exception as e:
            common.log("写清单失败：%s" % str(e)[:80], "WARN")

        threading.Thread(target=_monitor, daemon=True).start()
        try:
            dl.download(cfg, only_ids=ids, stop_flag=lambda: _STOP["flag"])
        except Exception as e:
            common.log("批量下载异常：%s" % str(e)[:120], "WARN")
        finally:
            _mon.set()

        if _STOP["flag"]:
            with _LOCK:
                _B["stage"] = "已取消"
            return

        # ── 2. 派生 ──
        want_noaudio = "noaudio" in outs
        want_audio = "audio" in outs
        if want_noaudio or want_audio:
            ff = common.find_ffmpeg()
            n_ok = 0
            for i, vid in enumerate(ids, 1):
                if _STOP["flag"]:
                    break
                src = find_output(out_dir, vid)
                if not src:
                    continue
                stem = os.path.splitext(src)[0]
                with _LOCK:
                    _B["stage"] = "生成附加格式"
                    _B["detail"] = "%d / %d" % (i, len(ids))
                if want_noaudio:
                    out = stem + "_无音轨.mp4"
                    if not os.path.exists(out) and ffmpeg_make(ff, src, out, True):
                        n_ok += 1
                if want_audio:
                    out = stem + ".m4a"
                    if not os.path.exists(out) and ffmpeg_make(ff, src, out, False):
                        n_ok += 1
            common.log("附加格式生成完成：%d 个" % n_ok)

        with _LOCK:
            _B["stage"] = "完成" if not _STOP["flag"] else "已取消"
            _B["detail"] = ""
    except Exception as e:
        with _LOCK:
            _B["stage"] = "失败"
            _B["error"] = str(e)[:200]
    finally:
        with _LOCK:
            _B["running"] = False
