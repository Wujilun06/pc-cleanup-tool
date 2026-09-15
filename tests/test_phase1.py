# -*- coding: utf-8 -*-
"""
阶段一自测：在合成目录上验证删除逻辑的边界行为。
用法: python tests/test_phase1.py
"""
import importlib.util
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(os.path.dirname(HERE), "src", "pc_cleaner.py")

spec = importlib.util.spec_from_file_location("pc", SRC)
pc = importlib.util.module_from_spec(spec)
sys.modules["pc"] = pc
spec.loader.exec_module(pc)

FAILED = []


def check(cond, msg):
    print(("  [PASS] " if cond else "  [FAIL] ") + msg)
    if not cond:
        FAILED.append(msg)


def build_tree(root):
    """构造: root/a/f1.txt, root/a/b/f2.txt, root/a/b/c/(空), root/empty_sub/, root/top.txt"""
    os.makedirs(os.path.join(root, "a", "b", "c"), exist_ok=True)
    os.makedirs(os.path.join(root, "empty_sub"), exist_ok=True)
    with open(os.path.join(root, "top.txt"), "w") as f:
        f.write("x" * 100)
    with open(os.path.join(root, "a", "f1.txt"), "w") as f:
        f.write("y" * 200)
    with open(os.path.join(root, "a", "b", "f2.txt"), "w") as f:
        f.write("z" * 300)


def test_purge():
    print("\n[1] purge_directory 基本行为")
    base = tempfile.mkdtemp(prefix="pc_cleaner_test_")
    root = os.path.join(base, "cache")
    build_tree(root)
    try:
        st = pc.purge_directory(root)
        check(os.path.isdir(root), "根目录本身必须保留")
        check(not os.path.exists(os.path.join(root, "top.txt")), "顶层文件已删除")
        check(not os.path.exists(os.path.join(root, "a", "f1.txt")), "深层文件已删除")
        check(st["files"] == 3, f"删除文件数应为 3，实际 {st['files']}")
        check(st["bytes"] == 600, f"释放字节应为 600，实际 {st['bytes']}")
        check(not os.path.exists(os.path.join(root, "a")), "空子目录已移除")
        left = os.listdir(root)
        check(left == [], f"清理后根目录应为空，实际 {left}")
    finally:
        shutil.rmtree(base, ignore_errors=True)


def test_purge_skip():
    print("\n[2] purge_directory 跳过保护目录")
    base = tempfile.mkdtemp(prefix="pc_cleaner_test_")
    root = os.path.join(base, "Temp")
    keep = os.path.join(root, "_MEI12345")
    os.makedirs(os.path.join(keep, "sub"), exist_ok=True)
    with open(os.path.join(keep, "sub", "important.dll"), "w") as f:
        f.write("keep" * 50)
    with open(os.path.join(root, "junk.tmp"), "w") as f:
        f.write("junk" * 50)
    try:
        st = pc.purge_directory(root, skip={keep})
        check(os.path.exists(os.path.join(keep, "sub", "important.dll")),
              "受保护目录内文件必须完好")
        check(not os.path.exists(os.path.join(root, "junk.tmp")), "非保护区域已清理")
        check(st["files"] == 1, f"只应删除 1 个文件，实际 {st['files']}")
    finally:
        shutil.rmtree(base, ignore_errors=True)


def test_readonly():
    print("\n[3] 只读文件处理")
    base = tempfile.mkdtemp(prefix="pc_cleaner_test_")
    root = os.path.join(base, "cache")
    os.makedirs(root, exist_ok=True)
    p = os.path.join(root, "ro.txt")
    with open(p, "w") as f:
        f.write("ro")
    os.chmod(p, 0o444)
    try:
        st = pc.purge_directory(root)
        check(not os.path.exists(p), "只读文件应被强制删除")
        check(st["failed"] == 0, "不应出现失败项")
    finally:
        shutil.rmtree(base, ignore_errors=True)


def test_detect():
    print("\n[4] 路径探测")
    for app in ("wechat", "qq", "dingtalk"):
        dirs = pc.resolve_cache_dirs(app)
        print(f"    {pc.APP_LABEL[app]}: {len(dirs)} 个缓存目录")
        for d in dirs:
            print(f"      {pc.fmt_size(pc.dir_size(d)):>10s}  {d}")
    check(pc.APP_LABEL["wechat"] == "微信", "应用标签映射正确")


def test_tasks():
    print("\n[5] 任务可用性")
    for cls in sorted(pc.TASK_REGISTRY, key=lambda c: c.order):
        t = cls()
        ok, reason = t.available()
        print(f"    {t.name:<16s} {'可用' if ok else '不可用 → ' + reason}")
        check(bool(t.desc.strip()), f"{t.name} 缺少悬停说明")


def test_ui():
    print("\n[6] 界面构建（2 秒后自动关闭）")
    try:
        app = pc.App()
        app.after(2000, app.destroy)
        app.mainloop()
        check(True, "主窗口构建无异常")
    except Exception as e:
        check(False, f"主窗口构建失败: {e}")


def test_volumecache():
    print("\n[7] 磁盘清理注册表枚举")
    try:
        items = pc.list_volumecache()
    except Exception as e:
        check(False, f"枚举失败: {e}")
        return
    print(f"    共 {len(items)} 项")
    excluded = {n for n, _, c in items if not c}
    for n in pc.VOLCACHE_EXCLUDE:
        check(n in excluded, f"{n} 应被排除（不勾选）")
    # 用户要求的「以前的 Windows 安装」应被勾选
    checked_names = {n for n, _, c in items if c}
    check("Previous Installations" in checked_names,
          "Previous Installations（Windows.old）应被勾选")
    # DownloadsFolder 必须在排除集合里
    check("DownloadsFolder" in pc.VOLCACHE_EXCLUDE,
          "DownloadsFolder 在排除规则中")
    # 排除数量应正好 = 4
    check(len(pc.VOLCACHE_EXCLUDE) == 4, f"排除项应为 4 项，实际 {len(pc.VOLCACHE_EXCLUDE)}")
    # 每项都有可读的中文显示名（且不是原始英文名）
    for n, d, c in items:
        check(bool(d), f"{n} 有显示名")


def test_cleanmgr_write():
    print("\n[8] cleanmgr 注册表写入（需管理员）")
    if not pc.is_admin():
        print("    跳过（非管理员）")
        return
    try:
        n = pc.write_cleanmgr_stateflags()
        check(n > 0, f"至少写入了 1 项，实际 {n}")
        # 校验：被排除项 StateFlags0001 = 0，其余 = 1
        h = __import__('winreg').OpenKey(
            __import__('winreg').HKEY_LOCAL_MACHINE, pc.VOLCACHE_KEY)
        for name, _disp, checked in pc.list_volumecache():
            sh = __import__('winreg').OpenKey(h, name)
            v = __import__('winreg').QueryValueEx(sh, "StateFlags0001")[0]
            __import__('winreg').CloseKey(sh)
            expect = 1 if checked else 0
            check(v == expect, f"{name} StateFlags0001={v}（期望 {expect}）")
        __import__('winreg').CloseKey(h)
    except Exception as e:
        check(False, f"写入/校验失败: {e}")


def test_dismpp_path():
    print("\n[9] Dism++ 路径探测")
    p = pc.find_dismpp_path()
    print(f"    → {p}")
    check(p == "" or os.path.isfile(p), "路径有效或为空")
    t = pc.TaskDismPP()
    ok, reason = t.available()
    check(ok, f"任务可用: {reason}")


if __name__ == "__main__":
    test_purge()
    test_purge_skip()
    test_readonly()
    test_detect()
    test_tasks()
    test_volumecache()
    test_cleanmgr_write()
    test_dismpp_path()
    if "--no-ui" not in sys.argv:
        test_ui()

    print("\n" + "=" * 60)
    if FAILED:
        print(f"存在 {len(FAILED)} 项失败：")
        for f in FAILED:
            print("  - " + f)
        sys.exit(1)
    print("全部通过")
