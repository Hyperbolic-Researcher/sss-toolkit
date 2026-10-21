#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""report：生成可直接筛选的 Excel 清单。

★ 分类踩过的两个坑：
1) 【Unicode 撇号】YouTube 标题大量使用 ’(U+2019)，而正则里写的是 '，
   不规范化会导致 What's / Let's 类标题全部匹配失败。必须先用 _norm() 归一化。
2) 【合集判定】Super Simple 大量合集标题是「XXX + More」，最初的正则完全没有这条，
   导致 >30 分钟的 296 个里 125 个漏判。同时时长阈值 5 分钟太短（实测 ≤5 分钟无一合集），
   改成 15 分钟。
"""
import os, re, json, glob
from collections import Counter
from . import common
from . import scan as scan_mod
from . import download as dl
from . import lyrics as lyr

THEME_RULES = [
    ("万圣节 / Halloween", [r"halloween", r"spooky", r"ghost", r"witch", r"monster", r"scary", r"trick or treat", r"pumpkin", r"zombie", r"vampire", r"skeleton"]),
    ("圣诞节 / Christmas", [r"christmas", r"santa", r"reindeer", r"gingerbread", r"jingle bell", r"north pole", r"grinch", r"carol", r"stocking", r"housetop", r"sleigh", r"snowman", r"frosty", r"rudolph"]),
    ("生日与派对 / Birthday & Party", [r"birthday", r"\bparty\b", r"celebrat", r"\bcandle"]),
    ("情人节与春季节日 / Valentine & Spring", [r"valentine", r"\beaster", r"mother'?s day", r"father'?s day", r"\bthanksgiving", r"new year", r"st\.? patrick"]),
    ("字母与拼读 / Alphabet & Phonics", [r"alphabet", r"\babc\b", r"\bletters?\b", r"phonics", r"spell", r"a is for"]),
    ("数字与计数 / Numbers & Counting", [r"\bcount", r"\bnumbers?\b", r"ten little", r"one two", r"five little", r"how many", r"\bone\b", r"\btwo\b", r"\bthree\b", r"\bfour\b", r"\bfive\b", r"\bsix\b", r"\bseven\b", r"\beight\b", r"\bnine\b", r"\bten\b", r"adding up"]),
    ("颜色与形状 / Colors & Shapes", [r"colou?r", r"\bshapes?\b", r"\bcircle\b", r"\bsquare\b", r"triangle", r"\bred\b", r"\byellow\b", r"\bblue\b", r"\bgreen\b", r"\borange\b", r"\bpink\b", r"\bpurple\b", r"\bbrown\b", r"\bblack\b", r"\bwhite\b"]),
    ("时间与日历 / Time & Calendar", [r"days? of the week", r"months?", r"\bweek\b", r"\btoday\b", r"\bclock\b", r"\bcalendar", r"\bmonday", r"\bsunday"]),
    ("认知与相反概念 / Concepts & Opposites", [r"opposite", r"big and small", r"open shut", r"same and different", r"what'?s this", r"what'?s that", r"who took", r"where is", r"can you imagine", r"peekaboo", r"peek-a-boo", r"mystery box"]),
    ("动物 / Animals", [r"animal", r"\bzoo\b", r"\bfarm", r"puppy", r"kitten", r"\bcats?\b", r"\bdogs?\b", r"\bduck", r"\bpigs?\b", r"\bcows?\b", r"monkey", r"chick", r"\bfrogs?\b", r"dinosaur", r"shark", r"dolphin", r"\blions?\b", r"\bbears?\b", r"elephant", r"butterfly", r"\bbees?\b", r"\bbirds?\b", r"\bfish", r"rabbit", r"penguin", r"\bwhales?\b", r"turtle", r"bunny", r"\bgoats?\b", r"giraffe", r"tiger", r"zebra", r"\bcamel", r"\bcrocodile", r"jellyfish", r"ladybug", r"octopus", r"hippo"]),
    ("食物与饮品 / Food & Drink", [r"pizza", r"spaghetti", r"yogurt", r"cookie", r"muffin", r"cake", r"apple", r"banana", r"ice cream", r"hungry", r"\beat\b", r"\bdrink", r"snack", r"lunch", r"breakfast", r"dinner", r"carrot", r"potato", r"soup", r"bread", r"\bmilk\b", r"juice", r"pasta", r"pancake", r"popcorn", r"candy", r"\bfood", r"yummy", r"peanut butter", r"\bjelly\b", r"lasagna", r"milkshake"]),
    ("身体与健康 / Body & Health", [r"brush your teeth", r"wash (your|our|my) (face|hands)", r"healthy", r"\bteeth\b", r"toothbrush", r"\bbody\b", r"head.{0,3}shoulders", r"\bfingers?\b", r"\btoes?\b", r"tummy", r"\beyes?\b", r"\bnose\b", r"\bmouth\b", r"sneeze", r"achoo", r"\bdoctor", r"dentist", r"\bbath\b", r"\bface\b", r"\bheart\b", r"loose tooth"]),
    ("穿衣与自理 / Clothing & Self-care", [r"\bboots?\b", r"\bshoes?\b", r"\bhats?\b", r"shirt", r"\bcoat\b", r"\bdress\b", r"put on", r"take off", r"jacket", r"\bsocks?\b", r"pants", r"scarf", r"mitten", r"get dressed", r"potty", r"clean ?up", r"\btidy", r"good habits?"]),
    ("问候与礼貌 / Greetings & Manners", [r"\bhello\b", r"\bhi\b", r"thank you", r"\bthanks\b", r"\bplease\b", r"you'?re welcome", r"\bsorry\b", r"excuse me", r"skidamarink", r"\bwave\b", r"\bhug\b", r"\bkiss\b", r"high five", r"\bbye\b", r"goodbye", r"good morning", r"here you are", r"your name", r"\bmanners?\b", r"polite"]),
    ("情绪与感受 / Emotions & Feelings", [r"\bhappy\b", r"\bsad\b", r"\bangry\b", r"scared", r"\bfeelings?\b", r"\blaugh", r"\bcry\b", r"\bsmile", r"grumpy", r"excited", r"\bcalm\b", r"\bbrave\b", r"love you", r"alright", r"thankful", r"\bproud"]),
    ("家庭与朋友 / Family & Friends", [r"mommy", r"mummy", r"\bmom\b", r"\bdad(dy)?\b", r"\bbaby\b", r"\bfamily\b", r"brother", r"sister", r"grandma", r"grandpa", r"\bfriends?\b", r"together", r"the more we get"]),
    ("游戏与玩具 / Play & Toys", [r"\bbubbles?\b", r"rock scissors paper", r"hide and seek", r"\btoys?\b", r"\bplay", r"\bgames?\b", r"puzzle", r"\bball\b", r"balloon", r"\bkite\b", r"playground"]),
    ("节奏律动与舞蹈 / Rhythm & Movement", [r"\bmove\b", r"action song", r"\bdance", r"\bjump", r"\bclap", r"stomp", r"\bshake\b", r"line up", r"\bmarch", r"\bhop\b", r"freeze", r"walking walking", r"wiggle", r"follow me", r"roly poly"]),
    ("职业与梦想 / Jobs & Dreams", [r"when i grow up", r"firefight", r"\bpolice", r"astronaut", r"\bpilot", r"\bchef\b", r"\bfarmer", r"engineer", r"scientist", r"\bjobs?\b"]),
    ("交通工具 / Vehicles", [r"\bbus\b", r"\bcars?\b", r"\btrains?\b", r"\btrucks?\b", r"\bplanes?\b", r"\bboats?\b", r"\bbikes?\b", r"ambulance", r"fire truck", r"tractor", r"helicopter", r"\bwheels?\b", r"vroom"]),
    ("天气与自然 / Weather & Nature", [r"weather", r"\brain", r"\bsnow", r"\bwind", r"\bsun(ny)?\b", r"\bcloud", r"\btrees?\b", r"\bflowers?\b", r"\bseasons?\b", r"\bspring\b", r"\bsummer\b", r"\bwinter\b", r"\bautumn", r"rainbow", r"\bforest", r"\bmountain", r"\bgrass", r"\bnature"]),
    ("太空与想象 / Space & Imagination", [r"\bspace\b", r"\bplanets?\b", r"rocket", r"\bmoon\b", r"\bstars?\b", r"\balien", r"\bmagic", r"\bdragon", r"unicorn", r"\bimagine", r"\bdream"]),
    ("农场与海洋 / Farm & Ocean", [r"\bocean\b", r"\bsea\b", r"underwater", r"safari", r"\bjungle", r"\bbeach\b"]),
    ("课堂与教学 / Classroom", [r"classroom", r"teaching", r"\blesson", r"sit down", r"story time", r"\bteacher", r"preschool", r"\blearn"]),
    ("睡前安抚 / Bedtime & Lullaby", [r"lullaby", r"bedtime", r"good ?night", r"\bsleep", r"\bhush\b", r"rock a bye", r"nighty night"]),
    ("经典童谣 / Classic Nursery Rhymes", [r"twinkle", r"\bbingo\b", r"humpty", r"dickory", r"old macdonald", r"\bitsy", r"eensy", r"row row", r"hickory", r"baa baa", r"mary had", r"jack (and|&) jill", r"hokey pokey", r"wheel on the bus", r"this is the way", r"rain rain go away", r"down by the bay", r"alice the camel", r"looby loo", r"pinocchio"]),
    ("Top 20 合集", [r"top ?20", r"\bbest of\b", r"\bcollection", r"\bcompilation", r"giant", r"\bwrapped\b", r"anniversary"]),
]

COMPILE_RE = re.compile(
    r"top\s*20|compilation|collection|playlist|mega|giant|all songs|best of"
    r"|\+\s*more\b|\band more\b|more kids songs|more nursery rhymes"
    r"|\bwrapped\b|anniversary|\bfavorites?\b|\bvol\.?\s*\d|\bpart\s*\d", re.I)
DURATION_LONG = 900     # ★ 15 分钟以上算合集（实测 ≤5 分钟无一合集）


def _norm(s):
    s = (s or "").lower()
    for a, b in (("\u2019", "'"), ("\u2018", "'"), ("\u02bc", "'"), ("\u00b4", "'"),
                 ("\u201c", '"'), ("\u201d", '"'), ("\u2013", "-"), ("\u2014", "-")):
        s = s.replace(a, b)
    return s


def classify(title, tags, duration):
    blob = (_norm(title) + " " + _norm(tags)).replace(" & ", " and ")
    hits = []
    for name, pats in THEME_RULES:
        for p in pats:
            if re.search(p, blob):
                hits.append(name)
                break
    out = list(dict.fromkeys(hits))
    if not out:
        out = ["其他 / Other"]
    is_comp = bool(COMPILE_RE.search(title or "")) or (duration and duration >= DURATION_LONG)
    if is_comp and not any("Top 20" in o for o in out):
        out.insert(0, "Top 20 合集")
    MARK = ("Top 20 合集", "其他 / Other")
    primary = next((o for o in out if o not in MARK), "其他 / Other")
    return "、".join(out), is_comp, primary


def build(cfg):
    out_dir = cfg["output_dir"]
    videos = scan_mod.read_list(out_dir)
    if not videos:
        common.log("清单为空", "ERROR")
        return None

    arch = dl.load_archive(out_dir)
    lidx = {}
    lp = lyr.idx_path(out_dir)
    if os.path.exists(lp):
        try:
            lidx = json.load(open(lp, encoding="utf-8"))
        except Exception:
            pass

    # 文件索引
    files = {}
    for f in glob.glob(os.path.join(out_dir, "*.mp4")):
        b = os.path.basename(f)
        if re.search(r"\.f\d+\.", b):
            continue
        m = re.search(r"\[([A-Za-z0-9_-]{11})\]\.mp4$", b)
        if m:
            files[m.group(1)] = f

    rows = []
    for i, (vid, dur_s, views, title) in enumerate(videos, 1):
        try:
            dur = float(dur_s or 0)
        except ValueError:
            dur = 0.0
        try:
            vw = int(float(views or 0))
        except ValueError:
            vw = 0
        path = files.get(vid, "")
        exists = bool(path) and os.path.exists(path)
        info = dl.probe_media(path) if exists else {}
        w = info.get("width", 0); h = info.get("height", 0)
        ac = info.get("acodec", "")
        size_mb = round(os.path.getsize(path)/1024**2, 2) if exists else 0.0

        theme, is_comp, primary = classify(title, "", dur)
        lv = lidx.get(vid, {})

        # 画质评级
        minh = int(cfg["quality"].get("min_height") or 1080)
        if not exists:
            status, grade = "未下载", "❌ 缺失"
        elif cfg["quality"].get("mode") == "strict" and h and h < minh:
            status, grade = "已下载（低于设定 %dp）" % minh, "⚠️ 低于阈值"
        elif ac == "opus":
            status, grade = "已下载（最高音轨 Opus）", "✅ 最高品质"
        elif ac:
            status, grade = "已下载（音轨 %s）" % ac, "⚠️ 音轨次优"
        else:
            status, grade = "已下载（无音轨）", "❌ 无音轨"

        rows.append({
            "序号": i,
            "标题": title,
            "视频ID": vid,
            "YouTube链接": "https://www.youtube.com/watch?v=" + vid,
            "本地文件路径": path.replace("\\", "/") if path else "",
            "文件存在": "是" if exists else "否",
            "分辨率": ("%dx%d" % (w, h)) if w else "",
            "视频编码": info.get("vcodec", ""),
            "音频编码": ac,
            "文件大小MB": size_mb,
            "时长秒": round(dur, 1),
            "时长": "%d:%02d" % (int(dur)//60, int(dur) % 60) if dur else "",
            "播放量": vw,
            "主分类": primary,
            "分类主题": theme,
            "是否合集": "是" if is_comp else "否",
            "难度等级": lv.get("level_cn", ""),
            "难度分": lv.get("difficulty_score", ""),
            "语速WPM": lv.get("wpm", ""),
            "唯一词数": lv.get("unique_words", ""),
            "歌词SRT": lv.get("srt", ""),
            "歌词LRC": lv.get("lrc", ""),
            "下载状态": status,
            "质量评级": grade,
        })

    # ---- 写 Excel ----
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment
        from openpyxl.utils import get_column_letter
    except ImportError:
        common.log("需要 openpyxl：pip install openpyxl", "ERROR")
        return None

    wb = Workbook(); ws = wb.active; ws.title = "媒体库清单"
    headers = list(rows[0].keys())
    ws.append(headers)
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="4472C4")
        c.alignment = Alignment(horizontal="center", vertical="center")
    for r in rows:
        ws.append([r[h] for h in headers])

    widths = {"标题": 52, "YouTube链接": 44, "本地文件路径": 60, "难度等级": 12,
              "分类主题": 34, "歌词SRT": 42, "歌词LRC": 42, "下载状态": 26, "质量评级": 16}
    for i, h in enumerate(headers, 1):
        ws.column_dimensions[get_column_letter(i)].width = widths.get(h, 12)
    ws.freeze_panes = "B2"
    ws.auto_filter.ref = ws.dimensions

    # 汇总页
    ws2 = wb.create_sheet("汇总")
    done = [r for r in rows if r["文件存在"] == "是"]
    withl = [r for r in rows if r["歌词SRT"]]
    stats = [
        ("视频总数", len(rows)),
        ("已下载", len(done)),
        ("有官方歌词", len(withl)),
        ("最高品质(Opus)", len([r for r in rows if r["质量评级"] == "✅ 最高品质"])),
        ("音轨次优", len([r for r in rows if r["质量评级"] == "⚠️ 音轨次优"])),
        ("低于画质阈值", len([r for r in rows if r["质量评级"] == "⚠️ 低于阈值"])),
        ("未下载", len([r for r in rows if r["文件存在"] == "否"])),
        ("合集数", len([r for r in rows if r["是否合集"] == "是"])),
        ("总大小GB", round(sum(r["文件大小MB"] for r in rows)/1024, 2)),
    ]
    ws2.append(["指标", "数值"])
    for k, v in stats:
        ws2.append([k, v])
    ws2.append([])
    ws2.append(["主分类", "数量"])
    for k, v in Counter(r["主分类"] for r in rows).most_common():
        ws2.append([k, v])
    ws2.append([])
    ws2.append(["难度等级", "数量"])
    for k, v in sorted(Counter(r["难度等级"] for r in rows if r["难度等级"]).items()):
        ws2.append([k, v])
    ws2.column_dimensions["A"].width = 34
    ws2.column_dimensions["B"].width = 14

    out = os.path.join(out_dir, cfg["report"].get("filename") or "媒体库清单.xlsx")
    wb.save(out)
    common.log("Excel 已生成：%s（%d 行）" % (out, len(rows)))
    common.write_state(stage="report", file=out.replace("\\", "/"))
    return out
