"""验证三项修复：钉钉缓存规则命中、FluentButton 结构、rebuild_ui root bg。"""
import os, sys, glob, tkinter as tk

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import pc_cleaner as pc

def human(n):
    for u in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f}{u}"
        n /= 1024
    return f"{n:.1f}TB"

# ---------- 1. 钉钉缓存规则命中验证 ----------
print("=" * 64)
print("【1】钉钉缓存规则命中情况（实际会清理什么）")
print("=" * 64)

# 定位钉钉根目录：优先注册表，其次常见路径
roots = []
reg_root = pc.reg_get("dingtalk_root", "")
if reg_root:
    roots.append(reg_root)
appdata = pc.appdata_dir()
candidates = [
    os.path.join(appdata, "DingTalk"),
    os.path.join(appdata, "DingDing", "DingTalk"),
    r"C:\Program Files (x86)\DingTalk",
    r"C:\Program Files\DingTalk",
]
for c in candidates:
    if os.path.isdir(c) and c not in roots:
        roots.append(c)

print("钉钉根目录候选:", roots)
# 新增：打印候选根列表与自动选中的根（命中缓存标记最多的根）
cands = pc._dingtalk_roots()
print("候选根列表:", cands)
found_dirs = pc.resolve_cache_dirs("dingtalk")
sel = os.path.dirname(found_dirs[0]) if found_dirs else "(无)"
print("自动选中根:", sel)
found_root = next((r for r in roots if os.path.isdir(r)), None)
if not found_root:
    print("⚠ 本机未找到钉钉数据目录（可能未安装或未登录），无法实测命中。")
    print("  规则语法检查：逐一 glob 仅验证逻辑正确性。")
    found_root = roots[0] if roots else appdata

total = 0
hit_any = False
for rule in pc.CACHE_RULES["dingtalk"]:
    matched = glob.glob(os.path.join(found_root, rule), recursive=True)
    matched_dirs = [m for m in matched if os.path.isdir(m)]
    if matched_dirs:
        hit_any = True
        sz = sum(
            (sum(os.path.getsize(os.path.join(dp, f), follow_symlinks=False)
                 for dp, _, fs in os.walk(m) for f in fs)
             if os.path.isdir(m) else 0)
            for m in matched_dirs
        ) if False else 0  # 避免过慢：仅计数目录数
        # 简单累计：遍历目录大小
        rule_sz = 0
        for m in matched_dirs:
            for dp, _, fs in os.walk(m):
                for f in fs:
                    fp = os.path.join(dp, f)
                    try:
                        rule_sz += os.path.getsize(fp)
                    except Exception:
                        pass
        total += rule_sz
        names = ", ".join(os.path.basename(m) for m in matched_dirs[:3])
        print(f"  ✓ {rule:<28} -> {len(matched_dirs)} 个目录, ~{human(rule_sz)}  [{names}]")
    else:
        print(f"  · {rule:<28} -> 未命中（本机无此目录，正常）")
print(f"  合计可清理约: {human(total)}  hit_any={hit_any}")

# ---------- 2. FluentButton 结构验证 ----------
print()
print("=" * 64)
print("【2】FluentButton 结构（应含独立 Label，避 DPI 双重渲染）")
print("=" * 64)
root = tk.Tk()
root.withdraw()
for kind in ("standard", "accent", "danger", "subtle"):
    b = pc.FluentButton(root, text="取消（保留打开）", kind=kind, height=44,
                        font_size=10, padx=18)
    has_canvas = isinstance(getattr(b, "_cv", None), tk.Canvas)
    has_label = isinstance(getattr(b, "_lbl", None), tk.Label)
    # Label 必须是独立兄弟控件，而非 Canvas 内嵌的 window
    embedded = False
    if has_canvas:
        try:
            embedded = len(b._cv.find_withtag("all")) > 0 and \
                any(b._cv.type(i) == "window" for i in b._cv.find_withtag("all"))
        except Exception:
            embedded = "?"
    print(f"  {kind:<8} Frame={isinstance(b, tk.Frame)} Canvas={has_canvas} "
          f"Label={has_label} Canvas_embedded_window={embedded}")
    b._draw()
    print(f"           label_text={b._lbl.cget('text')!r} bg={b._lbl.cget('bg')} fg={b._lbl.cget('fg')}")
root.destroy()

# ---------- 3. rebuild_ui root bg 同步验证 ----------
print()
print("=" * 64)
print("【3】rebuild_ui 是否重设 root bg（浅色切换关键）")
print("=" * 64)
import inspect
src = inspect.getsource(pc.App.rebuild_ui)
print("  rebuild_ui 首行 self.configure(bg=BG):",
      'self.configure(bg=BG)' in src.split('\n', 2)[1])

print()
print("验证完成。")
