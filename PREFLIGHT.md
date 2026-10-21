# 开工前必读（PREFLIGHT）

> 用途：新会话接手 / 换机器 / 换节点后，**读一遍这份，再开工**。
> 巡查不需要读这份——直接跑 `python sss.py check --quick`（约 150 tokens）。
> 最后更新：2026-10-22

---

## 一、三条必查（任一 FAIL 立即停）

### 1. POT 服务是否活着
```bash
curl --noproxy '*' -s -m 3 http://127.0.0.1:4416/ping
```
**无响应 = 服务已停**。重启：
```bash
cd .workbuddy/tools/pot/server/server
deno run --allow-env --allow-net --allow-import --allow-write --allow-read src/main.ts
```
> 会话重启会杀掉它。这是最常见的"莫名其妙失败"根因。

### 2. 节点是否可用（顺序不能错）
```bash
yt-dlp -F "https://www.youtube.com/watch?v=4XLQpRI_wOQ"
```
| 看到什么 | 判断 |
|---|---|
| `399` / `401` / `137` / `251` / 各档 144p~1080p | ✅ 正常 |
| **只有 `18`（360p）** | ⚠️ **先检查 POT 服务**（见第 1 条） |

> **★ 关键纠错（2026-10-22 实测）**：
> 只看到 360p 时，**90% 是 POT 服务停了**，不是节点被降级。
> POT 停止会导致格式解析不完整，只剩单文件 format 18。
> 重启 POT 后，同一节点、同一 IP，格式列表立刻恢复完整。
> **只有在 POT 确认在线后仍然只有 360p，才是节点问题。**

### 3. 是否被封禁
日志出现 `Sign in to confirm you're not a bot` → IP 配额耗尽。
**冷却无效**（实测跨夜 8 小时不恢复），只能换 IP。

---

## 二、六条铁律（都是踩坑换来的）

| 铁律 | 违反后果 |
|---|---|
| 格式串**禁止 `/best`** | 合并失败回退 360p，整批废 |
| 必须 `--keep-video` | 沙箱环境批量删文件会卡死进程 |
| 字幕只用 `--write-subs` | 混入 ASR 会得到 `sh be quiet` 噪声 |
| 批量清理用 `mv` 不用 `rm` | 删了找不回来 |
| 分类前做 Unicode 归一化 | 标题是 `’`(U+2019)，正则是 `'`，会大面积漏匹配 |
| 合集阈值 15 分钟 | 5 分钟阈值会漏判 125 个 |

---

## 三、已知死路（别重复尝试）

| 现象 | 已排除的方案 | 正解 |
|---|---|---|
| 字幕 `HTTP 429` | 换 IP、换 client（tv/web/android）、换格式（vtt/json3/ttml）、重启 POT | **从视频简介提取歌词**（`sss.py lyrics-desc`） |
| `Some xxx client https formats have been skipped` | 单 client 无解（SABR-only） | 用 `mweb,tv,web,ios` 多 client 组合 |
| 只看到 360p（format 18）| 换节点、换 IP | **重启 POT 服务**（这才是 90% 的真因） |
| B站高清拿不到 | — | 需 `SESSDATA` cookie；否则只有 288p |
| 微信视频号 | — | **无解**，yt-dlp 无 extractor |

---

## 四、巡查怎么做

```bash
python sss.py check --quick   # 只输出关键行 + PASS/FAIL
```

**不要**每轮读这份文档。文档是知识，命令才是检查。

---

## 五、当前项目状态（供接手参考）

- 视频：779/779 完成，107.7 GB，`E:\SuperSimpleSongs`
- 歌词：663/779（85.1%）
  - 官方字幕 640（带毫秒时间轴）
  - 官方简介 23（纯文本，无时间轴）
  - 无歌词 116（86 个长合集 + 11 个非歌曲 + 19 个待补）
- Excel：`SuperSimpleSongs_视频清单_下载对照表.xlsx`，35 列
- 仓库：https://github.com/Hyperbolic-Researcher/sss-toolkit
