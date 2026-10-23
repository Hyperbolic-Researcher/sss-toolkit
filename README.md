# 频道资料库一键构建工具

把一个 YouTube 频道，变成**可直接使用的本地资料库**：最高画质视频 + 官方歌词 + 难度分级 + Excel 清单。

> 最初为解决「Super Simple Songs 779 个视频全量整理」而写，过程中踩的坑全部固化进了代码。

---

## ⚠️ 使用边界（请先读）

**这是一个个人学习研究项目，不是商业产品。**

| 可以 | 不可以 |
|---|---|
| 个人学习、研究 yt-dlp 工程实践 | 商业分发、售卖资源包 |
| 给孩子离线看儿歌 | 二次上传 / 公开提供下载 |
| 学习 ctypes / 标准库做界面 | 绕过付费墙、破解 DRM |

**代码是 MIT（自由使用），但你用它下载的内容版权归原作者。**
判断标准很简单：**你的行为是否替代了别人付费获取的渠道？**

完整说明见 **[DISCLOSURE.md](DISCLOSURE.md)**。

---

## 📖 文档索引

| 文档 | 内容 |
|---|---|
| **[docs/问题与解决手册.md](docs/问题与解决手册.md)** | **踩过的所有坑 + 解法（按症状查）** ⭐ |
| [PREFLIGHT.md](PREFLIGHT.md) | 开工前必读：三条必查 + 铁律 + 已知死路 |
| [docs/手机端使用.md](docs/手机端使用.md) | 手机遥控、内网穿透、手机看视频 |
| [docs/支持的网站.md](docs/支持的网站.md) | 1752 个站点中主流站点的实测支持情况 |
| [DISCLOSURE.md](DISCLOSURE.md) | 使用边界与合规说明 |
| [docs/发布到GitHub.md](docs/发布到GitHub.md) | 首次发布流程 |

---

## ⚡ 三行上手

```bash
# 1. 克隆到本地
git clone https://github.com/Hyperbolic-Researcher/sss-toolkit.git
cd sss-toolkit

# 2. 装依赖
pip install -U yt-dlp openpyxl imageio-ffmpeg

# 3. 启动
#    Windows：双击 start_webui.bat
#    或命令行：python webui.py --lan
```

浏览器打开 `http://127.0.0.1:8765`。

> **Windows 用户注意**：如果你的电脑装过多个 Python，
> `start_webui.bat` 会自动找出装了 yt-dlp 的那个。
> 详见 [问题与解决手册 A3](docs/问题与解决手册.md#a3-多个-python-导致缺依赖)。

---

## 它能做什么

| 能力 | 说明 |
|---|---|
| **最高画质下载** | 严格模式只下 1080p 以上，**绝不降清**（不会回退到 360p） |
| **官方歌词** | 抓 YouTube 官方手动字幕（SRT，带毫秒时间轴）+ 转 LRC |
| **难度分级** | 用歌词客观计算 L1–L5，含语速 WPM、唯一词数、平均句长、重复率 |
| **Excel 清单** | 33 列，含本地路径、画质、难度、歌词路径、完整元数据，可直接筛选 |
| **断点续传** | 中断后重跑自动跳过已完成 |
| **自动防封** | 通道探测 + 连续无进展停机，避免空烧配额 |
| **网页界面** | 双击启动，点按钮即可，零第三方依赖 |

---

## 快速开始

### 1. 准备

```bash
pip install -U yt-dlp openpyxl
```

可选但强烈建议（影响速度和成功率）：

| 工具 | 作用 | 获取 |
|---|---|---|
| **ffmpeg** | 合并音视频（必需） | `pip install imageio-ffmpeg` 即可自动找到 |
| **deno** | 解 YouTube 的 JS challenge | https://deno.land |
| **aria2c** | 多线程加速 | https://github.com/aria2/aria2/releases |
| **bgutil POT provider** | 生成 PO Token，提升成功率 | https://github.com/Brainicism/bgutil-ytdlp-pot-provider |

### 2. 配置

编辑 `config.json`，最少改两项：

```json
{
  "output_dir": "E:/MediaLibrary",
  "channel_url": "https://www.youtube.com/@频道名/videos"
}
```

### 3. 运行

**方式 A：网页界面（推荐）**

双击 `启动网页界面.bat`，浏览器会自动打开 `http://127.0.0.1:8765`，点按钮即可。

> 三个启动器任选一个，它们最终跑的是同一份逻辑：
> `启动网页界面.bat` / `start_webui.bat` / 桌面的 `SSS工具.bat`。

**方式 B：命令行**

```bash
python sss.py check      # 先体检
python sss.py all        # 一条龙
```

单步执行：

```bash
python sss.py scan       # 1. 扫描频道生成清单
python sss.py download   # 2. 下载（可反复跑）
python sss.py lyrics     # 3. 抓歌词 + 算难度
python sss.py report     # 4. 生成 Excel
```

---

## 输出结构

```
输出目录/
├── videos.txt              清单：ID|时长|播放量|标题
├── downloaded.txt          下载归档（断点续传靠它）
├── lyrics_index.json       每个视频的难度指标
├── 媒体库清单.xlsx          最终交付表
├── lyrics/                 官方歌词
│   ├── {id}.en.srt         原始字幕（带时间轴）
│   └── {id}.lrc            播放器可直接加载
├── 视频标题 [id].mp4        成品
└── _quarantine/            不达标的中间文件（只移不删）
```

---

## 难度分级怎么看

| 等级 | 难度分 | 特征 | 适用 |
|---|---|---|---|
| **L1 入门** | < 0.35 | 语速慢、词汇少、重复高 | 零基础起步 |
| **L2 简单** | < 0.50 | | 有少量基础 |
| **L3 中等** | < 0.65 | | 能跟唱短句 |
| **L4 较难** | < 0.82 | 语速快、词汇多 | 进阶 |
| **L5 复杂** | ≥ 0.82 | | 接近母语儿歌 |

计算方式（全部可从歌词客观得出）：

```
难度分 = 0.38 × 语速 + 0.32 × 词汇广度 + 0.15 × 句长 + 0.15 × 重复率(反向)
```

> **为什么不用户词表？** 试过 Dolch 220 词表统计生僻词，结果 100% 视频都被判极难——
> `shoulder` / `knee` / `toe` 这些常见词全不在表里。所以改用不依赖词表的指标。

---

## 单视频下载（网页版最常用）

打开网页控制台，最上面就是**单视频下载**区，流程只有三步：

```
1. 粘贴 YouTube 链接  →  自动解析（显示标题/时长/最高画质）
2. 确认保存目录        →  默认输出目录，可改成任意路径
3. 点「开始下载」      →  实时进度，完成后可一键打开所在文件夹
```

**支持三种链接格式**：
- `https://www.youtube.com/watch?v=XXXXXXXXXXX`
- `https://youtu.be/XXXXXXXXXXX`
- `https://www.youtube.com/shorts/XXXXXXXXXXX`
- 也可以只粘贴 11 位视频 ID

**音频格式**：强制优先 AAC（`bestaudio[ext=m4a]`），不用 Opus。
原因：AV1 + Opus 的 MP4 在 Windows 自带播放器里经常打不开——Opus 在 MP4 容器中支持很差。
视频仍保留 AV1（同画质体积只有 H.264 的 1/3），只有音频换成 AAC，体积几乎不变。

**和批量下载的区别**：单视频允许画质兜底（`/best`）。
用户要的就是这一个文件，拿不到 1080p 也该下到 720p——**但完成后会明确告知实际分辨率**，例如：

> ✓ 已下载（该视频源站最高只有 360p，已按最高可用下载）

批量下载**绝不兜底**，拿不到高清就跳过，避免整库混入低清。


---

## 手机端使用

下载必须跑在电脑上（需要代理、硬盘、算力），**手机只做遥控器**。

```
手机（遥控器） ──WiFi──> 电脑（干活） ──代理──> YouTube
                          ↓
                     E 盘存视频
```

### 在家（同 WiFi）

1. 双击 `启动网页界面.bat`（主脚本默认已监听局域网）
2. 黑窗口会打印一个地址，例如 `http://192.168.0.107:8765/`
3. 手机连**同一 WiFi**，浏览器打开这个地址
4. 建议"添加到主屏幕"，以后像 App 一样点开

> 窗口不能关，关了服务就停。

### 不在家

用 [Tailscale](https://tailscale.com/download)（推荐）或 Cloudflare Tunnel 做内网穿透。
详细步骤见 `docs/手机端使用.md`。

### 安全提醒

`--lan` 模式会把服务暴露给局域网内所有设备。家用 WiFi 一般可信；
若要暴露到公网，务必先设口令：

```bash
set SSS_TOKEN=你的口令
python webui.py --lan
```
访问时带 `?k=你的口令`。


## 常见问题

**Q：下载报 `Sign in to confirm you're not a bot`**
出口 IP 被 YouTube 限流。这是配额型封禁，**冷却无效**，只能换 IP。本工具会探测到并自动停机，避免空烧。

**Q：日志出现 `Some mweb client https formats have been skipped`**
YouTube 对单 client 开了 SABR-only 实验。`config.json` 里的 `player_client` 默认是 `mweb,tv,web,ios` 多 client 组合，可规避。不要改成单个 client。

**Q：为什么下载完目录里有一堆 `.f399.mp4` 文件？**
那是分离的视频流/音频流中间文件。`--keep-video` 故意保留（见下），每次运行结束会自动移到 `_quarantine/`。

**Q：能不能加 `--no-keep-video` 省点空间？**
不建议。在某些沙箱环境里，进程内删除满 50 个文件会被安全机制拦截并卡死进程，表现为「取 20 个只成 1 个」。保留后由脚本移动，永不触发。


**Q：视频只有 360p，是不是节点不行？**
**先查 POT 服务，再查源站，最后才怀疑节点。**
1. `curl --noproxy '*' -s -m 3 http://127.0.0.1:4416/ping` 无响应 → POT 停了，重启它（POT 停止会导致格式列表只剩 360p）
2. POT 正常仍只有 360p → `yt-dlp -F <url>` 看源站最高能给多少；若源站本身就低，**重下只会更差，保持原文件**

**Q：下载完了，目录里只有 `.f398.mp4` 和 `.f251.webm`，没有完整视频？**
yt-dlp 的合并环节静默失败了（不报错）。手动合并：
```bash
ffmpeg -y -i "video.f398.mp4" -i "audio.f251.webm" -c copy \
  -map 0:v:0 -map 1:a:0 -movflags +faststart out.mp4
```

**Q：怎么判断某个视频"值不值得重下"？**
```
本地 ≥ 1080p           → 不用重下
本地 < 1080p → 查源站  → 源站最高 ≤ 本地：源站上限，别动
                       → 源站最高 > 本地：可以重下
```
一次实测里 78 个「疑似低清」，回查源站后**可修复 0 个**——不查源站就重下，等于用差文件换掉好文件。

**Q：字幕是机器识别的吗？**
默认 `manual_only: true`，只下官方手动字幕（完整句子、规范标点）。自动字幕（ASR）会有 `sh be quiet` 这类噪声，字母歌甚至被切成单字母，用来算难度会严重失真。

---

## 设计取舍（踩坑记录）

| 决策 | 原因 |
|---|---|
| 格式串禁止 `/best` | `/best` 在合并失败时回退 360p，整批报废 |
| `--keep-video` | 规避沙箱批量删除拦截（见上） |
| 多 client 组合 | 单 client 遇 SABR-only 时拿不到流 |
| 连续无进展停机 | IP 封禁冷却无效，无限重试只是空烧配额 |
| 分类前做 Unicode 归一化 | 标题里是 `’`(U+2019)，正则是 `'`，不归一化会大面积匹配失败 |
| 合集阈值 15 分钟 | 实测 ≤5 分钟的 438 个里没有一个合集 |
| 只用标准库做 Web | 换电脑不用 pip install |

---

## 🔄 自动备份

代码和文档靠 GitHub 保底，丢了 `git clone` 就能回来。

```bash
bash autosync.sh        # 提交并推送；没改动就静默跳过
```

| 特性 | 说明 |
|---|---|
| 幂等 | 没有改动不产生空提交 |
| 不挂起 | 凭证失效立即失败，不会卡在密码输入 |
| 有护栏 | 单文件 >50MB 或改动 >200 个文件直接中止，防止视频误传 |

定时执行：WorkBuddy 自动化「SSS 工具每日自动备份到 GitHub」，每天 23:00
（前提：电脑开机且 App 在运行）。细节见
[问题与解决手册 5.3](docs/问题与解决手册.md#53-每天自动备份已配置)。

> 仓库只备份代码与文档。视频、歌词、Excel 已被 `.gitignore` 排除，
> 这些要靠硬盘或网盘备份。

---

## 许可

本工具代码：MIT

注意：
- 下载的内容版权归原作者，**请勿用于商业分发**
- yt-dlp 本身是 Unlicense，但**其仓库明确禁止 AI/LLM 参与贡献**（本项目的 issue 不会提交到 yt-dlp）
- 请遵守目标网站的服务条款
