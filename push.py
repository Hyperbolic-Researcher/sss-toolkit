#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""一键推送到 GitHub（交互式，替代 bat 里的中文逻辑）

为什么用 Python 而不是纯 bat：
  Windows cmd 默认用 GBK(936) 读取批处理文件，
  而 bat 存成 UTF-8 时中文会解析错乱，出现
  "'?? 不是内部或外部命令" 这类报错。
  Python 读写 UTF-8 无此问题，bat 只做一行启动器。
"""
import os, sys, subprocess, getpass

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)

DEFAULT_USER = "Hyperbolic-Researcher"
REPO = "sss-toolkit"


def run(args, quiet=True):
    r = subprocess.run(args, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not quiet:
        print(r.stdout or "", end="")
        print(r.stderr or "", end="", file=sys.stderr)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def main():
    print("=" * 52)
    print("  推送 sss-toolkit 到 GitHub")
    print("=" * 52)
    print()

    # 1. 用户名
    u = input("1) GitHub 用户名（直接回车用 %s）: " % DEFAULT_USER).strip()
    if not u:
        u = DEFAULT_USER

    # 2. 仓库检查
    code, out = run(["git", "remote", "get-url", "origin"])
    print("   目标仓库: https://github.com/%s/%s" % (u, REPO))
    print()

    # 3. 令牌
    print("2) 生成令牌：在浏览器打开下面地址")
    print("   https://github.com/settings/tokens/new")
    print()
    print("   页面上只需填两处：")
    print("     Note       -> 随便写，例如 sss-toolkit")
    print("     Expiration -> 选 7 days")
    print()
    print("   然后往下滚到 Select scopes，勾选最上面的 [repo]")
    print("   再滚到最底部，点绿色按钮 Generate token")
    print()
    input("   准备好后按回车，会打开令牌页面...")
    try:
        os.startfile("https://github.com/settings/tokens/new")
    except Exception:
        pass
    print()

    tok = getpass.getpass("3) 粘贴令牌（输入时不显示），回车确认: ").strip()
    if not tok:
        print("\n没有输入令牌，已取消。")
        input("按回车退出...")
        return 1
    if not tok.startswith("ghp_") and not tok.startswith("github_pat_"):
        print("\n注意：令牌通常以 ghp_ 开头，你输入的似乎不是。仍将尝试。")

    # 4. 推送
    remote_url = "https://%s:%s@github.com/%s/%s.git" % (u, tok, u, REPO)
    print("\n[1/3] 配置远程仓库...")
    run(["git", "remote", "remove", "origin"])
    code, out = run(["git", "remote", "add", "origin", remote_url])
    if code != 0:
        print("失败:", out[:300])
        input("按回车退出...")
        return 1

    print("[2/3] 设置主分支为 main ...")
    run(["git", "branch", "-M", "main"])

    print("[3/3] 推送中（可能需要几十秒）...")
    code, out = run(["git", "push", "-u", "origin", "main"], quiet=False)

    # 5. 清理令牌
    run(["git", "remote", "set-url", "origin",
         "https://github.com/%s/%s.git" % (u, REPO)])

    print()
    if code == 0:
        print("=" * 52)
        print("  推送成功")
        print("=" * 52)
        print("  仓库地址: https://github.com/%s/%s" % (u, REPO))
        print()
        print("  已把令牌从本地配置里清除。")
        print("  请去撤销这个令牌: https://github.com/settings/tokens")
    else:
        print("=" * 52)
        print("  推送失败")
        print("=" * 52)
        low = out.lower()
        if "403" in out or "denied" in low:
            print("  原因可能是：令牌没勾 repo 权限，或已过期")
        elif "not found" in low:
            print("  原因可能是：仓库 %s 还没创建，或用户名写错" % REPO)
        elif "rejected" in low or "non-fast-forward" in low:
            print("  原因可能是：远程仓库已有内容，需要先合并")
        else:
            print("  原始输出：")
            print(out[:800])
        print()
        print("  令牌已从配置中清除，可以重新运行本脚本。")

    print()
    input("按回车退出...")
    return 0 if code == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
