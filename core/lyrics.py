#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""lyrics：抓官方歌词字幕 + 计算量化难度。

★ 两个关键经验：

1) 【只下手动字幕，不要自动字幕】
   实测官方视频 20/20 都有手动上传的英文字幕（Available subtitles），
   质量是完整句子 + 规范标点 + 精确时间轴。
   而 --write-auto-subs 拿到的是 ASR 结果，会出现 "sh be quiet" 这类噪声，
   字母歌甚至被切成单字母，用来算难度会严重失真。

2) 【难度不能用词表算】
   最初用 Dolch 220 词表统计"生僻词占比"，结果 100% 的视频都被判成极难，
   因为 shoulder/knee/toe 这些常见词都不在表里。
   改用不依赖词表的指标：语速 WPM、唯一词数、平均句长、重复率（反向）。
"""
import os, re, subprocess, json, time
from . import common
from . import scan as scan_mod

IDX_NAME = "lyrics_index.json"
TS_RE = re.compile(r"(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})[,.](\d{3})")


def idx_path(out_dir):
    return os.path.join(out_dir, IDX_NAME)


def _t(m, i):
    return int(m.group(i))*3600 + int(m.group(i+1))*60 + int(m.group(i+2)) + int(m.group(i+3))/1000


def parse_srt(path):
    try:
        raw = open(path, encoding="utf-8", errors="replace").read()
    except OSError:
        return []
    out = []
    for block in re.split(r"\n\s*\n", raw):
        lines = [l.strip() for l in block.strip().split("\n") if l.strip()]
        if not lines:
            continue
        ti, m = 0, None
        for i, l in enumerate(lines):
            m = TS_RE.search(l)
            if m:
                ti = i
                break
        if not m:
            continue
        txt = " ".join(lines[ti+1:]).strip()
        txt = re.sub(r"<[^>]+>", "", txt)
        txt = re.sub(r"\[[^\]]*\]", "", txt)       # 去 [Music] 之类
        if txt:
            out.append((_t(m, 1), _t(m, 5), txt))
    return out


def strip_dup(cues):
    """自动字幕常有滚动重复，去连续重复段"""
    res, prev = [], None
    for t0, t1, tx in cues:
        key = re.sub(r"[^a-z ]", "", tx.lower()).strip()
        if key and key != prev:
            res.append((t0, t1, tx))
            prev = key
    return res


def analyze(cues):
    if not cues:
        return None
    text = " ".join(c[2] for c in cues)
    words = re.findall(r"[a-z']+", text.lower())
    total = len(words)
    if total < 3:
        return None
    uniq = set(words)
    span = max(cues[-1][1] - cues[0][0], 1)
    wpm = total / (span/60)
    avg_sent = total / max(len(cues), 1)
    repeat_ratio = 1 - len(uniq)/total

    # 综合分：语速权重最高（跟唱最难），其次词汇广度
    s_wpm  = min(wpm/140, 1.5)
    s_uniq = min(len(uniq)/70, 1.5)
    s_sent = min(avg_sent/12, 1.5)
    s_rep  = max(0.0, min((0.75-repeat_ratio)/0.75, 1.5))
    score = 0.38*s_wpm + 0.32*s_uniq + 0.15*s_sent + 0.15*s_rep

    if score < 0.35:   lvl, cn = "L1", "L1 入门"
    elif score < 0.50: lvl, cn = "L2", "L2 简单"
    elif score < 0.65: lvl, cn = "L3", "L3 中等"
    elif score < 0.82: lvl, cn = "L4", "L4 较难"
    else:              lvl, cn = "L5", "L5 复杂"

    return {
        "unique_words": len(uniq), "total_words": total,
        "wpm": round(wpm, 1), "avg_sent_len": round(avg_sent, 1),
        "repeat_ratio": round(repeat_ratio, 3),
        "cue_count": len(cues), "span_sec": round(span, 1),
        "difficulty_score": round(score, 3),
        "level": lvl, "level_cn": cn,
        "unique_word_list": sorted(uniq),
        "preview": " / ".join(c[2] for c in cues[:3])[:120],
    }


def to_lrc(cues):
    out = []
    for t0, _t1, tx in cues:
        m = int(t0 // 60); s = t0 - m*60
        out.append("[%02d:%05.2f]%s" % (m, s, tx))
    return "\n".join(out)


def fetch(cfg, batch=25, limit=0, stop_flag=None):
    out_dir = cfg["output_dir"]
    ly = cfg["lyrics"]
    sub_dir = os.path.join(out_dir, ly.get("sub_dir_name") or "lyrics")
    os.makedirs(sub_dir, exist_ok=True)

    videos = scan_mod.read_list(out_dir)
    if not videos:
        common.log("清单为空，请先 scan", "ERROR")
        return {}
    if limit:
        videos = videos[:limit]

    idx = {}
    if os.path.exists(idx_path(out_dir)):
        try:
            idx = json.load(open(idx_path(out_dir), encoding="utf-8"))
        except Exception:
            idx = {}

    langs = ",".join(ly.get("languages") or ["en"])
    net = cfg["network"]; adv = cfg["advanced"]

    base = [common.py(), "-m", "yt_dlp", "--skip-download",
            "--sub-langs", langs, "--sub-format", "srt", "--convert-subs", "srt",
            "--sleep-requests", "0.6", "--no-warnings", "--socket-timeout", "25"]
    if ly.get("manual_only", True):
        base.append("--write-subs")          # ★ 只手动字幕
    else:
        base += ["--write-subs", "--write-auto-subs"]
    if net.get("proxy_enabled") and net.get("proxy"):
        base += ["--proxy", net["proxy"]]
    deno = common.find_deno(cfg)
    if deno:
        base += ["--js-runtimes", "deno:" + deno]
    extra = "youtube:player_client=" + adv.get("player_client", "mweb,tv,web,ios")
    if net.get("pot_server"):
        extra += ";youtubepot-bgutilhttp:base_url=" + net["pot_server"]
    base += ["--extractor-args", extra,
             "-o", os.path.join(sub_dir, "%(id)s.%(ext)s")]

    have = sum(1 for v in idx.values() if v.get("has_lyrics"))
    common.log("歌词任务：清单 %d，已有 %d" % (len(videos), have))
    common.write_state(stage="lyrics", total=len(videos), done=have)

    got = 0
    for bi in range(0, len(videos), batch):
        if stop_flag and stop_flag():
            common.log("歌词任务收到停止指令")
            break
        chunk = videos[bi:bi+batch]
        todo = [v for v in chunk if not idx.get(v[0], {}).get("has_lyrics")]
        if todo:
            urls = ["https://www.youtube.com/watch?v=" + v[0] for v in todo]
            try:
                subprocess.run(base + urls, capture_output=True, text=True,
                               env=common.env_no_proxy(), timeout=900,
                               encoding="utf-8", errors="replace")
            except Exception as e:
                common.log("本批字幕异常: %s" % str(e)[:80], "WARN")

        for v in chunk:
            vid = v[0]
            if idx.get(vid, {}).get("has_lyrics"):
                continue
            p = None
            for ext in (".en.srt", ".srt"):
                cand = os.path.join(sub_dir, vid + ext)
                if os.path.exists(cand):
                    p = cand
                    break
            if not p:
                idx[vid] = {"has_lyrics": False}
                continue
            cues = strip_dup(parse_srt(p))
            a = analyze(cues) if len(cues) >= 2 else None
            if not a:
                idx[vid] = {"has_lyrics": False, "note": "字幕为空或词数过少"}
                continue
            a["has_lyrics"] = True
            a["srt"] = p.replace("\\", "/")
            try:
                lrc = os.path.join(sub_dir, vid + ".lrc")
                open(lrc, "w", encoding="utf-8").write(to_lrc(cues))
                a["lrc"] = lrc.replace("\\", "/")
            except Exception:
                pass
            idx[vid] = a
            got += 1

        done = sum(1 for x in idx.values() if x.get("has_lyrics"))
        common.log("歌词进度 %d/%d（本轮新增 %d）" % (done, len(videos), got))
        common.write_state(stage="lyrics", done=done, total=len(videos))
        try:
            json.dump(idx, open(idx_path(out_dir), "w", encoding="utf-8"),
                      ensure_ascii=False, indent=1)
        except Exception:
            pass
        time.sleep(1)

    have = sum(1 for x in idx.values() if x.get("has_lyrics"))
    common.log("歌词完成：%d/%d 有官方歌词" % (have, len(videos)))
    common.write_state(stage="lyrics", running=False, done=have, total=len(videos))
    return idx
