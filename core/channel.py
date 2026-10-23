#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""channel：频道解析（流式，可看进度）

与 scan.py 的区别：
  scan.py 是"跑完才返回"，几百个视频要等好几分钟，界面一片空白。
  这里改成边跑边收集，前端能看到「已解析 N 个」的实时数字。

★ 关于文件大小：YouTube 的 flat-playlist 模式不返回 filesize，
  逐个视频去查格式大小会让解析慢 10 倍（779 × 8 秒 ≈ 1.7 小时）。
  所以用「时长 × 典型码率」估算，并明确标注是预估。
  典型值来自实测：AV1 1080p ≈ 550kbps，AAC 音频 ≈ 128kbps，合计 ≈ 678kbps。
"""
import os, re, sys, json, subprocess, threading, time
from . import common

# ---------------- 解析任务状态 ----------------
_SCAN = {
    "running": False,
    "url": "",
    "stage": "",          # 准备中 / 解析中 / 完成 / 失败
    "count": 0,           # 已获取条数
    "expected": 0,        # 预估总数（能拿到就用）
    "items": [],          # [{id,title,dur,size_mb}]
    "error": "",
    "started": 0,
    "elapsed": 0,
}
_SCAN_LOCK = threading.Lock()
_SCAN_STOP = {"flag": False}

# 平均码率（kbps）：AV1 1080p + AAC
AVG_KBPS = 678


def scan_state(with_items=True, limit=2000):
    with _SCAN_LOCK:
        d = dict(_SCAN)
        d["elapsed"] = int(time.time() - d["started"]) if d["started"] else 0
        if with_items:
            d["items"] = d["items"][:limit]
        else:
            d["items"] = []
        d["count"] = len(_SCAN["items"])
        return d


def stop_scan():
    _SCAN_STOP["flag"] = True


def _est_size_mb(duration):
    try:
        sec = float(duration)
    except (TypeError, ValueError):
        return 0
    if sec <= 0:
        return 0
    return round(sec * AVG_KBPS / 8 / 1024, 1)


def _build_args(cfg, url):
    net = cfg["network"]; adv = cfg["advanced"]
    args = [common.py(), "-m", "yt_dlp", "--flat-playlist", "--no-warnings"]
    if net.get("proxy_enabled") and net.get("proxy"):
        args += ["--proxy", net["proxy"]]
    deno = common.find_deno(cfg)
    if deno:
        args += ["--js-runtimes", "deno:" + deno]
    extra = "youtube:player_client=" + adv.get("player_client", "mweb,tv,web,ios")
    if net.get("pot_server"):
        extra += ";youtubepot-bgutilhttp:base_url=" + net["pot_server"]
    args += ["--extractor-args", extra]
    args += ["--print", "%(id)s\t%(duration)s\t%(title)s", url]
    return args


def start_scan(cfg, url):
    """启动后台解析。返回 (ok, msg)"""
    with _SCAN_LOCK:
        if _SCAN["running"]:
            return False, "已有解析在进行"
        if not url:
            return False, "请填写频道地址"
        _SCAN.update({
            "running": True, "url": url, "stage": "准备中", "count": 0,
            "expected": 0, "items": [], "error": "", "started": time.time(),
        })
        _SCAN_STOP["flag"] = False
    threading.Thread(target=_worker, args=(cfg, url), daemon=True).start()
    return True, "已开始解析"


def _worker(cfg, url):
    items = []
    try:
        with _SCAN_LOCK:
            _SCAN["stage"] = "解析中"
        args = _build_args(cfg, url)
        proc = subprocess.Popen(args, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                                text=True, encoding="utf-8", errors="replace",
                                env=common.env_no_proxy(), bufsize=1)

        buf = []
        for line in proc.stdout:
            if _SCAN_STOP["flag"]:
                proc.terminate()
                break
            line = line.rstrip("\n")
            if not line:
                continue
            p = line.split("\t")
            if len(p) < 3:
                continue
            vid = p[0].strip()
            if not re.fullmatch(r"[A-Za-z0-9_-]{11}", vid):
                continue
            dur = 0
            try:
                dur = float(p[1]) if p[1] not in ("NA", "None", "") else 0
            except ValueError:
                dur = 0
            title = "\t".join(p[2:]).strip()
            items.append({
                "id": vid,
                "title": title,
                "dur": int(dur),
                "dur_text": ("%d:%02d" % (int(dur)//60, int(dur) % 60)) if dur else "",
                "size_mb": _est_size_mb(dur),
            })
            # 每 5 条更新一次状态，减少锁竞争
            if len(items) % 5 == 0:
                with _SCAN_LOCK:
                    _SCAN["items"] = list(items)
                    _SCAN["count"] = len(items)
            buf.append(vid)

        proc.wait()
        err = (proc.stderr.read() or "") if proc.stderr else ""

        with _SCAN_LOCK:
            _SCAN["items"] = items
            _SCAN["count"] = len(items)
            if _SCAN_STOP["flag"]:
                _SCAN["stage"] = "已取消"
            elif items:
                _SCAN["stage"] = "完成"
                # 顺手落一份清单，供后续下载使用
                try:
                    out_dir = cfg["output_dir"]
                    os.makedirs(out_dir, exist_ok=True)
                    with open(os.path.join(out_dir, "videos.txt"), "w", encoding="utf-8") as f:
                        for it in items:
                            f.write("%s|%s|0|%s\n" % (it["id"], it["dur"], it["title"]))
                except Exception:
                    pass
            else:
                _SCAN["stage"] = "失败"
                _SCAN["error"] = (err.strip().split("\n")[-1][:160] if err.strip()
                                  else "没有解析到任何视频，请检查频道地址或代理")
    except Exception as e:
        with _SCAN_LOCK:
            _SCAN["stage"] = "失败"
            _SCAN["error"] = str(e)[:200]
    finally:
        with _SCAN_LOCK:
            _SCAN["running"] = False
