# 频道资料库一键构建工具

把一个 YouTube 频道，变成**可直接使用的本地资料库**：最高画质视频 + 官方歌词 + 难度分级 + Excel 清单。

> 最初为解决「Super Simple Songs 779 个视频全量整理」而写，过程中踩的坑全部固化进了代码。

---

## 它能做什么

| 能力 | 说明 |
|---|---|
| **最高画质下载** | 严格模式只下 1080p 以上，**绝不降清**（不会回退到 360p） |
| **官方歌词** | 抓 YouTube 官方手动字幕（SRT，带毫秒时间轴）+ 转 LRC |
| **难度分级** | 用歌词客观计算 L1–L5，含语速 WPM、唯一词数、平均句长、重复率 |
| **Excel 清单** | 27 列，含本地路径、画质、难度、歌词路径，可直接筛选 |
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

## 常见问题

**Q：下载报 `Sign in to confirm you're not a bot`**
出口 IP 被 YouTube 限流。这是配额型封禁，**冷却无效**，只能换 IP。本工具会探测到并自动停机，避免空烧。

**Q：日志出现 `Some mweb client https formats have been skipped`**
YouTube 对单 client 开了 SABR-only 实验。`config.json` 里的 `player_client` 默认是 `mweb,tv,web,ios` 多 client 组合，可规避。不要改成单个 client。

**Q：为什么下载完目录里有一堆 `.f399.mp4` 文件？**
那是分离的视频流/音频流中间文件。`--keep-video` 故意保留（见下），每次运行结束会自动移到 `_quarantine/`。

**Q：能不能加 `--no-keep-video` 省点空间？**
不建议。在某些沙箱环境里，进程内删除满 50 个文件会被安全机制拦截并卡死进程，表现为「取 20 个只成 1 个」。保留后由脚本移动，永不触发。

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

## 许可

本工具代码：MIT

注意：
- 下载的内容版权归原作者，**请勿用于商业分发**
- yt-dlp 本身是 Unlicense，但**其仓库明确禁止 AI/LLM 参与贡献**（本项目的 issue 不会提交到 yt-dlp）
- 请遵守目标网站的服务条款
