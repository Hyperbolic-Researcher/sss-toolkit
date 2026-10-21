# 发布到 GitHub · 三个步骤

代码已经提交到本地 git 仓库（2 个 commit），只差最后一步推送。

---

## 方式 A：装 GitHub CLI（推荐，一次装好以后都能用）

### 1. 安装

打开 **PowerShell**（不是 Git Bash），执行：

```powershell
winget install --id GitHub.cli
```

装完**关掉窗口重开**，然后：

```powershell
gh auth login
```

按提示选：
- `GitHub.com`
- `HTTPS`
- `Login with a web browser` → 复制它给的 8 位码 → 浏览器里粘贴 → 授权

### 2. 创建仓库并推送

```powershell
cd C:\Users\P775\WorkBuddy\2026-10-16-11-31-07\sss-toolkit

gh repo create sss-toolkit --public --source=. --remote=origin --push
```

一行搞定：建仓库 + 关联 + 推送。

---

## 方式 B：不装任何东西（用网页 + Token）

### 1. 在网页建空仓库

打开 https://github.com/new

- Repository name：`sss-toolkit`
- 选 **Public**
- **不要**勾选 "Add a README"（否则会冲突）
- 点 Create

### 2. 生成 Token

https://github.com/settings/tokens → `Generate new token (classic)`

- 勾选 **`repo`**（整组）
- 有效期选 30 天
- 生成后**复制保存**（只显示一次）

### 3. 推送

在 Git Bash 里执行（把 `你的用户名` 和 `你的TOKEN` 换掉）：

```bash
cd "C:/Users/P775/WorkBuddy/2026-10-16-11-31-07/sss-toolkit"

git remote add origin https://你的用户名:你的TOKEN@github.com/你的用户名/sss-toolkit.git
git branch -M main
git push -u origin main
```

> 推送成功后再清理一下凭据（可选）：
> `git remote set-url origin https://github.com/你的用户名/sss-toolkit.git`

---

## 推送前确认清单

| 项 | 状态 |
|---|---|
| 代码文件 | 15 个，共 92 KB |
| 大文件已排除 | `tools/`（deno 92MB）已在 `.gitignore` |
| 媒体文件已排除 | `*.mp4 *.srt *.lrc *.xlsx` 已在 `.gitignore` |
| LICENSE | MIT |
| README | 含能力说明、快速开始、踩坑记录 |

---

## 关于工具的二进制依赖

`deno` / `aria2c` / `ffmpeg` **不在仓库里**（体积太大，也不适合分发）。

本机已经放在 `sss-toolkit/tools/` 下，所以现在能直接用。
换电脑时，按 README 的「快速开始」重新获取即可，或者把 `tools/` 目录一起拷过去。

---

## 如果想加个截图到 README

启动 `启动网页界面.bat`，浏览器打开后用截图工具截一张，存为 `docs/screenshot.png`，
然后在 README 里加：

```markdown
![界面](docs/screenshot.png)
```
