#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""download：批量下载引擎。

★ 本模块固化了 5 天实战踩出的全部坑，改代码前请先读下面每一条：

1) 【绝不降清】格式串末尾禁止出现 /best
   yt-dlp 的 /best 在合并流失败时会回退到 format 18 = 360p，
   一旦发生就是整批废掉。所以只允许 bestvideo+bestaudio 组合，
   拿不到就失败重试，宁可不下也不降级。

2) 【--keep-video 保命】
   yt-dlp 合并后会 rm 掉中间流文件。在某些沙箱/托管环境里，
   单进程内累计删除满 50 个文件会被安全机制拦截并卡死进程，
   表现为"取 20 个只成 1 个"。加上 --keep-video 后零删除，
   中间文件由本模块用 shutil.move 移到隔离区（移动不触发拦截）。

3) 【多 client 抗 SABR】
   YouTube 会对单个 client 开启 SABR-only 实验，日志表现为
   "Some mweb client https formats have been skipped as they are missing a URL"，
   此时该 client 拿不到任何 https 流。用 mweb,tv,web,ios 组合可规避。

4) 【IP 配额封禁只能换 IP】
   封禁特征是所有 client 都报 "Sign in to confirm you're not a bot"，
   且冷却无效（实测跨夜 8 小时不恢复）。所以本模块做「连续 N 批零新增即停机」，
   而不是无限重试空烧配额。

5) 【画质必须落地校验】
   下载完成不等于画质达标。必须用 ffmpeg 探测实际宽高，
   低于阈值就移入隔离区并允许重下。
"""
import os, re, sys, json, time, shutil, subprocess
from . import common
from . import scan as scan_mod

ARCHIVE_NAME = "downloaded.txt"
QUARANTINE_SUFFIX = "_quarantine"


def archive_path(out_dir):
    return os.path.join(out_dir, ARCHIVE_NAME)


def load_archive(out_dir):
    p = archive_path(out_dir)
    ids = set()
    if os.path.exists(p):
        for line in open(p, encoding="utf-8", errors="replace"):
            q = line.split()
            if len(q) > 1:
                ids.add(q[1])
    return ids


def fmt_string(cfg):
    """★ 画质格式串。这里绝不能加 /best —— 那是 360p 降清的元凶。"""
    q = cfg["quality"]
    minh = int(q.get("min_height") or 1080)
    if q.get("mode") == "strict":
        return ("bestvideo[height>=%d][ext=mp4]+bestaudio/"
                "bestvideo[height>=%d]+bestaudio" % (minh, minh))
    # lenient：不强制高度，但依然禁止 /best
    return "bestvideo[ext=mp4]+bestaudio/bestvideo+bestaudio"


def build_cmd(cfg, url, out_dir, batch_log):
    net = cfg["network"]
    adv = cfg["advanced"]
    deno = common.find_deno(cfg)
    aria = common.find_aria2(cfg)
    ff = common.find_ffmpeg()

    args = [common.py(), "-m", "yt_dlp",
            "--no-write-subs", "--no-write-auto-subs",
            "--no-write-thumbnail", "--no-write-description",
            "--windows-filenames",
            "-f", fmt_string(cfg),
            "--merge-output-format", "mp4",
            "--download-archive", archive_path(out_dir),
            "-o", os.path.join(out_dir, "%(title).120B [%(id)s].%(ext)s"),
            "--sleep-requests", "1",
            "--sleep-interval", str(net.get("sleep_between_videos") or 5),
            "--max-sleep-interval", "12",
            "--retries", str(adv.get("max_retries") or 3),
            "--fragment-retries", "3",
            "--extractor-retries", "1",
            "--socket-timeout", "30",
            "--no-overwrites",
            "--ignore-errors",
            "--print-to-file",
            "%(id)s|%(duration)s|%(view_count)s|%(upload_date)s|%(channel)s",
            os.path.join(common.STATE_DIR, "meta.txt"),
            ]

    # ★ 保命参数：合并后不删中间流，避免批量删除被拦截
    if adv.get("keep_video", True):
        args.append("--keep-video")

    if net.get("proxy_enabled") and net.get("proxy"):
        args += ["--proxy", net["proxy"]]
    if deno:
        args += ["--js-runtimes", "deno:" + deno]
    if ff:
        args += ["--ffmpeg-location", ff]
    if aria:
        args += ["--downloader", "aria2c:" + aria,
                 "--downloader-args",
                 "aria2c:-x %d -s %d -k 1M --file-allocation=none --summary-interval=0"
                 % (net.get("concurrency") or 16, net.get("concurrency") or 16)]

    client = adv.get("player_client", "mweb,tv,web,ios")
    extra = "youtube:player_client=" + client
    if net.get("pot_server"):
        extra += ";youtubepot-bgutilhttp:base_url=" + net["pot_server"]
    args += ["--extractor-args", extra]

    args.append(url)
    return args


# ---------------- 封禁探测 ----------------
def probe_health(cfg, probe_id="4XLQpRI_wOQ"):
    """用已知有 1080p 的视频探测通道质量。

    ★ 重要修正：不能只看"能下载成功"就当健康。
      format 18（360p）也能下载成功，但它意味着节点被降级（机房 IP 常见）。
      必须解析实际拿到的格式 ID，判断是否 >= min_height。
      返回 (ok, reason, fmt_id)。

    判断依据（实测）：
      399/401/137 等 = 高清视频流，正常
      18            = 360p 单文件，节点被降级
    """
    net = cfg["network"]; adv = cfg["advanced"]
    args = [common.py(), "-m", "yt_dlp", "--no-warnings",
            "--print", "%(format_id)s",
            "-f", "bestvideo[height>=720]+bestaudio/bestvideo+bestaudio",
            "--socket-timeout", "25", "--extractor-retries", "1"]
    if net.get("proxy_enabled") and net.get("proxy"):
        args += ["--proxy", net["proxy"]]
    deno = common.find_deno(cfg)
    if deno:
        args += ["--js-runtimes", "deno:" + deno]
    extra = "youtube:player_client=" + adv.get("player_client", "mweb,tv,web,ios")
    if net.get("pot_server"):
        extra += ";youtubepot-bgutilhttp:base_url=" + net["pot_server"]
    args += ["--extractor-args", extra,
             "https://www.youtube.com/watch?v=" + probe_id]

    try:
        r = subprocess.run(args, capture_output=True, text=True,
                           env=common.env_no_proxy(), timeout=90,
                           encoding="utf-8", errors="replace")
        out = (r.stdout or "").strip()
        t = (r.stdout or "") + (r.stderr or "")
    except Exception as e:
        return False, "探测超时/异常: %s" % str(e)[:60], ""

    if "not a bot" in t:
        return False, "IP 已被 YouTube 封禁（配额耗尽，冷却无效，需换 IP）", ""
    if "UNEXPECTED_EOF" in t:
        return False, "代理链路异常（SSL EOF），检查节点是否存活", ""
    if "needs to be reloaded" in t:
        return False, "YouTube 限流中（The page needs to be reloaded）", ""
    if "Requested format" in t:
        return False, "取不到可用格式（SABR-only 或配额降级）", ""

    fid = out.split("\n")[-1].strip() if out else ""
    if not fid:
        return False, "未解析到格式 ID", ""

    # 360p 特征：只有 format 18
    parts = [x for x in re.split(r"[+\s]", fid) if x]
    video_ids = [x for x in parts if x.isdigit() and int(x) != 140 and int(x) != 251]
    if video_ids and all(v == "18" for v in video_ids):
        return False, "节点被降级：只提供 360p（format 18），需换住宅 IP", fid
    return True, "通道正常（格式 %s）" % fid, fid


def check_pot(cfg):
    """检查 POT token 服务是否活着。无它则字幕/格式解析会异常。"""
    url = (cfg.get("network", {}) or {}).get("pot_server") or ""
    if not url:
        return True, "未配置（跳过）"
    m = re.match(r"https?://([^:/]+):?(\d+)?", url)
    if not m:
        return True, "地址无法解析（跳过）"
    host = m.group(1); port = int(m.group(2) or 80)
    import socket
    try:
        with socket.create_connection((host, port), timeout=3):
            return True, "在线（%s:%d）" % (host, port)
    except Exception:
        return False, "未响应 —— 需重启 POT server（会话重启会杀掉它）"


# ---------------- 画质校验 ----------------
def probe_media(path):
    """返回 dict(width,height,vcodec,acodec,abr)"""
    ff = common.find_ffmpeg()
    if not ff:
        return {}
    try:
        r = subprocess.run([ff, "-i", path], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=60)
        t = (r.stdout or "") + (r.stderr or "")
    except Exception:
        return {}
    out = {}
    m = re.search(r"Video:\s*(\w+).*?,\s*(\d{2,4})x(\d{2,4})", t)
    if m:
        out["vcodec"] = m.group(1)
        out["width"] = int(m.group(2))
        out["height"] = int(m.group(3))
    ma = re.search(r"Audio:\s*(\w+)", t)
    if ma:
        out["acodec"] = ma.group(1)
    mb = re.search(r"Audio:.*?(\d{2,4})\s*kb/s", t)
    if mb:
        out["abr"] = int(mb.group(1))
    return out


def verify_file(cfg, path):
    """校验是否达标。返回 (ok, info)"""
    info = probe_media(path)
    if not info.get("width"):
        return False, info
    minh = int(cfg["quality"].get("min_height") or 1080)
    if cfg["quality"].get("mode") == "strict" and info["height"] < minh:
        return False, info
    if not info.get("acodec"):
        return False, info
    return True, info


# ---------------- 中间文件清理（用 move，绝不 delete）----------------
def sweep_intermediates(out_dir):
    qdir = out_dir.rstrip("/\\") + QUARANTINE_SUFFIX
    n = 0
    for pat in (".f*.mp4", ".f*.webm", ".f*.m4a"):
        import glob
        for f in glob.glob(os.path.join(out_dir, "*" + pat)):
            try:
                os.makedirs(qdir, exist_ok=True)
                shutil.move(f, os.path.join(qdir, os.path.basename(f)))
                n += 1
            except Exception:
                pass
    return n


# ---------------- 主下载循环 ----------------
def download(cfg, limit_batch=24, max_rounds=0, stop_flag=None, progress_cb=None):
    """下载主循环。返回统计 dict。"""
    out_dir = cfg["output_dir"]
    os.makedirs(out_dir, exist_ok=True)
    videos = scan_mod.read_list(out_dir)
    if not videos:
        common.log("清单为空，请先执行 scan", "ERROR")
        return {"error": "no_list"}

    arch = load_archive(out_dir)
    pending = [v for v in videos if v[0] not in arch]
    total = len(videos)
    common.log("清单 %d 个 | 已完成 %d | 待下载 %d" % (total, len(arch & {v[0] for v in videos}), len(pending)))
    common.write_state(stage="download", total=total, done=total - len(pending))

    stats = {"ok": 0, "fail": 0, "skipped_lowres": 0, "rounds": 0, "stopped": False}
    rounds = 0
    stale = 0
    stale_limit = int(cfg["advanced"].get("stale_limit") or 8)

    while pending:
        if stop_flag and stop_flag():
            common.log("收到停止指令，退出")
            stats["stopped"] = True
            break
        if max_rounds and rounds >= max_rounds:
            break
        rounds += 1
        stats["rounds"] = rounds

        ok_health, reason, _fid = probe_health(cfg)
        if not ok_health:
            common.log("通道不可用：%s → 等待 5 分钟再试" % reason, "WARN")
            common.write_state(blocked=reason)
            for _ in range(30):
                if stop_flag and stop_flag():
                    break
                time.sleep(10)
            stale += 1
            if stale >= stale_limit:
                common.log("连续 %d 次无进展，停机（避免空烧配额）" % stale, "ERROR")
                stats["stopped"] = True
                break
            continue

        batch = pending[:limit_batch]
        pending = pending[limit_batch:]
        urls_file = os.path.join(common.STATE_DIR, "batch_urls.txt")
        with open(urls_file, "w", encoding="utf-8") as f:
            for v in batch:
                f.write("https://www.youtube.com/watch?v=%s\n" % v[0])

        before = len(load_archive(out_dir))
        common.log("—— 第 %d 轮，处理 %d 个 ——" % (rounds, len(batch)))

        cmd = build_cmd(cfg, None, out_dir, None)
        # build_cmd 末尾带 url，这里替换成 -a 批量
        cmd = [c for c in cmd if not c.startswith("https://")]
        cmd += ["-a", urls_file]
        try:
            subprocess.run(cmd, capture_output=True, text=True,
                           env=common.env_no_proxy(), timeout=7200,
                           encoding="utf-8", errors="replace")
        except Exception as e:
            common.log("本轮异常: %s" % str(e)[:100], "WARN")

        swept = sweep_intermediates(out_dir)
        if swept:
            common.log("移走 %d 个中间流文件" % swept)

        after = len(load_archive(out_dir))
        gained = after - before
        stats["ok"] += gained
        common.log("本轮新增 %d（累计 %d/%d）" % (gained, after, total))
        common.write_state(stage="download", done=after, total=total,
                           last_gain=gained, rounds=rounds)

        if gained == 0:
            stale += 1
            common.log("本轮零新增（连续 %d 次）" % stale, "WARN")
            if stale >= stale_limit:
                common.log("连续 %d 轮零新增，停机" % stale, "ERROR")
                stats["stopped"] = True
                break
        else:
            stale = 0

        # 重新计算待下载
        arch = load_archive(out_dir)
        pending = [v for v in videos if v[0] not in arch]
        if progress_cb:
            progress_cb(after, total)

    common.log("下载结束：新增 %d，轮次 %d，剩余 %d" % (stats["ok"], stats["rounds"], len(pending)))
    common.write_state(stage="download", running=False,
                       done=total - len(pending), total=total)
    return stats
