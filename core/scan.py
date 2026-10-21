#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""scan：把频道/播放列表展开成「ID|时长|播放量|标题」清单。

为什么单独做这一步：
  频道有几百上千个视频，边扫边下会导致「下到一半才发现清单不全」。
  先落一份完整清单，后续下载/歌词/报表都以它为唯一事实源。
"""
import os, re, json, subprocess
from . import common

LIST_NAME = "videos.txt"


def list_path(out_dir):
    return os.path.join(out_dir, LIST_NAME)


def build_args(cfg):
    net = cfg["network"]
    args = [common.py(), "-m", "yt_dlp", "--flat-playlist", "--no-warnings"]
    if net.get("proxy_enabled") and net.get("proxy"):
        args += ["--proxy", net["proxy"]]
    deno = common.find_deno(cfg)
    if deno:
        args += ["--js-runtimes", "deno:" + deno]
    pot = net.get("pot_server")
    client = cfg["advanced"].get("player_client", "mweb,tv,web,ios")
    extra = "youtube:player_client=" + client
    if pot:
        extra += ";youtubepot-bgutilhttp:base_url=" + pot
    args += ["--extractor-args", extra]
    return args


def scan(cfg, url=None, limit=0):
    """返回 (清单路径, 视频数)"""
    url = url or cfg.get("channel_url") or ""
    if not url:
        common.log("未配置频道 URL", "ERROR")
        return None, 0
    out_dir = cfg["output_dir"]
    os.makedirs(out_dir, exist_ok=True)
    lp = list_path(out_dir)

    common.log("开始扫描清单: %s" % url)
    common.write_state(stage="scan", running=True, total=0, done=0)

    fmt = "%(id)s|%(duration)s|%(view_count)s|%(title)s"
    args = build_args(cfg) + ["--print", fmt]
    if limit:
        args += ["--playlist-end", str(limit)]
    args.append(url)

    try:
        r = subprocess.run(args, capture_output=True, text=True,
                           env=common.env_no_proxy(), timeout=1800,
                           encoding="utf-8", errors="replace")
        out = r.stdout or ""
        err = r.stderr or ""
    except Exception as e:
        common.log("扫描失败: %s" % e, "ERROR")
        return None, 0

    rows = []
    for line in out.split("\n"):
        line = line.strip()
        if not line or "|" not in line:
            continue
        p = line.split("|")
        if len(p) < 4 or not re.fullmatch(r"[A-Za-z0-9_-]{11}", p[0]):
            continue
        rows.append(p)

    if not rows:
        common.log("扫描到 0 个视频，检查 URL / 代理 / 网络", "ERROR")
        if err:
            common.log(err.strip().split("\n")[-1][:200], "ERROR")
        return None, 0

    # 去重保序
    seen, uniq = set(), []
    for p in rows:
        if p[0] in seen:
            continue
        seen.add(p[0])
        uniq.append(p)

    with open(lp, "w", encoding="utf-8") as f:
        for p in uniq:
            f.write("|".join(p) + "\n")

    common.log("清单完成: %d 个视频 -> %s" % (len(uniq), lp))
    common.write_state(stage="scan", running=False, total=len(uniq), done=0)
    return lp, len(uniq)


def read_list(out_dir):
    """读取清单，返回 [(id, duration, views, title)]"""
    lp = list_path(out_dir)
    if not os.path.exists(lp):
        return []
    rows = []
    for line in open(lp, encoding="utf-8", errors="replace"):
        p = line.strip().split("|")
        if len(p) >= 4 and re.fullmatch(r"[A-Za-z0-9_-]{11}", p[0]):
            rows.append((p[0], p[1], p[2], "|".join(p[3:])))
    return rows
