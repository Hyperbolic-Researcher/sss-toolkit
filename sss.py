#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""sss-toolkit 命令行入口

用法：
    python sss.py check            体检环境（依赖/代理/通道）
    python sss.py scan             扫描频道生成清单
    python sss.py download         下载（可反复跑，断点续传）
    python sss.py lyrics           抓官方歌词 + 算难度
    python sss.py report           生成 Excel
    python sss.py all              一条龙：scan → download → lyrics → report

想改频道/画质/路径，改 config.json 即可，不用动代码。
"""
import os, sys, argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core import common, scan as scan_mod, download as dl, lyrics as lyr, report as rep


def cmd_check(cfg):
    print("=" * 56)
    print("环境体检")
    print("=" * 56)
    ok = True

    print("\n[1/5] Python: %s" % sys.version.split()[0])

    print("\n[2/5] 工具链")
    for name, path, required in (
        ("ffmpeg", common.find_ffmpeg(), True),
        ("deno", common.find_deno(cfg), False),
        ("aria2c", common.find_aria2(cfg), False),
    ):
        mark = "OK " if path else ("-- " if not required else "!! ")
        print("  %s%-8s %s" % (mark, name, path or "未找到"))
        if not path and required:
            ok = False
    print("  （deno/aria2 缺失不影响基本下载，但速度与成功率会下降）")

    print("\n[3/5] Python 依赖")
    try:
        import yt_dlp  # noqa
        print("  OK  yt-dlp")
    except ImportError:
        print("  !!  yt-dlp 未安装：pip install -U yt-dlp")
        ok = False
    try:
        import openpyxl  # noqa
        print("  OK  openpyxl")
    except ImportError:
        print("  !!  openpyxl 未安装：pip install openpyxl（生成 Excel 需要）")

    print("\n[4/5] 输出目录")
    od = cfg["output_dir"]
    try:
        os.makedirs(od, exist_ok=True)
        t = os.path.join(od, ".write_test")
        open(t, "w").write("1"); os.remove(t)
        print("  OK  %s（可写）" % od)
    except Exception as e:
        print("  !!  %s 不可写: %s" % (od, e))
        ok = False

    print("\n[5/5] 通道健康（真实取流测试）")
    good, reason = dl.probe_health(cfg)
    print("  %s  %s" % ("OK " if good else "!! ", reason))
    if not good:
        print("     → 检查代理是否开启 / 节点是否存活 / 是否需要换 IP")
        ok = False

    print("\n" + "=" * 56)
    print("结论：" + ("全部通过，可以开始" if ok else "有问题，先按上面提示处理"))
    return 0 if ok else 1


def cmd_scan(cfg, args):
    lp, n = scan_mod.scan(cfg, url=args.url, limit=args.limit)
    return 0 if lp else 1


def cmd_download(cfg, args):
    st = dl.download(cfg, limit_batch=args.batch, max_rounds=args.rounds)
    return 0 if not st.get("error") else 1


def cmd_lyrics(cfg, args):
    lyr.fetch(cfg, batch=args.batch, limit=args.limit)
    return 0


def cmd_report(cfg, args):
    out = rep.build(cfg)
    return 0 if out else 1


def main():
    ap = argparse.ArgumentParser(description="sss-toolkit：频道资料库一键构建")
    ap.add_argument("command", nargs="?", default="all",
                    choices=["check", "scan", "download", "lyrics", "report", "all"])
    ap.add_argument("--url", help="频道/播放列表 URL（默认读 config.json）")
    ap.add_argument("--limit", type=int, default=0, help="只处理前 N 个（调试用）")
    ap.add_argument("--batch", type=int, default=24, help="每批数量")
    ap.add_argument("--rounds", type=int, default=0, help="最多跑几轮（0=不限制）")
    args = ap.parse_args()

    cfg = common.load_config()
    cmd = args.command

    if cmd == "check":
        return cmd_check(cfg)
    if cmd == "scan":
        return cmd_scan(cfg, args)
    if cmd == "download":
        return cmd_download(cfg, args)
    if cmd == "lyrics":
        return cmd_lyrics(cfg, args)
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
    print("\n>>> 4/4 生成报表")
    cmd_report(cfg, args)
    print("\n全部完成。输出目录：%s" % cfg["output_dir"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
