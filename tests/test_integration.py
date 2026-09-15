"""集成验证：构造 App、切换浅色主题（rebuild_ui）、实例化各控件，确认无异常。"""
import os, sys, tkinter as tk, traceback

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import pc_cleaner as pc

fails = []

def ok(cond, msg):
    print(("  ✓ " if cond else "  ✗ ") + msg)
    if not cond:
        fails.append(msg)

print("=" * 60)
print("构造 App 并切换主题")
print("=" * 60)
try:
    app = pc.App()
    app.withdraw()
except Exception as e:
    print("  ✗ App 构造异常:", repr(e))
    traceback.print_exc()
    sys.exit(1)

# 默认应为深色
ok(app.cget("bg") == pc.THEME["bg"], f"默认 root bg={app.cget('bg')} (期望 {pc.THEME['bg']})")

# 切换到浅色（会触发 rebuild_ui）
try:
    pc.set_theme("light")
    app.rebuild_ui()
    ok(app.cget("bg") == pc.THEME["bg"], f"浅色后 root bg={app.cget('bg')} (期望 {pc.THEME['bg']})")
    # 验证顶栏标题 Label 同步为浅色前景
    ok(pc.TEXT == pc.THEME["text"], f"浅色 TEXT={pc.TEXT}")
except Exception as e:
    print("  ✗ 切换主题异常:", repr(e)); traceback.print_exc(); fails.append("theme switch")

# 验证 FluentTile / Pill 已重构为 Frame（无 create_text）
print()
print("=" * 60)
print("控件结构验证（无 create_text DPI 双重绘制）")
print("=" * 60)
try:
    tile = pc.FluentTile(app, icon="🗑", title="清理微信缓存", subtitle="", height=88)
    ok(isinstance(tile, tk.Frame), "FluentTile 为 tk.Frame")
    ok(hasattr(tile, "_lbl_title") and isinstance(tile._lbl_title, tk.Label),
       "FluentTile 含原生 Label(_lbl_title)")
    ok(hasattr(tile, "_cv") and isinstance(tile._cv, tk.Canvas), "FluentTile 含 Canvas 背景层")
    # 动态设置副标题并触发重绘
    tile.set_subtitle("不可用：未检测到目录")
    tile._draw()
    ok(tile._lbl_sub.cget("text") != "", "FluentTile 副标题 Label 可更新")

    pill = pc.Pill(app, "管理员权限已获取", pc.OK_BG, pc.OKC, height=32)
    ok(isinstance(pill, tk.Frame), "Pill 为 tk.Frame")
    ok(hasattr(pill, "_lbl") and isinstance(pill._lbl, tk.Label), "Pill 含原生 Label(_lbl)")
    pill.set("测试状态", "#333333", "#FFFFFF")
    ok("●" in pill._lbl.cget("text"), "Pill 文字含 ● 装饰")
except Exception as e:
    print("  ✗ 控件验证异常:", repr(e)); traceback.print_exc(); fails.append("widgets")

# 钉钉解析验证（沿用上轮结论）
print()
print("=" * 60)
print("钉钉缓存解析")
print("=" * 60)
try:
    dirs = pc.resolve_cache_dirs("dingtalk")
    ok(len(dirs) > 0, f"解析到 {len(dirs)} 个钉钉缓存目录")
    print("   示例:", dirs[:3])
except Exception as e:
    print("  ✗ 钉钉解析异常:", repr(e)); fails.append("dingtalk")

# 清理
try:
    app.destroy()
except Exception:
    pass

print()
if fails:
    print(f"存在 {len(fails)} 项失败：{fails}")
    sys.exit(1)
else:
    print("全部通过 ✓")
