#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""sss-toolkit 命令行入口

用法：
    python sss.py check            体检环境（依赖/代理/通道）
    python sss.py scan             扫描频道生成清单
    python sss.py download         下载（可反复跑，断点续传）
    python sss.py lyrics           抓官方歌词 + 算难度
    python sss.py lyrics-desc      对没字幕的视频从「视频简介」提取歌词（回退路径）
    python sss.py report           生成 Excel
    python sss.py all              一条龙：scan → download → lyrics → report

想改频道/画质/路径，改 config.json 即可，不用动代码。
"""
import os, sys, argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core import common, scan as scan_mod, download as dl, lyrics as lyr, report as rep


def cmd_check(cfg, quick=False):
    """环境体检。quick=True 时只输出关键行（供巡查，约 150 tokens）。"""
    rows = []

    # 1) POT 服务
    pot_ok, pot_msg = dl.check_pot(cfg)
    rows.append(("POT服务", pot_ok, pot_msg))

    # 2) 工具链
    ff = common.find_ffmpeg(); deno = common.find_deno(cfg); aria = common.find_aria2(cfg)
    rows.append(("ffmpeg", bool(ff), "OK" if ff else "缺失（合并必需）"))
    if not quick:
        rows.append(("deno", bool(deno), deno or "缺失（影响 JS challenge）"))
        rows.append(("aria2c", bool(aria), "OK" if aria else "缺失（影响速度）"))

    # 3) Python 依赖
    try:
        import openpyxl  # noqa
        rows.append(("openpyxl", True, "OK"))
    except ImportError:
        rows.append(("openpyxl", False, "缺失：pip install openpyxl"))

    # 4) 输出目录
    od = cfg["output_dir"]
    try:
        os.makedirs(od, exist_ok=True)
        t = os.path.join(od, ".wtest"); open(t, "w").write("1"); os.remove(t)
        rows.append(("输出目录", True, od))
    except Exception as e:
        rows.append(("输出目录", False, "%s 不可写: %s" % (od, str(e)[:40])))

    # 5) 通道质量（关键：能识破 360p 降级）
    ok_h, msg_h, fid = dl.probe_health(cfg)
    rows.append(("节点质量", ok_h, msg_h))

    all_ok = all(r[1] for r in rows)

    if quick:
        # 极简输出：每行一条，最后一行结论
        for name, ok, msg in rows:
            print("%-10s %s  %s" % (name, "OK  " if ok else "FAIL", msg))
        print("→ %s" % ("PASS" if all_ok else "FAIL：先处理上面 FAIL 项，别急着开跑"))
        return 0 if all_ok else 1

    # 详细模式
    print("=" * 58)
    print("环境体检")
    print("=" * 58)
    print("\nPython: %s" % sys.version.split()[0])
    for name, ok, msg in rows:
        print("  %s %-10s %s" % ("[OK]  " if ok else "[FAIL]", name, msg))
    print("\n" + "=" * 58)
    print("结论：" + ("全部通过，可以开始" if all_ok else "有问题，先按上面提示处理"))
    if not all_ok:
        print("\n提示：详见 PREFLIGHT.md（开工前必读）")
    return 0 if all_ok else 1


def cmd_scan(cfg, args):
    lp, n = scan_mod.scan(cfg, url=args.url, limit=args.limit)
    return 0 if lp else 1


def cmd_download(cfg, args):
    st = dl.download(cfg, limit_batch=args.batch, max_rounds=args.rounds)
    return 0 if not st.get("error") else 1


def cmd_lyrics(cfg, args):
    lyr.fetch(cfg, batch=args.batch, limit=args.limit)
    return 0


def cmd_lyrics_desc(cfg, args):
    lyr.fetch_desc_fallback(cfg, batch=8, limit=args.limit)
    return 0


def cmd_report(cfg, args):
    out = rep.build(cfg)
    return 0 if out else 1


def main():
    ap = argparse.ArgumentParser(description="sss-toolkit：频道资料库一键构建")
    ap.add_argument("command", nargs="?", default="all",
                    choices=["check", "scan", "download", "lyrics", "lyrics-desc", "report", "all"])
    ap.add_argument("--url", help="频道/播放列表 URL（默认读 config.json）")
    ap.add_argument("--limit", type=int, default=0, help="只处理前 N 个（调试用）")
    ap.add_argument("--batch", type=int, default=24, help="每批数量")
    ap.add_argument("--rounds", type=int, default=0, help="最多跑几轮（0=不限制）")
    ap.add_argument("--quick", action="store_true", help="体检只输出关键行（巡查用，省 token）")
    args = ap.parse_args()

    cfg = common.load_config()
    cmd = args.command

    if cmd == "check":
        return cmd_check(cfg, quick=args.quick)
    if cmd == "scan":
        return cmd_scan(cfg, args)
    if cmd == "download":
        return cmd_download(cfg, args)
    if cmd == "lyrics":
        return cmd_lyrics(cfg, args)
    if cmd == "lyrics-desc":
        return cmd_lyrics_desc(cfg, args)
    if cmd == "report":
        return cmd_report(cfg, args)

    # all
    print(">>> 1/4 扫描清单")
    if not cmd_scan(cfg, args):
        print("扫描失败，终止")
        return 1
    print("\n>>> 2/4 下载媒体")
    cmd_download(cfg, args)
    print("\n>>> 3/4 抓取歌词")
    cmd_lyrics(cfg, args)
    print("    回退：从视频简介提取")
    try:
        cmd_lyrics_desc(cfg, args)
    except Exception as e:
        print("    简介回退跳过：%s" % e)
    print("\n>>> 4/4 生成报表")
    cmd_report(cfg, args)
    print("\n全部完成。输出目录：%s" % cfg["output_dir"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
