#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""本地网页界面（零第三方依赖，只用标准库）。

启动后浏览器访问 http://127.0.0.1:8765 ，点按钮即可。
任务在后台线程跑，页面实时显示进度与日志。
"""
import os, sys, json, threading, time, webbrowser, subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core import common, scan as scan_mod, download as dl, lyrics as lyr, report as rep, single as sg, channel as ch, batch as bt

PORT = int(os.environ.get("SSS_PORT", "8765"))
# ★ 手机访问：默认只监听本机；加 --lan 参数则监听所有网卡，手机连同一 WiFi 即可访问
LAN = "--lan" in sys.argv
HOST = "0.0.0.0" if LAN else "127.0.0.1"
# 可选口令：设置 SSS_TOKEN 环境变量后，访问需带 ?k=口令（家用 WiFi 一般不需要）
TOKEN = os.environ.get("SSS_TOKEN", "").strip()


def lan_ip():
    """取本机局域网 IP（不实际发包）"""
    import socket
    try:
        s_ = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s_.connect(("8.8.8.8", 80))
        ip = s_.getsockname()[0]
        s_.close()
        return ip
    except Exception:
        return "127.0.0.1"
_STOP = {"flag": False}
_WORKER = {"thread": None, "task": ""}


def _run_task(task, cfg):
    _STOP["flag"] = False
    try:
        if task == "check":
            good, reason, _fid = dl.probe_health(cfg)
            common.log("体检：%s" % reason, "OK" if good else "ERROR")
        elif task == "scan":
            scan_mod.scan(cfg)
        elif task == "download":
            dl.download(cfg)
        elif task == "lyrics":
            lyr.fetch(cfg)
        elif task == "report":
            rep.build(cfg)
        elif task == "all":
            common.log("=== 全流程开始 ===")
            scan_mod.scan(cfg)
            dl.download(cfg)
            lyr.fetch(cfg)
            rep.build(cfg)
            common.log("=== 全流程结束 ===", "OK")
    except Exception as e:
        common.log("任务异常：%s" % e, "ERROR")
    finally:
        common.write_state(running=False, task="")
        _WORKER["thread"] = None
        _WORKER["task"] = ""


def _fetch_ip(url, proxy, timeout=6):
    """通过代理查一个回显 IP 的地址。返回 (ip, err)"""
    import urllib.request
    handlers = []
    if proxy:
        handlers.append(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
    else:
        handlers.append(urllib.request.ProxyHandler({}))
    try:
        op = urllib.request.build_opener(*handlers)
        r = op.open(url, timeout=timeout)
        return r.read().decode("utf-8", "replace").strip(), ""
    except Exception as e:
        return "", str(e)[:80]


def diagnose():
    """诊断当前出口状态，供「画质未达标」时的解决面板使用"""
    cfg = common.load_config()
    net = cfg.get("network", {}) or {}
    proxy = net.get("proxy") if net.get("proxy_enabled") else ""
    ip4, e4 = _fetch_ip("https://api.ipify.org", proxy)
    ip6, e6 = _fetch_ip("https://api64.ipify.org", proxy, timeout=5)
    out = {
        "proxy": proxy or "(未启用代理)",
        "ipv4": ip4 or "",
        "ipv4_error": e4,
        "ip_any": ip6 or ip4 or "",
        "using_ipv6": bool(ip6 and ":" in ip6),
        "pot": "",
    }
    try:
        pot_ok, pot_msg = dl.check_pot(cfg)
        out["pot"] = ("在线" if pot_ok else "未响应") + " — " + pot_msg
    except Exception:
        out["pot"] = "未知"
    return out


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _html(self, text):
        body = text.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _auth_ok(self, q):
        if not TOKEN:
            return True
        return (q.get("k") or [""])[0] == TOKEN

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if not self._auth_ok(q):
            return self._json({"error": "需要口令，请在网址后加 ?k=你的口令"}, 401)
        if u.path in ("/", "/index.html"):
            return self._html(INDEX_HTML)
        if u.path == "/api/status":
            cfg = common.load_config()
            st = common.read_state()
            busy = _WORKER["thread"] is not None
            return self._json({
                "config": {
                    "output_dir": cfg["output_dir"],
                    "channel_url": cfg.get("channel_url", ""),
                    "min_height": cfg["quality"].get("min_height"),
                    "proxy": cfg["network"].get("proxy") if cfg["network"].get("proxy_enabled") else "",
                },
                "state": st,
                "busy": busy,
                "task": _WORKER["task"],
                "events": common.recent_events(80),
                "tools": {
                    "ffmpeg": bool(common.find_ffmpeg()),
                    "deno": bool(common.find_deno(cfg)),
                    "aria2": bool(common.find_aria2(cfg)),
                },
                "channel": cfg.get("channel_url", ""),
            })
        if u.path == "/api/probe":
            cfg = common.load_config()
            url = (q.get("url") or [""])[0]
            return self._json(sg.probe(cfg, url))
        if u.path == "/api/dl_status":
            return self._json(sg.task_state())
        if u.path == "/api/channel_state":
            return self._json(ch.scan_state())
        if u.path == "/api/batch_state":
            return self._json(bt.state())
        if u.path == "/api/diagnose":
            return self._json(diagnose())
        if u.path == "/api/pick_folder":
            """弹系统原生目录选择框（独立子进程跑 tkinter，避免线程内崩溃）"""
            init = (q.get("init") or [""])[0]
            picker = os.path.join(os.path.dirname(os.path.abspath(__file__)), "core", "folder_picker.py")
            try:
                r = subprocess.run([sys.executable, picker, init],
                                   capture_output=True, text=True, timeout=300,
                                   encoding="utf-8", errors="replace")
                path = (r.stdout or "").strip()
                return self._json({"ok": bool(path), "path": path})
            except Exception as e:
                return self._json({"ok": False, "error": str(e)[:100]})
        if u.path == "/api/open_folder":
            path = (q.get("path") or [""])[0]
            try:
                if path and os.path.exists(path):
                    if os.path.isfile(path):
                        # ★ 必须给路径加引号：路径含空格或中文逗号（，）时，
                        #   不加引号会被 explorer 拆成多个参数，跳到错误位置。
                        subprocess.Popen('explorer /select,"%s"' % os.path.normpath(path),
                                         shell=True)
                    else:
                        os.startfile(path)
                    return self._json({"ok": True})
                return self._json({"ok": False, "error": "文件不存在（可能已被移动或清理）"})
            except Exception as e:
                return self._json({"ok": False, "error": str(e)[:80]})
        if u.path == "/api/open":
            cfg = common.load_config()
            try:
                os.startfile(cfg["output_dir"])
            except Exception:
                pass
            return self._json({"ok": True})
        return self._json({"error": "not_found"}, 404)

    def do_POST(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if not self._auth_ok(q):
            return self._json({"error": "需要口令"}, 401)
        if u.path == "/api/start":
            if _WORKER["thread"] is not None:
                return self._json({"error": "已有任务在运行"}, 409)
            task = (q.get("task") or ["check"])[0]
            cfg = common.load_config()
            common.write_state(running=True, task=task, stage=task, done=0, total=0)
            t = threading.Thread(target=_run_task, args=(task, cfg), daemon=True)
            _WORKER["thread"] = t
            _WORKER["task"] = task
            t.start()
            return self._json({"ok": True, "task": task})
        if u.path == "/api/channel_scan":
            cfg = common.load_config()
            url = (q.get("url") or [""])[0].strip()
            ok, msg = ch.start_scan(cfg, url)
            return self._json({"ok": ok, "msg": msg})
        if u.path == "/api/channel_stop":
            ch.stop_scan()
            return self._json({"ok": True})
        if u.path == "/api/batch_start":
            cfg = common.load_config()
            ids = (q.get("ids") or [""])[0]
            outs = (q.get("outputs") or ["video"])[0]
            dl_dir = (q.get("dest") or [""])[0].strip()
            chn = (q.get("channel") or [""])[0].strip()
            # 先把目录/频道写回配置，下载模块要读
            if dl_dir:
                cfg["output_dir"] = dl_dir
            if chn:
                cfg["channel_url"] = chn
            try:
                json.dump(cfg, open(common.CONFIG_PATH, "w", encoding="utf-8"),
                          ensure_ascii=False, indent=2)
            except Exception:
                pass
            id_list = [x for x in ids.split(",") if x]
            out_list = [x for x in outs.split(",") if x]
            ok, msg = bt.start(cfg, id_list, out_list)
            return self._json({"ok": ok, "msg": msg})
        if u.path == "/api/batch_stop":
            bt.stop()
            return self._json({"ok": True})
        if u.path == "/api/save_config":
            cfg = common.load_config()
            chv = (q.get("channel") or [""])[0].strip()
            od = (q.get("output_dir") or [""])[0].strip()
            mh = (q.get("min_height") or [""])[0].strip()
            changed = []
            if chv:
                cfg["channel_url"] = chv
                changed.append("频道")
            if od:
                cfg["output_dir"] = od
                changed.append("目录")
            if mh:
                try:
                    cfg["quality"]["min_height"] = int(mh)
                    changed.append("画质")
                except ValueError:
                    pass
            try:
                json.dump(cfg, open(common.CONFIG_PATH, "w", encoding="utf-8"),
                          ensure_ascii=False, indent=2)
                common.log("配置已保存：%s" % "、".join(changed))
                return self._json({"ok": True, "changed": changed})
            except Exception as e:
                return self._json({"ok": False, "error": str(e)[:100]})
        if u.path == "/api/dl_single":
            cfg = common.load_config()
            url = (q.get("url") or [""])[0]
            dest = (q.get("dest") or [cfg["output_dir"]])[0]
            outs = (q.get("outputs") or ["video"])[0]
            outs = [x for x in outs.split(",") if x]
            ok, msg = sg.start_download(cfg, url, dest, outputs=outs)
            return self._json({"ok": ok, "msg": msg})
        if u.path == "/api/dl_stop":
            sg.stop_task()
            return self._json({"ok": True})
        if u.path == "/api/stop":
            _STOP["flag"] = True
            common.log("已请求停止（当前批次结束后生效）", "WARN")
            return self._json({"ok": True})
        return self._json({"error": "not_found"}, 404)


INDEX_HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>频道资料库 · 一键构建</title>
<style>
:root{--bg:#0f1115;--card:#181c23;--line:#2a3038;--txt:#e6e9ee;--dim:#8b95a5;
--ok:#3ddc97;--warn:#ffb84d;--err:#ff6b6b;--acc:#4c8dff}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--txt);
font:14px/1.6 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif;padding:22px}
.wrap{max-width:1080px;margin:0 auto}
h1{font-size:19px;margin:0 0 4px}
.sub{color:var(--dim);font-size:12.5px;margin-bottom:18px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px;margin-bottom:14px}
.row{display:flex;gap:10px;flex-wrap:wrap;align-items:center}
button{background:var(--acc);color:#fff;border:0;border-radius:7px;padding:9px 16px;
font-size:13.5px;cursor:pointer;font-weight:500}
button:hover{filter:brightness(1.1)}
button:disabled{opacity:.4;cursor:not-allowed}
button.ghost{background:transparent;border:1px solid var(--line);color:var(--txt)}
button.danger{background:var(--err)}
.meta{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:11px;margin-bottom:14px}
.kv{background:#141821;border:1px solid var(--line);border-radius:8px;padding:10px 12px}
.kv .k{color:var(--dim);font-size:11.5px;margin-bottom:3px}
.kv .v{font-size:13px;word-break:break-all}
.bar{height:9px;background:#0b0e13;border-radius:5px;overflow:hidden;margin:10px 0 6px}
.bar i{display:block;height:100%;background:linear-gradient(90deg,#4c8dff,#3ddc97);width:0;transition:width .4s}
.stat{display:flex;justify-content:space-between;font-size:12.5px;color:var(--dim)}
.log{background:#0b0e13;border:1px solid var(--line);border-radius:8px;padding:11px;
height:340px;overflow-y:auto;font:12px/1.65 ui-monospace,Consolas,monospace;white-space:pre-wrap;word-break:break-all}
.log .INFO{color:#c3cad6}
.log .OK{color:var(--ok)}
.log .WARN{color:var(--warn)}
.log .ERROR{color:var(--err)}
.tag{display:inline-block;font-size:11px;padding:1px 7px;border-radius:4px;background:#232a34;color:var(--dim);margin-left:6px}
.dot{width:7px;height:7px;border-radius:50%;display:inline-block;margin-right:5px}
.on{background:var(--ok)}.off{background:#4a5260}
@keyframes slide{0%{transform:translateX(-100%)}100%{transform:translateX(360%)}}
@keyframes spin{to{transform:rotate(360deg)}}
.spin{width:14px;height:14px;border:2px solid var(--line);border-top-color:var(--ok);
border-radius:50%;animation:spin .8s linear infinite;flex:none}
tr.row:hover{background:#161b24}
td{padding:7px 8px;border-bottom:1px solid #1e242d}
td.ttl{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:0;color:#d7dce4}
td.ttl:hover{color:#fff}
</style>
</head>
<body><div class="wrap">
<h1>视频下载</h1>

<div class="card" style="border-color:#2f4a6d">
  <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px">
    <span style="font-size:15px;font-weight:600">单视频下载</span>
    <span style="color:var(--dim);font-size:12px">粘贴链接自动解析，回车即下</span>
  </div>
  <div style="display:flex;gap:8px">
    <input id="dlUrl" placeholder="粘贴 YouTube 链接…（支持 watch / youtu.be / shorts）"
      style="flex:1;background:#0b0e13;border:1px solid var(--line);color:var(--txt);
      border-radius:7px;padding:10px 12px;font-size:13.5px;outline:none"
      autocomplete="off" spellcheck="false" />
    <button class="ghost" onclick="doProbe(true)">解析</button>
  </div>
  <div id="probeMsg" style="margin-top:8px;font-size:12.5px;color:var(--dim)"></div>
  <div id="probeBox" style="display:none;margin-top:12px;background:#141821;
       border:1px solid var(--line);border-radius:8px;padding:12px">
    <div id="vTitle" style="font-size:14px;font-weight:600;margin-bottom:6px"></div>
    <div id="vMeta" style="color:var(--dim);font-size:12.5px;margin-bottom:12px"></div>
    <div style="display:flex;gap:8px;align-items:center;margin-bottom:12px;flex-wrap:wrap">
      <span style="color:var(--dim);font-size:12.5px;flex:none">保存到</span>
      <input id="dlDest" readonly style="flex:1;min-width:240px;background:#0b0e13;
        border:1px solid var(--line);color:var(--txt);border-radius:6px;padding:7px 10px;
        font-size:12.5px;outline:none;cursor:pointer" onclick="pickFolder()"
        title="点击选择目录" />
      <button class="ghost" onclick="pickFolder()" style="flex:none;font-size:12.5px;padding:7px 14px">浏览…</button>
    </div>
    <div style="display:flex;gap:14px;align-items:center;margin-bottom:12px;flex-wrap:wrap">
      <span style="color:var(--dim);font-size:12.5px;flex:none">下载内容</span>
      <label style="display:flex;align-items:center;gap:6px;font-size:13px;cursor:pointer">
        <input type="checkbox" id="optVideo" checked style="width:15px;height:15px;cursor:pointer" /> 原视频
      </label>
      <label style="display:flex;align-items:center;gap:6px;font-size:13px;cursor:pointer">
        <input type="checkbox" id="optNoAudio" style="width:15px;height:15px;cursor:pointer" /> 视频（无音轨）
      </label>
      <label style="display:flex;align-items:center;gap:6px;font-size:13px;cursor:pointer">
        <input type="checkbox" id="optAudio" style="width:15px;height:15px;cursor:pointer" /> 音频（m4a）
      </label>
      <span style="color:#5a6373;font-size:11.5px">可多选</span>
    </div>
    <div style="display:flex;gap:8px">
      <button id="btnDl" onclick="startDl()" style="flex:1">开始下载</button>
    </div>
  </div>
  <div id="dlBox" style="display:none;margin-top:12px">
    <div class="bar"><i id="dlFill"></i></div>
    <div class="stat" style="margin-top:6px"><span id="dlStage">准备中</span><span id="dlPct">0%</span></div>
    <div class="stat" style="margin-top:2px"><span id="dlSpeed" style="font-size:12px"></span><span id="dlEta" style="font-size:12px"></span></div>
    <div id="dlDone" style="display:none;margin-top:10px;padding:10px;border-radius:7px;
         background:#12261c;border:1px solid #1f4d38">
      <div id="dlDoneTitle" style="color:var(--ok);font-size:13px;margin-bottom:8px"></div>
      <div id="dlFiles"></div>
    </div>
    <div id="dlErr" style="display:none;margin-top:10px;color:var(--err);font-size:12.5px"></div>
    <div style="margin-top:10px"><button class="ghost" onclick="stopDl()" id="btnStopDl" style="font-size:12px;padding:6px 12px">取消下载</button></div>
  </div>

  <div id="fixPanel" style="display:none;margin-top:14px;padding:14px;border-radius:8px;
       background:#221a10;border:1px solid #6b4a1f">
    <div id="fixHead" style="font-size:13.5px;font-weight:600;margin-bottom:10px;display:flex;align-items:center"></div>
    <div style="font-size:12.5px;color:#c9b393;line-height:1.7;margin-bottom:12px">
      <span style="color:#8a7a63">原因</span>　当前出口被 YouTube 临时降级，只返回了
      <b id="fixLocal" style="color:var(--warn)"></b> 视频流
    </div>
    <div style="background:#191309;border-radius:6px;padding:10px 12px;margin-bottom:12px;font-size:12px">
      <div style="display:flex;justify-content:space-between;margin-bottom:6px">
        <span style="color:#8a7a63">当前出口 IP</span><span id="fixIp" style="color:#e6e9ee"></span>
      </div>
      <div style="display:flex;justify-content:space-between;margin-bottom:6px">
        <span style="color:#8a7a63">IP 类型</span><span id="fixIpType" style="color:#e6e9ee"></span>
      </div>
      <div style="display:flex;justify-content:space-between;margin-bottom:6px">
        <span style="color:#8a7a63">代理地址</span><span id="fixProxy" style="color:#9aa3b0;font-size:11px"></span>
      </div>
      <div style="display:flex;justify-content:space-between;margin-bottom:6px">
        <span style="color:#8a7a63">本次下载</span><span id="fixSize" style="color:#e6e9ee"></span>
      </div>
      <div style="display:flex;justify-content:space-between;padding-top:6px;border-top:1px solid #3a2c19">
        <span style="color:#8a7a63">源站最高</span><span id="fixSrc" style="color:var(--ok)"></span>
      </div>
    </div>
    <div style="font-size:12.5px;color:#c9b393;margin-bottom:6px">解决步骤</div>
    <ol style="margin:0 0 12px 20px;padding:0;font-size:12.5px;color:#b9c0cb;line-height:1.9">
      <li>在代理客户端内关闭 <b>IPv6</b></li>
      <li><b>断开</b>当前代理连接</li>
      <li>重新选择<b>另一个节点</b>并连接</li>
      <li>回到这里点击下方按钮<b>重新下载</b></li>
    </ol>
    <div style="display:flex;gap:8px">
      <button onclick="retryDownload()" style="flex:1;background:#c8811f">重新解析并下载</button>
      <button class="ghost" onclick="hideFix()" style="flex:none">关闭提示</button>
    </div>
  </div>

  <div style="margin-top:14px;padding-top:12px;border-top:1px solid var(--line);
       font-size:11.5px;color:#5a6373;display:flex;align-items:center;gap:8px;flex-wrap:wrap">
    <span>支持 YouTube / B站 / 抖音 / 小红书 / 微博 / TikTok / Vimeo / Twitch 等 1752 个站点</span>
    <span onclick="toggleSites()" style="color:var(--acc);cursor:pointer;user-select:none"
      id="sitesToggle">查看完整列表</span>
  </div>
  <div id="sitesList" style="display:none;margin-top:10px;padding:12px;background:#141821;
       border:1px solid var(--line);border-radius:8px;font-size:11.5px;line-height:2">
    <div style="color:var(--ok);margin-bottom:6px;font-weight:600">支持</div>
    <div style="color:#9aa3b0">YouTube · Bilibili(B站) · 抖音 · 小红书 · 微博 · TikTok ·
      Instagram · Twitter/X · Facebook · Reddit · Pinterest · Tumblr · Vimeo · Dailymotion ·
      优酷 · 爱奇艺 · 腾讯视频 · Twitch · SoundCloud · TED</div>
    <div style="color:var(--err);margin:10px 0 6px;font-weight:600">不支持</div>
    <div style="color:#9aa3b0">微信视频号（生态封闭，无解） · 快手（无解析器）</div>
    <div style="color:#5a6373;margin-top:10px">
      判断方法：把链接粘到上面能不能解析出来就知道。支持 ≠ 能拿高清，
      也 ≠ 可以随便用于商业分发。
    </div>
  </div>
</div>

<div class="card" style="border-color:#2a3340">
  <div style="font-size:15px;font-weight:600;margin-bottom:4px">频道批量下载</div>
  <div style="color:var(--dim);font-size:12px;margin-bottom:16px">
    先解析频道拿到视频列表，勾选要下的，再统一下载（不设画质门槛，一律取最高）
  </div>

  <!-- 步骤一：地址与目录 -->
  <div style="display:flex;flex-direction:column;gap:12px">
    <div>
      <div style="color:var(--dim);font-size:12px;margin-bottom:5px">频道地址</div>
      <div style="display:flex;gap:8px">
        <input id="bChannel" placeholder="https://www.youtube.com/@频道名/videos"
          style="flex:1;background:#0b0e13;border:1px solid var(--line);color:var(--txt);
          border-radius:7px;padding:9px 12px;font-size:13px;outline:none" spellcheck="false" />
        <button id="bParse" onclick="startParse()" style="flex:none">解析</button>
      </div>
    </div>
    <div>
      <div style="color:var(--dim);font-size:12px;margin-bottom:5px">保存到</div>
      <div style="display:flex;gap:8px">
        <input id="bDest" readonly onclick="pickBatchFolder()"
          style="flex:1;background:#0b0e13;border:1px solid var(--line);color:var(--txt);
          border-radius:7px;padding:9px 12px;font-size:12.5px;outline:none;cursor:pointer" />
        <button class="ghost" onclick="pickBatchFolder()" style="flex:none;font-size:12.5px;padding:9px 16px">浏览…</button>
      </div>
    </div>
  </div>

  <!-- 解析进度 -->
  <div id="parseBox" style="display:none;margin-top:14px;padding:12px;background:#141821;
       border:1px solid var(--line);border-radius:8px">
    <div style="display:flex;align-items:center;gap:10px;margin-bottom:8px">
      <div class="spin"></div>
      <span id="parseMsg" style="font-size:13px;color:var(--txt)">正在解析频道…</span>
      <span id="parseCount" style="margin-left:auto;font-size:12px;color:var(--dim)"></span>
    </div>
    <div style="height:4px;background:#0b0e13;border-radius:2px;overflow:hidden">
      <div id="parseBar" style="height:100%;width:30%;background:linear-gradient(90deg,#4c8dff,#3ddc97);
           animation:slide 1.4s ease-in-out infinite"></div>
    </div>
    <div style="color:#5a6373;font-size:11.5px;margin-top:8px">
      频道视频多时需要几分钟，请耐心等待，不要关闭页面
    </div>
  </div>

  <!-- 步骤二：列表 -->
  <div id="listBox" style="display:none;margin-top:16px">
    <div style="display:flex;align-items:center;gap:12px;margin-bottom:10px">
      <button class="ghost" onclick="toggleAll(true)" style="font-size:12px;padding:5px 12px">全选</button>
      <button class="ghost" onclick="toggleAll(false)" style="font-size:12px;padding:5px 12px">取消全选</button>
      <span id="listStat" style="color:var(--dim);font-size:12px"></span>
      <input id="listFilter" placeholder="搜索标题…" oninput="renderList()"
        style="margin-left:auto;background:#0b0e13;border:1px solid var(--line);color:var(--txt);
        border-radius:6px;padding:6px 10px;font-size:12px;outline:none;width:180px" />
    </div>

    <div style="max-height:340px;overflow-y:auto;border:1px solid var(--line);border-radius:8px">
      <table style="width:100%;border-collapse:collapse;font-size:12.5px;table-layout:fixed">
        <colgroup>
          <col style="width:40px" />
          <col />
          <col style="width:74px" />
          <col style="width:96px" />
        </colgroup>
        <thead>
          <tr style="background:#141821;position:sticky;top:0">
            <th style="padding:8px;text-align:center"></th>
            <th style="text-align:left;padding:8px;color:var(--dim);font-weight:500">标题</th>
            <th style="padding:8px;text-align:right;color:var(--dim);font-weight:500">时长</th>
            <th style="padding:8px;text-align:right;color:var(--dim);font-weight:500">预估大小</th>
          </tr>
        </thead>
        <tbody id="listBody"></tbody>
      </table>
    </div>

    <div style="display:flex;gap:14px;align-items:center;margin:14px 0;flex-wrap:wrap">
      <span style="color:var(--dim);font-size:12.5px;flex:none">下载内容</span>
      <label style="display:flex;align-items:center;gap:6px;font-size:13px;cursor:pointer">
        <input type="checkbox" id="bOptVideo" checked style="width:15px;height:15px;cursor:pointer" /> 原视频
      </label>
      <label style="display:flex;align-items:center;gap:6px;font-size:13px;cursor:pointer">
        <input type="checkbox" id="bOptNoAudio" style="width:15px;height:15px;cursor:pointer" /> 视频（无音轨）
      </label>
      <label style="display:flex;align-items:center;gap:6px;font-size:13px;cursor:pointer">
        <input type="checkbox" id="bOptAudio" style="width:15px;height:15px;cursor:pointer" /> 音频（m4a）
      </label>
    </div>

    <button onclick="startBatchDl()" id="b-do" style="width:100%;padding:11px">开始下载勾选的视频</button>
  </div>

  <!-- 步骤三：下载进度 -->
  <div id="batchProg" style="display:none;margin-top:16px;padding:12px;background:#141821;
       border:1px solid var(--line);border-radius:8px">
    <div class="stat" style="margin-bottom:8px">
      <span id="bStage">准备中</span><span id="bPct">0%</span>
    </div>
    <div class="bar"><i id="bFill"></i></div>
    <div class="stat" style="margin-top:6px">
      <span id="bCount"></span><span id="bDetail"></span>
    </div>
    <div style="margin-top:10px">
      <button class="danger" onclick="stopBatch()" id="b-stopdl" style="font-size:12px;padding:6px 14px">停止下载</button>
    </div>
  </div>

  <div style="margin-top:18px;padding-top:14px;border-top:1px solid var(--line)">
    <button class="ghost" onclick="toggleAdv()" id="btnAdv" style="font-size:12px;padding:6px 14px">高级操作</button>
    <div id="advBody" style="display:none;margin-top:14px">

      <div style="background:#141821;border:1px solid var(--line);border-radius:8px;
           padding:10px 12px;margin-bottom:14px">
        <div style="font-size:12px;color:#8b95a5;line-height:1.75">
          下面几项针对<b style="color:#c3c9d2">已经下载到本地的视频</b>，与上方的下载任务<b>互不影响</b>，可单独执行。<br>
          执行时会出现进度条，随时可以点「停止」；<b style="color:#c3c9d2">中途停止不会损坏已下载的视频</b>。
        </div>
      </div>

      <div style="display:flex;flex-direction:column;gap:12px">
        <div style="display:flex;align-items:flex-start;gap:12px">
          <button class="ghost" onclick="go('check')" id="b-check"
            style="font-size:12.5px;flex:none;width:104px">检查环境</button>
          <div style="font-size:11.5px;color:#7c8593;line-height:1.6;padding-top:6px">
            测试代理、POT 服务、能不能取到高清流。只做探测，<b>不会下载任何文件</b>
          </div>
        </div>
        <div style="display:flex;align-items:flex-start;gap:12px">
          <button class="ghost" onclick="go('lyrics')" id="b-lyrics"
            style="font-size:12.5px;flex:none;width:104px">抓取歌词</button>
          <div style="font-size:11.5px;color:#7c8593;line-height:1.6;padding-top:6px">
            给已下载的视频抓官方字幕，生成 .srt（带时间轴）/ .lrc / .txt
          </div>
        </div>
        <div style="display:flex;align-items:flex-start;gap:12px">
          <button class="ghost" onclick="go('report')" id="b-report"
            style="font-size:12.5px;flex:none;width:104px">生成 Excel</button>
          <div style="font-size:11.5px;color:#7c8593;line-height:1.6;padding-top:6px">
            把已下载的视频整理成表格：标题、画质、分类、难度、歌词路径等
          </div>
        </div>
        <div style="display:flex;align-items:flex-start;gap:12px">
          <button class="ghost" onclick="openDir()"
            style="font-size:12.5px;flex:none;width:104px">打开目录</button>
          <div style="font-size:11.5px;color:#7c8593;line-height:1.6;padding-top:6px">
            在资源管理器里打开保存目录
          </div>
        </div>
      </div>

      <div id="advRun" style="display:none;margin-top:16px;padding:12px;background:#141821;
           border:1px solid var(--line);border-radius:8px">
        <div style="display:flex;align-items:center;gap:10px;margin-bottom:8px">
          <div class="spin" id="advSpin"></div>
          <span id="advStage" style="font-size:12.5px;color:var(--txt)"></span>
          <span id="advPct" style="margin-left:auto;font-size:12px;color:var(--dim)"></span>
          <button class="danger" onclick="stopAdv()" id="advStop"
            style="font-size:12px;padding:5px 14px;flex:none">停止</button>
        </div>
        <div class="bar"><i id="advFill"></i></div>
        <div id="advNote" style="color:#5a6373;font-size:11.5px;margin-top:8px"></div>
      </div>

      <div id="meta" class="meta" style="margin-top:14px"></div>
    </div>
  </div>
</div>

div>

<script>
let busy=false;

// ══ 单视频下载 ══
let probeTimer=null, dlTimer=null, lastUrl="", lastFile="", lastDest="", lastFiles=[];
// ★ 只有本页面真正跑过任务，才显示状态条和日志；刷新后不显示历史残留
let hadTask=false;

function toggleAdv(){
  const b=$('advBody'), btn=$('btnAdv');
  const open = b.style.display!=='none';
  b.style.display = open ? 'none' : 'block';
  btn.textContent = open ? '更多操作' : '收起更多操作';
  if(!open) refresh();
}

// ══ 频道批量：三步流程 ══
let parseTimer=null, batchTimer=null, scanItems=[], selSet=new Set();

async function startParse(){
  const url = $('bChannel').value.trim();
  const dest = $('bDest').value.trim();
  if(!url){ alert('请先粘贴频道地址'); $('bChannel').focus(); return; }
  if(!dest){ alert('请先选择保存目录'); return; }

  $('bParse').disabled = true;
  $('parseBox').style.display = 'block';
  $('listBox').style.display = 'none';
  $('batchProg').style.display = 'none';
  $('parseMsg').textContent = '正在解析频道…';
  $('parseCount').textContent = '0 个';

  const r = await (await fetch('/api/channel_scan?url='+encodeURIComponent(url),{method:'POST'})).json();
  if(!r.ok){ alert(r.msg||'启动解析失败'); $('bParse').disabled=false; return; }

  clearInterval(parseTimer);
  parseTimer = setInterval(pollParse, 800);
  pollParse();
}

async function pollParse(){
  let d;
  try{ d = await (await fetch('/api/channel_state')).json(); }catch(e){ return; }

  $('parseCount').textContent = (d.count||0) + ' 个';
  if(d.running){
    const sec = d.elapsed||0;
    $('parseMsg').textContent = '正在解析频道…已用 ' + fmtSec(sec);
    return;
  }

  clearInterval(parseTimer); parseTimer=null;
  $('bParse').disabled = false;
  $('parseBox').style.display = 'none';

  if(d.stage === '完成' && (d.items||[]).length){
    scanItems = d.items;
    selSet = new Set(scanItems.map(x=>x.id));   // 默认全选
    $('listBox').style.display = 'block';
    $('listStat').textContent = '共 ' + scanItems.length + ' 个视频';
    renderList();
  }else if(d.stage === '已取消'){
    $('parseMsg').textContent = '已取消';
  }else{
    alert('解析失败：' + (d.error||'未知原因'));
  }
}

function fmtSec(s){
  s = Math.max(0, Math.floor(s||0));
  if(s < 60) return s+' 秒';
  const m = Math.floor(s/60), r = s%60;
  return m+' 分 '+(r<10?'0':'')+r+' 秒';
}

function renderList(){
  const kw = ($('listFilter').value||'').trim().toLowerCase();
  const rows = scanItems.filter(x => !kw || (x.title||'').toLowerCase().includes(kw));
  const body = $('listBody');
  if(!rows.length){ body.innerHTML = '<tr><td colspan="4" style="padding:16px;text-align:center;color:var(--dim)">没有匹配的视频</td></tr>'; }
  else {
    body.innerHTML = rows.map(x=>{
      const on = selSet.has(x.id);
      return '<tr class="row">'
        + '<td style="text-align:center"><input type="checkbox" '+(on?'checked':'')+' onchange="toggleOne(\''+x.id+'\',this.checked)" style="width:14px;height:14px;cursor:pointer" /></td>'
        + '<td style="color:#d7dce4">'+esc(x.title||x.id)+'</td>'
        + '<td style="text-align:right;color:var(--dim)">'+(x.dur_text||'')+'</td>'
        + '<td style="text-align:right;color:var(--dim)">'+(x.size_mb?('~'+x.size_mb+' MB'):'—')+'</td>'
        + '</tr>';
    }).join('');
  }
  $('listStat').textContent = '共 ' + scanItems.length + ' 个 · 已选 ' + selSet.size;
}

function toggleOne(id, on){ on ? selSet.add(id) : selSet.delete(id); renderList(); }
function toggleAll(on){
  if(on) scanItems.forEach(x=>selSet.add(x.id));
  else selSet.clear();
  renderList();
}

async function startBatchDl(){
  if(!selSet.size){ alert('请至少勾选一个视频'); return; }
  const outs = [];
  if($('bOptVideo').checked) outs.push('video');
  if($('bOptNoAudio').checked) outs.push('noaudio');
  if($('bOptAudio').checked) outs.push('audio');
  if(!outs.length){ alert('请至少勾选一项下载内容'); return; }

  const ids = Array.from(selSet).join(',');
  const dest = $('bDest').value.trim();
  const chn = $('bChannel').value.trim();

  $('b-do').disabled = true;
  $('batchProg').style.display = 'block';
  $('bStage').textContent = '准备中';
  $('bFill').style.width = '0%';
  $('bPct').textContent = '0%';

  const r = await (await fetch('/api/batch_start?ids='+encodeURIComponent(ids)
      +'&outputs='+outs.join(',')
      +'&dest='+encodeURIComponent(dest)
      +'&channel='+encodeURIComponent(chn), {method:'POST'})).json();
  if(!r.ok){ alert(r.msg||'启动失败'); $('b-do').disabled=false; return; }

  clearInterval(batchTimer);
  batchTimer = setInterval(pollBatch, 1200);
  pollBatch();
}

async function pollBatch(){
  let d;
  try{ d = await (await fetch('/api/batch_state')).json(); }catch(e){ return; }
  const pct = d.total ? Math.round((d.done||0)/d.total*100) : 0;
  $('bStage').textContent = d.stage || '';
  $('bFill').style.width = pct+'%';
  $('bPct').textContent = pct+'%';
  $('bCount').textContent = d.total ? ((d.done||0)+' / '+d.total) : '';
  $('bDetail').textContent = d.detail || (d.elapsed? ('已用 '+fmtSec(d.elapsed)) : '');

  if(!d.running){
    clearInterval(batchTimer); batchTimer=null;
    $('b-do').disabled = false;
    $('b-stopdl').style.display = 'none';
    if(d.stage==='完成'){ $('bFill').style.width='100%'; $('bPct').textContent='100%'; }
    if(d.error){ $('bDetail').textContent = d.error; }
  }else{
    $('b-stopdl').style.display = 'inline-block';
  }
}

async function stopBatch(){
  await fetch('/api/batch_stop',{method:'POST'});
  $('bStage').textContent = '正在停止…';
}

async function pickBatchFolder(){
  const cur = $('bDest').value.trim();
  $('bDest').value = '选取中…';
  try{
    const r = await (await fetch('/api/pick_folder?init='+encodeURIComponent(cur))).json();
    if(r.ok && r.path){ $('bDest').value = r.path; }
    else { $('bDest').value = cur || ''; }
  }catch(e){ $('bDest').value = cur || ''; }
}

function $(id){return document.getElementById(id)}

const urlEl = $('dlUrl');
urlEl.addEventListener('input', ()=>{
  clearTimeout(probeTimer);
  const v = urlEl.value.trim();
  if(!v){ $('probeMsg').textContent=''; $('probeBox').style.display='none'; return; }
  // 看着像链接才自动解析，避免打字过程中乱请求
  if(/youtu\.?be|youtube\.com|^[A-Za-z0-9_-]{11}$/.test(v)){
    probeTimer = setTimeout(()=>doProbe(false), 650);
  }
});
urlEl.addEventListener('paste', ()=>{
  // 粘贴后立刻解析，不等防抖
  clearTimeout(probeTimer);
  setTimeout(()=>doProbe(false), 120);
});
urlEl.addEventListener('keydown', e=>{
  if(e.key==='Enter'){ e.preventDefault(); doProbe(true); }
});

async function doProbe(manual){
  const v = urlEl.value.trim();
  if(!v) return;
  if(v===lastUrl && !manual && $('probeBox').style.display!=='none') return;
  $('probeMsg').innerHTML = '<span style="color:var(--warn)">解析中…</span>';
  $('probeBox').style.display='none';
  try{
    const r = await (await fetch('/api/probe?url='+encodeURIComponent(v))).json();
    if(!r.ok){
      $('probeMsg').innerHTML = '<span style="color:var(--err)">'+esc(r.error||'解析失败')+'</span>';
      return;
    }
    lastUrl = v;
    $('probeMsg').textContent = '';
    $('vTitle').textContent = r.title || '(无标题)';
    const bits = [];
    if(r.duration_text) bits.push('时长 '+r.duration_text);
    if(r.max_height) bits.push('最高画质 '+(r.max_height>=1080?'<b style="color:var(--ok)">'+r.max_height+'p</b>':'<b style="color:var(--warn)">'+r.max_height+'p（源站上限）</b>'));
    if(r.uploader) bits.push(esc(r.uploader));
    if(r.upload_date) bits.push(r.upload_date);
    if(r.views) bits.push(r.views.toLocaleString()+' 次观看');
    $('vMeta').innerHTML = bits.join(' · ');
    $('probeBox').style.display='block';

    // 首次解析时给个默认目录（之后保留用户自己选的）
    if(!$('dlDest').value) $('dlDest').value = 'E:/SuperSimpleSongs';
  }catch(e){
    // 到这一步说明接口已返回成功、是前端渲染出错，不能再叫「请求失败」，否则误导
    $('probeMsg').innerHTML = '<span style="color:var(--warn)">页面渲染异常：'+esc(String(e))+'（解析结果已拿到）</span>';
  }
}

async function startDl(){
  const url = urlEl.value.trim();
  const dest = $('dlDest').value.trim();
  if(!url){ alert('请先粘贴链接'); return; }
  if(!dest){ alert('请先选择保存目录'); return; }
  lastDest = dest;

  // 收集勾选项
  const outs = [];
  if($('optVideo').checked) outs.push('video');
  if($('optNoAudio').checked) outs.push('noaudio');
  if($('optAudio').checked) outs.push('audio');
  if(!outs.length){ alert('请至少勾选一项下载内容'); return; }

  $('dlBox').style.display='block';
  $('dlDone').style.display='none';
  hideFix();
  $('dlErr').style.display='none';
  $('dlFill').style.width='0%';
  $('dlPct').textContent='0%';
  $('dlStage').textContent='准备中';
  $('dlSpeed').textContent='';
  $('dlEta').textContent='';
  $('btnDl').disabled = true;

  const r = await (await fetch('/api/dl_single?url='+encodeURIComponent(url)+'&dest='+encodeURIComponent(dest)+'&outputs='+outs.join(','),{method:'POST'})).json();
  if(!r.ok){
    $('dlErr').style.display='block';
    $('dlErr').textContent = r.msg || '启动失败';
    $('btnDl').disabled = false;
    return;
  }
  clearInterval(dlTimer);
  dlTimer = setInterval(pollDl, 600);
  pollDl();
}

async function pollDl(){
  let d;
  try{ d = await (await fetch('/api/dl_status')).json(); }catch(e){ return; }
  const pct = Math.max(0, Math.min(100, d.percent||0));
  $('dlFill').style.width = pct+'%';
  $('dlPct').textContent = pct.toFixed(0)+'%';
  $('dlStage').textContent = d.stage || '';
  $('dlSpeed').textContent = d.speed ? ('速度 '+d.speed) : '';
  $('dlEta').textContent = d.eta ? ('剩余 '+d.eta) : '';
  if(d.title) $('vTitle').textContent = d.title;

  if(!d.running){
    clearInterval(dlTimer); dlTimer=null;
    $('btnDl').disabled = false;
    if(d.stage==='完成'){
      lastFiles = d.files || [];
      lastFile = d.file || (lastFiles[0] && lastFiles[0].path) || '';
      $('dlDone').style.display='block';
      $('dlDoneTitle').innerHTML = d.note
        ? svgIcon('warn')+'<span style="color:var(--warn)">已下载（'+esc(d.note)+'）</span>'
        : svgIcon('ok')+'<span style="color:var(--ok)">下载完成'+(d.res?' · '+esc(d.res):'')+'</span>';
      renderFiles(lastFiles);
      $('dlFill').style.width='100%';
      $('dlPct').textContent='100%';
      $('btnStopDl').style.display='none';
      // 画质差距 → 弹出解决面板
      if(d.quality_gap){ showFixPanel(d.quality_gap); }
      else { hideFix(); }
    }else if(d.error){
      $('dlErr').style.display='block';
      $('dlErr').textContent = d.error;
      $('btnStopDl').style.display='none';
    }
  }else{
    $('btnStopDl').style.display='inline-block';
  }
}

async function stopDl(){
  await fetch('/api/dl_stop',{method:'POST'});
  $('dlStage').textContent='正在停止…';
}
function renderFiles(files){
  const box = $('dlFiles');
  if(!files || !files.length){ box.innerHTML=''; return; }
  box.innerHTML = files.map((f,i)=>{
    if(!f.path){
      return '<div style="color:var(--err);font-size:12px;margin-bottom:6px">'
        + esc(f.kind) + '：' + esc(f.error||'生成失败') + '</div>';
    }
    const name = f.path.split('/').pop();
    return '<div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">'
      + '<span style="font-size:11px;padding:2px 8px;border-radius:4px;background:#1f4d38;color:var(--ok);flex:none">'+esc(f.kind)+'</span>'
      + '<span style="color:var(--dim);font-size:11.5px;word-break:break-all;flex:1">'+esc(name)+'</span>'
      + '<button class="ghost" onclick="openFileAt('+i+')" style="font-size:11.5px;padding:4px 12px;flex:none">打开</button>'
      + '</div>';
  }).join('');
}

function openFileAt(i){
  const f = lastFiles[i];
  if(f && f.path) fetch('/api/open_folder?path='+encodeURIComponent(f.path))
    .then(r=>r.json()).then(j=>{ if(!j.ok) alert(j.error||'打开失败'); })
    .catch(()=>{});
}

function openFile(){
  if(lastFile) fetch('/api/open_folder?path='+encodeURIComponent(lastFile));
}
async function pickFolder(){
  const cur = $('dlDest').value.trim();
  $('dlDest').value = '选取中…';
  try{
    const r = await (await fetch('/api/pick_folder?init='+encodeURIComponent(cur))).json();
    if(r.ok && r.path){
      $('dlDest').value = r.path;
      lastDest = r.path;
    }else{
      $('dlDest').value = cur || '';
      if(r.error) $('probeMsg').innerHTML = '<span style="color:var(--err)">'+esc(r.error)+'</span>';
    }
  }catch(e){
    $('dlDest').value = cur || '';
  }
}

function svgIcon(kind){
  if(kind==='ok') return '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-2px;margin-right:5px;color:var(--ok)"><polyline points="20 6 9 17 4 12"/></svg>';
  if(kind==='warn') return '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-2px;margin-right:6px;color:var(--warn)"><path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>';
  return '';
}

async function showFixPanel(gap){
  // 面板一旦出现就保持不动，直到用户关闭或重新下载成功
  const p = $('fixPanel');
  p.style.display = 'block';
  $('fixHead').innerHTML = svgIcon('warn') + '画质未达最佳';
  $('fixLocal').textContent = gap.local_h + 'p';
  $('fixSize').textContent = gap.local_h + 'p · ' + gap.local_mb + ' MB';
  $('fixSrc').textContent = gap.src_h + 'p';
  $('fixIp').textContent = '查询中…';
  $('fixIpType').textContent = '查询中…';
  $('fixProxy').textContent = '查询中…';
  try{
    const d = await (await fetch('/api/diagnose')).json();
    $('fixIp').textContent = d.ipv4 || d.ip_any || '（查询失败）';
    const isV6 = d.ipv4 ? (d.ipv4.indexOf(':')>=0) : false;
    $('fixIpType').innerHTML = isV6
      ? '<span style="color:var(--warn)">IPv6（强烈建议关闭）</span>'
      : 'IPv4（正常）';
    $('fixProxy').textContent = d.proxy || '';
  }catch(e){
    $('fixIp').textContent = '（查询失败）';
  }
}

function hideFix(){ $('fixPanel').style.display='none'; }

function toggleSites(){
  const b = $('sitesList'), t = $('sitesToggle');
  const open = b.style.display !== 'none';
  b.style.display = open ? 'none' : 'block';
  t.textContent = open ? '查看完整列表' : '收起';
}

function retryDownload(){
  hideFix();
  startDl();
}

function esc(s){return String(s).replace(/[<>&]/g,c=>({'<':'&lt;','>':'&gt;','&':'&amp;'}[c]))}
function dot(ok){return `<span class="dot ${ok?'on':'off'}"></span>`}

async function refresh(){
  let d;
  try{ d=await (await fetch('/api/status')).json(); }catch(e){ return; }
  const c=d.config, st=d.state||{}, t=d.tools;
  // 频道地址/目录/画质：每次刷新同步到输入框（用户正在编辑时不覆盖）
  if(!$('bChannel').matches(':focus') && !$('bChannel').value) $('bChannel').value = c.channel_url||'';
  if(!$('bDest').value) $('bDest').value = c.output_dir||'';

  // 高级区的配置信息只在展开时填充
  if($('advBody').style.display!=='none'){
    document.getElementById('meta').innerHTML=`
      <div class="kv"><div class="k">输出目录</div><div class="v">${esc(c.output_dir)}</div></div>
      <div class="kv"><div class="k">频道</div><div class="v">${esc(c.channel_url||'未设置')}</div></div>
      <div class="kv"><div class="k">画质门槛</div><div class="v">${c.min_height}p 以上（不降清）</div></div>
      <div class="kv"><div class="k">工具链</div><div class="v">${dot(t.ffmpeg)}ffmpeg ${dot(t.deno)}deno ${dot(t.aria2)}aria2</div></div>`;
  }

  busy=d.busy;
  ['check','scan','download','lyrics','report','all'].forEach(k=>{
    document.getElementById('b-'+k).disabled=busy;
  });
  document.getElementById('b-stop').disabled=!busy;

  const total=+(st.total||0), done=+(st.done||0);
  const pct= total? Math.min(100,Math.round(done/total*100)) : 0;
  document.getElementById('fill').style.width=pct+'%';
  document.getElementById('pct').textContent=pct+'%';
  document.getElementById('count').textContent=`${done} / ${total}`;
  document.getElementById('stage').textContent= busy? ('进行中：'+ (d.task||st.stage||'')) : '待机';
  document.getElementById('tstate').textContent= st.updated? ('更新于 '+st.updated):'';

  // 高级操作区的任务进度
  if(hadTask && $('advBody').style.display!=='none'){
    $('advRun').style.display = 'block';
    $('advFill').style.width = pct+'%';
    $('advPct').textContent = total ? (pct+'%') : '';
    if(busy){
      $('advSpin').style.display = 'block';
      $('advStop').style.display = 'inline-block';
      $('advStop').disabled = false;
      $('advStage').textContent = (TASK_NAMES[d.task]||d.task||'处理中') +
        (total ? ('  '+done+' / '+total) : ' …');
      $('advNote').textContent = '可以随时点「停止」，已下载的文件不会受影响';
    }else{
      $('advSpin').style.display = 'none';
      $('advStop').style.display = 'none';
      if(st.stage==='report' && st.file){
        $('advStage').textContent = 'Excel 已生成';
        $('advNote').textContent = st.file;
      }else if(st.updated){
        $('advStage').textContent = '已完成';
        $('advNote').textContent = '更新于 ' + st.updated;
      }else{
        $('advStage').textContent = '待机';
      }
    }
  }
}

const TASK_NAMES = {check:'检查环境', scan:'抓取清单', download:'下载视频',
                    lyrics:'抓取歌词', 'lyrics-desc':'抓取歌词', report:'生成 Excel', all:'全流程'};

async function go(task){
  hadTask = true;
  $('advRun').style.display = 'block';
  $('advStage').textContent = (TASK_NAMES[task]||task) + ' 启动中…';
  $('advPct').textContent = '';
  $('advFill').style.width = '0%';
  $('advNote').textContent = '';
  $('advStop').style.display = 'inline-block';
  $('advSpin').style.display = 'block';

  const r = await fetch('/api/start?task='+task,{method:'POST'});
  if(!r.ok){ const j=await r.json(); alert(j.error||'启动失败'); $('advRun').style.display='none'; }
  refresh();
}

async function stopAdv(){
  await fetch('/api/stop',{method:'POST'});
  $('advStage').textContent = '正在停止…（当前批次结束后生效）';
  $('advStop').disabled = true;
}
async function stop(){ await fetch('/api/stop',{method:'POST'}); refresh(); }
async function openDir(){ await fetch('/api/open'); }

setInterval(refresh, 2000); refresh();
</script>
</body></html>"""


def main():
    cfg = common.load_config()
    print("=" * 56)
    print("频道资料库 · 本地控制台")
    print("=" * 56)
    print("输出目录：%s" % cfg["output_dir"])
    print("本机访问：http://127.0.0.1:%d" % PORT)
    if LAN:
        ip = lan_ip()
        suffix = ("/?k=" + TOKEN) if TOKEN else "/"
        print("")
        print("=" * 56)
        print("  手机访问（需与电脑连同一个 WiFi）")
        print("  http://%s:%d%s" % (ip, PORT, suffix))
        print("=" * 56)
        print("  把这个地址在手机浏览器打开，建议添加到主屏幕")
    else:
        print("（如需手机访问，请用 启动网页界面_手机版.bat 启动）")
    print("关闭窗口即停止服务（Ctrl+C）")
    print("=" * 56)
    try:
        webbrowser.open("http://127.0.0.1:%d" % PORT)
    except Exception:
        pass
    srv = ThreadingHTTPServer((HOST, PORT), Handler)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")


if __name__ == "__main__":
    main()
