#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""本地网页界面（零第三方依赖，只用标准库）。

启动后浏览器访问 http://127.0.0.1:8765 ，点按钮即可。
任务在后台线程跑，页面实时显示进度与日志。
"""
import os, sys, json, threading, time, webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core import common, scan as scan_mod, download as dl, lyrics as lyr, report as rep

PORT = int(os.environ.get("SSS_PORT", "8765"))
_STOP = {"flag": False}
_WORKER = {"thread": None, "task": ""}


def _run_task(task, cfg):
    _STOP["flag"] = False
    try:
        if task == "check":
            good, reason = dl.probe_health(cfg)
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

    def do_GET(self):
        u = urlparse(self.path)
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
            })
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
</style>
</head>
<body><div class="wrap">
<h1>频道资料库 · 一键构建</h1>
<div class="sub">下载 · 官方歌词 · 难度分级 · Excel 清单 —— 改 config.json 即可换频道</div>

<div class="card">
  <div class="meta" id="meta"></div>
  <div class="row">
    <button onclick="go('check')" id="b-check">体检</button>
    <button onclick="go('scan')" id="b-scan">1 扫描清单</button>
    <button onclick="go('download')" id="b-download">2 下载</button>
    <button onclick="go('lyrics')" id="b-lyrics">3 抓歌词</button>
    <button onclick="go('report')" id="b-report">4 生成 Excel</button>
    <button onclick="go('all')" id="b-all">一键全流程</button>
    <button class="danger" onclick="stop()" id="b-stop">停止</button>
    <button class="ghost" onclick="openDir()">打开输出目录</button>
  </div>
</div>

<div class="card">
  <div class="stat"><span id="stage">待机</span><span id="pct">0%</span></div>
  <div class="bar"><i id="fill"></i></div>
  <div class="stat"><span id="count">0 / 0</span><span id="tstate"></span></div>
</div>

<div class="card">
  <div style="color:var(--dim);font-size:12px;margin-bottom:8px">运行日志</div>
  <div class="log" id="log"></div>
</div>
</div>

<script>
let busy=false;
function esc(s){return String(s).replace(/[<>&]/g,c=>({'<':'&lt;','>':'&gt;','&':'&amp;'}[c]))}
function dot(ok){return `<span class="dot ${ok?'on':'off'}"></span>`}

async function refresh(){
  let d;
  try{ d=await (await fetch('/api/status')).json(); }catch(e){ return; }
  const c=d.config, st=d.state||{}, t=d.tools;
  document.getElementById('meta').innerHTML=`
    <div class="kv"><div class="k">输出目录</div><div class="v">${esc(c.output_dir)}</div></div>
    <div class="kv"><div class="k">频道</div><div class="v">${esc(c.channel_url||'未设置')}</div></div>
    <div class="kv"><div class="k">画质门槛</div><div class="v">${c.min_height}p 以上（不降清）</div></div>
    <div class="kv"><div class="k">工具链</div><div class="v">${dot(t.ffmpeg)}ffmpeg ${dot(t.deno)}deno ${dot(t.aria2)}aria2</div></div>`;

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

  const log=document.getElementById('log');
  log.innerHTML=(d.events||[]).map(e=>`<div class="${e.level||'INFO'}">${esc(e.msg)}</div>`).join('');
  log.scrollTop=log.scrollHeight;
}

async function go(task){
  const r=await fetch('/api/start?task='+task,{method:'POST'});
  if(!r.ok){ const j=await r.json(); alert(j.error||'启动失败'); }
  refresh();
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
    print("浏览器打开：http://127.0.0.1:%d" % PORT)
    print("关闭窗口即停止服务（Ctrl+C）")
    print("=" * 56)
    try:
        webbrowser.open("http://127.0.0.1:%d" % PORT)
    except Exception:
        pass
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")


if __name__ == "__main__":
    main()
