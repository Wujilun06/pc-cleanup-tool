# -*- coding: utf-8 -*-
"""
电脑清理工具 (PC Cleaner) —— 单文件图形界面清理工具
================================================================
阶段一：框架 + 系统缓存清理 + 微信/QQ/钉钉缓存清理
阶段二（待接入）：系统磁盘清理(cleanmgr 静默) / Dism++ 空间回收(UIA)

设计约束：
  1. 单一 .py 源文件 -> PyInstaller --onefile 打包为单个 .exe
  2. 运行时不落盘任何文件：配置写入注册表 HKCU\\Software\\PCCleaner
  3. 退出时清理 PyInstaller 自身解压残留 (_MEIxxxx)
  4. 模块化：所有功能以 Task 子类实现，注册到 TASK_REGISTRY 即可被 UI 自动识别
"""

from __future__ import annotations

import atexit
import ctypes
import os
import queue
import shutil
import stat
import string
import subprocess
import sys
import threading
import time
import traceback
import winreg
from datetime import datetime
from glob import glob

import math
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, font as tkfont

# --------------------------------------------------------------------------- #
# 0. 全局常量
# --------------------------------------------------------------------------- #

APP_NAME = "电脑清理工具"
APP_VER = "0.3.0"
REG_KEY = r"Software\PCCleaner"

# --------------------------------------------------------------------------- #
# 0.1 Windows 11 设计令牌（Fluent Design / 深色 + 浅色 双主题）
#     配色参考 Win11 设置：深色 Mica #1A1A1A / 卡片 #2C2C2C；浅色 Mica #F3F3F3 / 卡片 #FFFFFF
# --------------------------------------------------------------------------- #
THEMES = {
    "dark": {
        "bg": "#1A1A1A", "card": "#2C2C2C", "card_hover": "#333333",
        "border": "#3F3F3F", "border_strong": "#5A5A5A",
        "text": "#FFFFFF", "subtext": "#C5C5C5", "muted": "#8A8A8A",
        "accent": "#4CC2FF", "accent_hover": "#7CD4FF", "accent_press": "#3CA6E0",
        "accent_soft": "#1B2A3A", "accent_text": "#4CC2FF",
        "btn_face": "#3B3B3B", "btn_hover": "#454545", "btn_press": "#525252",
        "btn_border": "#555555",
        "ok": "#6CCB5F", "warn": "#FCE100", "err": "#FF99A4",
        "ok_bg": "#1E3320", "warn_bg": "#3A2F00", "err_bg": "#3A1F20",
        "tile_disabled": "#262626", "tile_disabled_sub": "#5A5A5A",
        "btn_disabled": "#2F2F2F", "scroll_thumb": "#C6C6C6",
    },
    "light": {
        # 浅色主题调色（v0.2.0 视觉修复）：
        #   bg 加深 → 让白色磁贴/卡片在背景上有明显投影感；
        #   border 加深 → 描边可见性提升（之前 #E5E5E5 在 Windows 系统主题下几乎看不见）
        "bg": "#E8E8E8", "card": "#FFFFFF", "card_hover": "#FAFAFA",
        "border": "#C8C8C8", "border_strong": "#9E9E9E",
        "text": "#1B1B1B", "subtext": "#616161", "muted": "#9E9E9E",
        "accent": "#0078D4", "accent_hover": "#1A86D9", "accent_press": "#005FB8",
        "accent_soft": "#E1EFFA", "accent_text": "#005FB8",
        # 标准按钮加深描边与轻背景，让底栏「设置/退出」按钮脱离卡片视觉
        "btn_face": "#F4F4F4", "btn_hover": "#E5E5E5", "btn_press": "#DADADA",
        "btn_border": "#A8A8A8",
        "ok": "#0F7B0F", "warn": "#9D5D00", "err": "#C42B1C",
        "ok_bg": "#DFF6DD", "warn_bg": "#FDF6E3", "err_bg": "#FDE7E9",
        "tile_disabled": "#EEEEEE", "tile_disabled_sub": "#A0A0A0",
        "btn_disabled": "#EEEEEE", "scroll_thumb": "#9E9E9E",
    },
}

# 当前生效主题（从注册表读出或默认深色）
THEME: dict = THEMES["dark"].copy()
_THEME_NAME: str = "dark"


# 模块级「活引用」：由 _sync_theme_globals() 同步指向 THEME 中对应键，
# 以便既有代码继续使用 BG / CARD / ACCENT 等短名。每次 set_theme() 都会重新同步。
def _sync_theme_globals() -> None:
    global BG, CARD, CARD_HOVER, BORDER, BORDER_STR, TEXT, SUBTEXT, MUTED
    global ACCENT, ACCENT_HOVER, ACCENT_PRESS, ACCENT_SOFT, ACCENT_TEXT
    global BTN_FACE, BTN_HOVER, BTN_PRESS, BTN_BORDER
    global OKC, WARNC, ERRC, OK_BG, WARN_BG, ERR_BG
    global TILE_DISABLED, TILE_DISABLED_SUB, BTN_DISABLED, SCROLL_THUMB
    BG, CARD, CARD_HOVER = THEME["bg"], THEME["card"], THEME["card_hover"]
    BORDER, BORDER_STR = THEME["border"], THEME["border_strong"]
    TEXT, SUBTEXT, MUTED = THEME["text"], THEME["subtext"], THEME["muted"]
    ACCENT, ACCENT_HOVER, ACCENT_PRESS = THEME["accent"], THEME["accent_hover"], THEME["accent_press"]
    ACCENT_SOFT, ACCENT_TEXT = THEME["accent_soft"], THEME["accent_text"]
    BTN_FACE, BTN_HOVER = THEME["btn_face"], THEME["btn_hover"]
    BTN_PRESS, BTN_BORDER = THEME["btn_press"], THEME["btn_border"]
    OKC, WARNC, ERRC = THEME["ok"], THEME["warn"], THEME["err"]
    OK_BG, WARN_BG, ERR_BG = THEME["ok_bg"], THEME["warn_bg"], THEME["err_bg"]
    TILE_DISABLED = THEME["tile_disabled"]
    TILE_DISABLED_SUB = THEME["tile_disabled_sub"]
    BTN_DISABLED = THEME["btn_disabled"]
    SCROLL_THUMB = THEME["scroll_thumb"]


_sync_theme_globals()   # 首次同步：让短名指向深色（默认）


def set_theme(name: str) -> None:
    """仅切换主题色板并同步短名引用，不重建 UI（由调用方决定）。"""
    global _THEME_NAME
    if name not in THEMES or name == _THEME_NAME:
        return
    THEME.clear()
    THEME.update(THEMES[name])
    _THEME_NAME = name
    _sync_theme_globals()


def apply_theme(name: str) -> None:
    """切换主题 + 重建主窗口 UI（保留任务实例与内存日志）。"""
    global _APP_REF
    set_theme(name)
    app = _APP_REF[0] if _APP_REF else None
    if app is not None and hasattr(app, "rebuild_ui"):
        try:
            app.rebuild_ui()
        except Exception:
            pass


# 主窗口实例的弱引用（用于从模块级函数 apply_theme 找到它并触发 UI 重建）
_APP_REF: list = []


# 圆角：窗口 8px，控件（按钮/输入框）4px，徽章胶囊取半高
R_WIN = 8
R_CTL = 4

# 字体：用户要求中文统一使用微软雅黑以保证 CJK 可读性（该加粗处仍加粗）
FONT_CANDIDATES = ["Microsoft YaHei UI", "Microsoft YaHei", "SimSun"]
FONT = "Microsoft YaHei UI"   # 默认值，启动时由 pick_font() 依实际可用字体覆盖

# --------------------------------------------------------------------------- #
# 1. 日志系统（内存环形缓冲 + 观察者）
# --------------------------------------------------------------------------- #


class LogBus:
    """线程安全的内存日志；可注册 sink 供 UI 实时渲染。"""

    def __init__(self, max_lines: int = 5000):
        self._lines: list[str] = []
        self._max = max_lines
        self._lock = threading.Lock()
        self._sinks: list = []

    def add_sink(self, fn):
        self._sinks.append(fn)

    def log(self, level: str, msg: str):
        line = f"[{datetime.now():%H:%M:%S}] [{level:<5}] {msg}"
        with self._lock:
            self._lines.append(line)
            if len(self._lines) > self._max:
                del self._lines[: len(self._lines) - self._max]
        for s in list(self._sinks):
            try:
                s(line, level)
            except Exception:
                pass

    def info(self, m): self.log("INFO", m)
    def ok(self, m):   self.log("OK", m)
    def warn(self, m): self.log("WARN", m)
    def error(self, m):self.log("ERROR", m)

    def clear(self):
        with self._lock:
            self._lines.clear()

    def text(self) -> str:
        with self._lock:
            return "\n".join(self._lines)


LOG = LogBus()

DEFAULT_HELP = "将鼠标悬停在上方任意功能卡片上，这里会显示该功能的详细说明。"


# --------------------------------------------------------------------------- #
# 2. 通用工具
# --------------------------------------------------------------------------- #

def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def elevate() -> bool:
    """以 runas 重启自身；成功返回 True（调用方应立即退出当前进程）。"""
    exe = sys.executable if getattr(sys, "frozen", False) else os.path.abspath(__file__)
    params = " ".join(f'"{a}"' for a in sys.argv[1:]) + " --elevated"
    rc = ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, params, None, 1)
    return rc > 32


def known_folder(csidl: int) -> str:
    """通过 Shell API 获取系统目录，避免依赖环境变量（某些宿主环境下 APPDATA 缺失）。"""
    buf = ctypes.create_unicode_buffer(1024)
    try:
        if ctypes.windll.shell32.SHGetFolderPathW(None, csidl, None, 0, buf) == 0:
            return buf.value
    except Exception:
        pass
    return ""


CSIDL_APPDATA = 26
CSIDL_LOCAL_APPDATA = 28
CSIDL_PERSONAL = 5


def appdata_dir() -> str:
    return os.environ.get("APPDATA") or known_folder(CSIDL_APPDATA) or \
        os.path.join(os.path.expanduser("~"), "AppData", "Roaming")


def localappdata_dir() -> str:
    return os.environ.get("LOCALAPPDATA") or known_folder(CSIDL_LOCAL_APPDATA) or \
        os.path.join(os.path.expanduser("~"), "AppData", "Local")


def documents_dir() -> str:
    return known_folder(CSIDL_PERSONAL) or os.path.join(os.path.expanduser("~"), "Documents")


def temp_dir() -> str:
    return os.environ.get("TEMP") or os.path.join(localappdata_dir(), "Temp")


def long_path(p: str) -> str:
    """转换为 Windows 扩展长度路径，规避 260 字符限制。"""
    p = os.path.abspath(p)
    if p.startswith("\\\\?\\"):
        return p
    if p.startswith("\\\\"):
        return "\\\\?\\UNC\\" + p[2:]
    return "\\\\?\\" + p


def fs_path(p: str) -> str:
    """
    仅在路径超长时才启用 \\\\?\\ 扩展前缀。
    原因：部分环境下扩展路径会导致删除/回收站接口失败（ERROR_BAD_NETPATH），
    而绝大多数目录并不会触及 260 字符限制。
    """
    p = os.path.abspath(p)
    return long_path(p) if len(p) > 240 else p


def short(p: str) -> str:
    return p.replace("\\\\?\\", "").replace("\\\\?\\UNC\\", "\\\\")


def fmt_size(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024.0:
            return f"{n:.1f} {unit}" if unit != "B" else f"{int(n)} B"
        n /= 1024.0
    return f"{n:.1f} PB"


def dir_size(path: str) -> int:
    total = 0
    lp = fs_path(path)
    for dirpath, _dirs, files in os.walk(lp, onerror=lambda e: None):
        for f in files:
            fp = os.path.join(dirpath, f)
            try:
                total += os.path.getsize(long_path(fp) if len(fp) > 240 else fp)
            except OSError:
                pass
    return total


def purge_directory(root: str, skip: set | None = None) -> dict:
    """
    清空目录内容：删除所有文件，并自底向上尽力删除空子目录。
    ★ 保留 root 目录本身（用户明确要求，防止软件因目录缺失报错）。
    skip 中的路径（及其子路径）完全跳过。
    """
    st = {"files": 0, "dirs": 0, "bytes": 0, "failed": 0}
    lp = fs_path(root)
    skip_lp = {os.path.abspath(s) for s in (skip or set())}

    def skip_dir(d: str) -> bool:
        n = os.path.abspath(short(d)).lower()
        for s in skip_lp:
            sl = s.lower()
            if n == sl or n.startswith(sl + os.sep):
                return True
        return False

    for dirpath, _dirnames, filenames in os.walk(lp, topdown=False, onerror=lambda e: None):
        if skip_dir(dirpath):
            continue
        for fn in filenames:
            fp = os.path.join(dirpath, fn)
            target = long_path(fp) if len(fp) > 240 else fp
            try:
                sz = os.path.getsize(target)
                try:
                    os.chmod(target, stat.S_IWRITE)
                except Exception:
                    pass
                os.remove(target)
                st["files"] += 1
                st["bytes"] += sz
            except Exception as e:
                st["failed"] += 1
                LOG.warn(f"跳过（占用/无权限）: {short(fp)}  [{type(e).__name__}]")
        if skip_dir(dirpath) or os.path.abspath(short(dirpath)).lower() == \
                os.path.abspath(root).lower():
            continue
        dtarget = long_path(dirpath) if len(dirpath) > 240 else dirpath
        try:
            os.rmdir(dtarget)
            st["dirs"] += 1
        except OSError:
            pass  # 非空或有占用，保留即可
    return st


# 主题兼容别名：旧代码里的 PRIMARY / PRIMARY_D 统一指向 Win11 强调色
PRIMARY = ACCENT
PRIMARY_D = ACCENT_PRESS


def set_dpi_aware():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)   # PER_MONITOR_DPI_AWARE
    except Exception:
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass


# --------------------------------------------------------------------------- #
# 2.1 字体与圆角几何
# --------------------------------------------------------------------------- #

def pick_font() -> str:
    """探测系统可用字体，返回最贴近 Win11 的 UI 字体名。"""
    try:
        fams = set(tkfont.families())
    except Exception:
        return FONT_CANDIDATES[-1]
    for f in FONT_CANDIDATES:
        if f in fams:
            return f
    return FONT_CANDIDATES[-1]


def init_theme():
    """在 Tk 根窗口创建后调用：确定实际字体。"""
    global FONT
    FONT = pick_font()
    return FONT


def round_rect_points(x1: float, y1: float, x2: float, y2: float,
                      r: float, steps: int = 6) -> list[float]:
    """生成精确圆角矩形的顶点序列（供 Canvas.create_polygon 使用）。"""
    r = max(0.0, min(r, (x2 - x1) / 2.0, (y2 - y1) / 2.0))
    pts: list[float] = []

    def arc(cx, cy, a0, a1):
        for i in range(steps + 1):
            a = math.radians(a0 + (a1 - a0) * i / steps)
            pts.extend((cx + r * math.cos(a), cy + r * math.sin(a)))

    arc(x2 - r, y1 + r, -90, 0)     # 右上
    arc(x2 - r, y2 - r, 0, 90)      # 右下
    arc(x1 + r, y2 - r, 90, 180)    # 左下
    arc(x1 + r, y1 + r, 180, 270)   # 左上
    return pts


def wrap_lines(text: str, tkfont_obj, max_px: int) -> list[str]:
    """
    按像素宽度模拟自动换行（中英混排：逐字符累加，避免按空格切分导致中文不换行）。
    返回的列表长度即渲染所需行数 —— 用于运行时精确计算说明区高度。
    """
    out: list[str] = []
    for para in text.split("\n"):
        if not para:
            out.append("")
            continue
        cur, w = "", 0.0
        for ch in para:
            cw = tkfont_obj.measure(ch)
            if w + cw > max_px and cur:
                out.append(cur)
                cur, w = ch, cw
            else:
                cur += ch
                w += cw
        out.append(cur)
    return out


# --------------------------------------------------------------------------- #
# 3. 配置存储（注册表，不落盘）
# --------------------------------------------------------------------------- #

def reg_get(name: str, default: str = "") -> str:
    try:
        h = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY)
        v, _ = winreg.QueryValueEx(h, name)
        winreg.CloseKey(h)
        return v
    except OSError:
        return default


def reg_set(name: str, value: str):
    try:
        h = winreg.CreateKey(winreg.HKEY_CURRENT_USER, REG_KEY)
        winreg.SetValueEx(h, name, 0, winreg.REG_SZ, value)
        winreg.CloseKey(h)
    except OSError as e:
        LOG.warn(f"配置写入失败: {e}")


# --------------------------------------------------------------------------- #
# 4. 路径自动探测
# --------------------------------------------------------------------------- #

def _drives() -> list[str]:
    return [f"{c}:\\" for c in string.ascii_uppercase if os.path.exists(f"{c}:\\")]


def detect_root(app: str) -> str:
    """
    自动定位软件数据根目录。
    优先级：用户预填(注册表) > 常见位置 > 各盘符 <盘>:\\<用户名>\\Documents\\<子目录>
    """
    custom = reg_get(f"{app}_root", "")
    if custom and os.path.isdir(custom):
        return custom

    user = os.environ.get("USERNAME", "")
    if app == "wechat":
        subs = ["xwechat_files", "WeChat Files"]
    elif app == "qq":
        subs = ["Tencent Files"]
    else:
        return ""

    candidates: list[str] = []
    docs = documents_dir()
    for s in subs:
        candidates.append(os.path.join(docs, s))
    for d in _drives():
        for s in subs:
            candidates.append(os.path.join(d, user, "Documents", s))
            candidates.append(os.path.join(d, s))

    for c in candidates:
        if os.path.isdir(c):
            return c
    return ""


# 各软件「缓存目录」匹配规则（glob，recursive）
# ★ 钉钉规则关键点（v0.2.x 修复）：
#   钉钉的「缓存大头」不在 Temp/log 这些小目录里，而在：
#     · plugins/                插件缓存（~300MB，下次按需重新加载）
#     · DingpanSyncUpgrade/     钉盘升级包（~100MB，下次升级重新下载）
#     · adacb*/EAppFiles/      E应用/小程序文件（~200MB，重新打开会重新下载）
#     · adacb*/resource_cache/ 资源缓存（~20MB）
#     · 其余 adacb*/xxx        各种业务缓存（Sync_v2/UserStorage/GrayStorage 等）
#   明确 NOT 清理：
#     · adacb*/DBFiles          聊天记录数据库（绝对不能删）
#     · adacb*/AvatarFiles      用户/群头像缓存（可选，但删除后下次重新下载慢）
#   备注：glob 的 * 不会跨路径分隔符，故 "adacb*/EAppFiles" 恰好匹配
#         "<root>/adacb<hash>_v3/EAppFiles" 这种"版本化资源池"下的子目录。
CACHE_RULES = {
    "wechat": ["**/cache", "**/temp", "**/apm_record",
               "**/FileStorage/Cache", "**/FileStorage/Temp"],
    "qq": ["**/nt_temp", "**/nt_data/Log", "**/nt_data/WeatherBgCache"],
    "dingtalk": [
        # 原有小目录
        "Temp", "log", "holmeslogs", "recordLog", "updaterlogs",
        "image_res_cache", "image_translate_cache",
        # 钉钉大头缓存（实测这才是真正占空间的目录）
        "plugins",              # 插件缓存（~300MB，按需重建）
        "DingpanSyncUpgrade",   # 钉盘同步升级包（~100MB，下次升级重新下载）
        # 版本化资源池 adacb<hash>_v3/ 下的子项（占大头但不损聊天数据）
        "adacb*/EAppFiles",        # E应用/小程序（~200MB，重新打开重新下载）
        "adacb*/resource_cache",   # 资源缓存（~20MB）
        "adacb*/Sync_v2",          # 同步缓存
        "adacb*/CommonStorage",    # 通用存储
        "adacb*/UserStorage",      # 用户存储
        "adacb*/dtnest_db",        # nest 数据库缓存
        "adacb*/GrayStorage",      # 灰度存储
        "adacb*/enterprise",       # 企业信息缓存
        # 明确不放入此列表：adacb*/DBFiles（聊天记录）、adacb*/AvatarFiles（头像）
    ],
}

APP_LABEL = {"wechat": "微信", "qq": "QQ", "dingtalk": "钉钉"}


def _dingtalk_roots() -> list[str]:
    """钉钉数据根目录候选（仅限 AppData 数据目录，绝不含 Program Files 安装目录）。

    ★ 安全约束：Program Files\\DingTalk\\plugins 是程序自身的「已安装」插件，
      删除会直接损坏钉钉；因此候选只收 AppData 下的数据目录，那里的 plugins /
      DingpanSyncUpgrade / adacb* 才是可安全清理的缓存。
    """
    custom = reg_get("dingtalk_root", "")
    ad = appdata_dir()
    ld = localappdata_dir()
    cands = []
    if custom:
        cands.append(custom)
    cands += [
        os.path.join(ad, "DingTalk"),
        os.path.join(ad, "DingDing", "DingTalk"),
        os.path.join(ld, "DingTalk"),
        os.path.join(ld, "DingDing", "DingTalk"),
    ]
    return cands


def resolve_cache_dirs(app: str) -> list[str]:
    """返回该软件实际存在的缓存目录列表。

    ★ 钉钉：在多个 AppData 候选根中，自动挑选「命中缓存标记最多」的那个，
      彻底解决「目录找错导致什么都没清理」的问题（用户机型数据目录位置不一）。
    """
    if app == "dingtalk":
        best_root, best_score = "", -1
        for c in _dingtalk_roots():
            if not os.path.isdir(c):
                continue
            score = sum(1 for rule in CACHE_RULES["dingtalk"]
                        if glob(os.path.join(c, rule), recursive=True))
            if score > best_score:
                best_score, best_root = score, c
        root = best_root
    else:
        root = detect_root(app)
    if not root or not os.path.isdir(root):
        return []

    found, seen = [], set()
    for rule in CACHE_RULES[app]:
        for m in glob(os.path.join(root, rule), recursive=True):
            if os.path.isdir(m):
                real = os.path.abspath(m)
                if real.lower() not in seen:
                    seen.add(real.lower())
                    found.append(real)
    found.sort()
    return found


# --------------------------------------------------------------------------- #
# 5. 任务基类与注册表
# --------------------------------------------------------------------------- #

class Cancelled(Exception):
    pass


class Task:
    """所有清理功能的基类。子类只需实现 describe() 与 run()。"""

    key = ""
    name = ""
    icon = ""
    desc = ""            # 鼠标悬停时显示在界面下方
    order = 100

    def available(self) -> tuple[bool, str]:
        return True, ""

    def describe(self) -> tuple[str, str]:
        """返回 (确认弹窗标题, 详情文本)。执行前调用。"""
        return f"确认执行「{self.name}」？", self.desc

    def run(self):
        raise NotImplementedError


TASK_REGISTRY: list[type[Task]] = []


def register(cls):
    TASK_REGISTRY.append(cls)
    return cls


# --------------------------------------------------------------------------- #
# 6. 任务实现（阶段一）
# --------------------------------------------------------------------------- #

@register
class TaskClearTemp(Task):
    key = "temp"
    name = "清理系统缓存"
    icon = "🗑"
    order = 10
    desc = ("清理当前用户的临时文件夹 %TEMP%（即 C:\\Users\\<用户名>\\AppData\\Local\\Temp）\n"
            "删除其中所有文件与可删除的空目录，保留 Temp 目录本身\n"
            "被程序占用的文件会自动跳过并在日志中列出，不会影响正在运行的软件")

    def describe(self):
        temp = temp_dir()
        return (f"确认执行「{self.name}」？",
                f"目标目录：\n  {temp}\n\n"
                f"将删除该目录下所有文件（保留目录本身）。\n"
                f"被占用的文件会自动跳过。")

    def run(self):
        temp = temp_dir()
        if not temp or not os.path.isdir(temp):
            raise FileNotFoundError(f"未找到临时目录: {temp}")

        # 排除本程序自身的解压目录（PyInstaller onefile）
        skip = set()
        meipass = getattr(sys, "_MEIPASS", "")
        if meipass:
            skip.add(meipass)
        for d in glob(os.path.join(temp, "_MEI*")):
            skip.add(d)

        LOG.info(f"开始清理临时目录: {temp}")
        if skip:
            LOG.info(f"已排除 {len(skip)} 个受保护目录（本程序运行时目录）")

        before = dir_size(temp)
        LOG.info(f"清理前占用: {fmt_size(before)}")
        st = purge_directory(temp, skip=skip)
        LOG.ok(f"完成：删除文件 {st['files']} 个、移除空目录 {st['dirs']} 个，"
               f"释放 {fmt_size(st['bytes'])}"
               + (f"，跳过 {st['failed']} 个" if st["failed"] else ""))
        if st["failed"]:
            LOG.warn(f"有 {st['failed']} 个文件被占用未能删除（属正常现象，详见上方 WARN 行）")


class IMCacheTask(Task):
    """微信 / QQ / 钉钉 缓存清理的公共实现。"""

    app = ""
    order = 20

    def available(self):
        dirs = resolve_cache_dirs(self.app)
        if not dirs:
            return False, f"未检测到{APP_LABEL[self.app]}数据目录，请点击「路径设置」手动指定"
        return True, ""

    def describe(self):
        dirs = resolve_cache_dirs(self.app)
        if not dirs:
            raise FileNotFoundError(f"未检测到{APP_LABEL[self.app]}数据目录")
        total = 0
        lines = []
        for d in dirs:
            sz = dir_size(d)
            total += sz
            lines.append(f"  • {d}    （{fmt_size(sz)}）")
        body = (f"将清空以下 {len(dirs)} 个缓存目录中的内容（保留目录本身）：\n\n"
                + "\n".join(lines)
                + f"\n\n合计约 {fmt_size(total)}\n\n"
                  f"⚠ 不会触碰聊天记录数据库与已保存的收发文件。")
        return f"确认清理{APP_LABEL[self.app]}缓存？", body

    def run(self):
        dirs = resolve_cache_dirs(self.app)
        LOG.info(f"开始清理{APP_LABEL[self.app]}缓存，共 {len(dirs)} 个目录")
        tf = td = tb = tfail = 0
        for d in dirs:
            LOG.info(f"清理: {d}")
            st = purge_directory(d)
            tf += st["files"]; td += st["dirs"]; tb += st["bytes"]; tfail += st["failed"]
            LOG.ok(f"  → 删除 {st['files']} 个文件，释放 {fmt_size(st['bytes'])}")
        LOG.ok(f"{APP_LABEL[self.app]}缓存清理完成：文件 {tf} 个、空目录 {td} 个、"
               f"释放 {fmt_size(tb)}" + (f"，跳过 {tfail} 个" if tfail else ""))
        if tfail:
            LOG.warn(f"提示：{tfail} 个文件被占用（软件正在运行时常见），可关闭{APP_LABEL[self.app]}后重试")


@register
class TaskWeChat(IMCacheTask):
    key = "wechat"
    app = "wechat"
    name = "清理微信缓存"
    icon = "💬"
    order = 20
    desc = ("自动定位微信数据目录（新版 xwechat_files / 旧版 WeChat Files）\n"
            "清理其中的 cache、temp、apm_record、FileStorage\\Cache、FileStorage\\Temp等\n"
            "聊天记录与已保存文件不受影响")


@register
class TaskQQ(IMCacheTask):
    key = "qq"
    app = "qq"
    name = "清理 QQ 缓存"
    icon = "🐧"
    order = 30
    desc = ("自动定位 QQ 数据目录（Tencent Files）\n"
            "清理其中的 nt_temp、nt_data\\Log、nt_data\\WeatherBgCache等\n"
            "聊天记录与已保存文件不受影响")


@register
class TaskDingTalk(IMCacheTask):
    key = "dingtalk"
    app = "dingtalk"
    name = "清理钉钉缓存"
    icon = "📌"
    order = 40
    desc = ("自动定位钉钉数据目录（%APPDATA%\\DingTalk）\n"
            "清理其中的大头缓存：plugins（插件缓存）、DingpanSyncUpgrade（升级包）、\n"
            "adacb*\\EAppFiles（E应用）、adacb*\\resource_cache（资源）等\n"
            "以及小目录：Temp / log / holmeslogs / recordLog / updaterlogs /\n"
            "image_res_cache / image_translate_cache\n"
            "★ 聊天记录数据库（adacb*\\DBFiles）与头像缓存不会被清理")


# --------------------------------------------------------------------------- #
# 7. 阶段二任务实现
# --------------------------------------------------------------------------- #

# 磁盘清理（cleanmgr）——注册表预置勾选 + sagerun 静默
VOLCACHE_KEY = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\VolumeCaches"
VOLCACHE_EXCLUDE = {
    "D3D Shader Cache":     "DirectX 着色器缓存（按你的要求保留）",
    "Recycle Bin":          "回收站（按你的要求保留）",
    "Temporary Files":      "临时文件（按你的要求保留）",
    "DownloadsFolder":      "下载文件夹（按你的要求保留，不会删除）",
}
DISPLAY_CN = {
    "Active Setup Temp Folders":         "Active Setup 临时文件夹",
    "BranchCache":                       "BranchCache 缓存",
    "Content Indexer Cleaner":           "内容索引器清理",
    "D3D Shader Cache":                  "DirectX 着色器缓存",
    "Delivery Optimization Files":       "传递优化文件",
    "Device Driver Packages":            "设备驱动程序包",
    "Diagnostic Data Viewer database files": "诊断数据查看器数据库",
    "Downloaded Program Files":          "已下载的程序文件",
    "DownloadsFolder":                   "下载文件夹",
    "Feedback Hub Archive log files":    "反馈中心归档日志",
    "Internet Cache Files":              "Internet 临时文件",
    "Language Pack":                     "语言包",
    "Offline Pages Files":               "脱机网页文件",
    "Old ChkDsk Files":                  "旧的磁盘检查文件",
    "Previous Installations":            "以前的 Windows 安装（Windows.old）",
    "Recycle Bin":                       "回收站",
    "RetailDemo Offline Content":        "零售演示离线内容",
    "Setup Log Files":                   "安装日志文件",
    "System error memory dump files":    "系统错误内存转储",
    "System error minidump files":       "系统错误小型转储",
    "Temporary Files":                   "临时文件",
    "Temporary Setup Files":             "安装临时文件",
    "Temporary Sync Files":              "同步临时文件",
    "Thumbnail Cache":                   "缩略图缓存",
    "Update Cleanup":                    "Windows 更新清理（耗时较长）",
    "Upgrade Discarded Files":           "升级丢弃文件",
    "User file versions":                "用户文件版本",
    "Windows Defender":                  "Windows Defender 扫描数据",
    "Windows Error Reporting Files":     "Windows 错误报告文件",
    "Windows ESD installation files":    "Windows ESD 安装文件",
    "Windows Reset Log Files":           "Windows 重置日志",
    "Windows Upgrade Log Files":         "Windows 升级日志",
}


def cleanmgr_exe() -> str:
    return os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "cleanmgr.exe")


def list_volumecache() -> list[tuple[str, str, bool]]:
    """枚举磁盘清理项 → [(注册表子项名, 显示名, 是否勾选), ...]"""
    items: list[tuple[str, str, bool]] = []
    try:
        h = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, VOLCACHE_KEY)
    except OSError as e:
        raise RuntimeError(f"无法打开注册表 {VOLCACHE_KEY}: {e}")
    i = 0
    while True:
        try:
            name = winreg.EnumKey(h, i)
        except OSError:
            break
        i += 1
        display = DISPLAY_CN.get(name, name)
        items.append((name, display, name not in VOLCACHE_EXCLUDE))
    winreg.CloseKey(h)
    items.sort(key=lambda t: (not t[2], t[1]))
    return items


def write_cleanmgr_stateflags():
    """为每个 VolumeCaches 子项写入 StateFlags0001：勾选=1 / 不勾选=0。"""
    try:
        parent = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE, VOLCACHE_KEY,
            0, winreg.KEY_READ | winreg.KEY_WRITE)
    except OSError as e:
        raise RuntimeError(f"无法打开注册表（需管理员）: {e}")
    written = 0
    try:
        for name, _disp, checked in list_volumecache():
            try:
                sub = winreg.OpenKey(parent, name, 0, winreg.KEY_SET_VALUE)
            except OSError:
                continue
            try:
                winreg.SetValueEx(sub, "StateFlags0001", 0, winreg.REG_DWORD,
                                  1 if checked else 0)
                written += 1
            finally:
                winreg.CloseKey(sub)
    finally:
        winreg.CloseKey(parent)
    return written


@register
class TaskDiskCleanup(Task):
    key = "cleanmgr"
    name = "系统磁盘清理"
    icon = "💽"
    order = 50
    desc = ("调用 Windows 磁盘清理清理 C盘\n"
            "不勾选（保留）：DirectX 着色器缓存、回收站、临时文件、下载文件夹\n"
            "⚠ 扫描与清理耗时可能较长，期间请勿取消或中止")

    def available(self):
        return (os.path.isfile(cleanmgr_exe()),
                "可用" if os.path.isfile(cleanmgr_exe()) else f"未找到 {cleanmgr_exe()}")

    def describe(self):
        items = list_volumecache()
        checked = [x for x in items if x[2]]
        unchecked = [x for x in items if not x[2]]
        lines = ["将通过注册表预置勾选 + cleanmgr /sagerun:1 静默执行 C 盘磁盘清理。\n"]
        lines.append(f"将清理 {len(checked)} 项：")
        for _n, d, c in checked:
            lines.append(f"  ☑ {d}")
        if unchecked:
            lines.append(f"\n已排除 {len(unchecked)} 项（保留）：")
            for _n, d, _c in unchecked:
                lines.append(f"  ☐ {d}")
        lines.append("\n⚠ 提示：")
        lines.append("  · 「Windows 更新清理」可能耗时 10 分钟以上")
        lines.append("  · 「以前的 Windows 安装」即 Windows.old，删除后无法回退到旧系统")
        lines.append("  · 清理过程中 cleanmgr 窗口不显示，但磁盘 IO 较高属正常现象")
        return "确认执行系统磁盘清理？", "\n".join(lines)

    def run(self):
        exe = cleanmgr_exe()
        if not os.path.isfile(exe):
            raise FileNotFoundError(f"未找到 {exe}")
        LOG.info(f"准备注册表: 写入 VolumeCaches 勾选状态（{len(VOLCACHE_EXCLUDE)} 项排除）")
        n = write_cleanmgr_stateflags()
        LOG.info(f"  → 已写入 {n} 个 VolumeCaches 子项的 StateFlags0001")
        excluded = ", ".join(VOLCACHE_EXCLUDE.values())
        LOG.info(f"  → 保留: {excluded}")
        LOG.info(f"启动 cleanmgr /sagerun:1 /D C （静默模式）")
        # cleanmgr 自身进程需要 admin 权限 — 我们当前进程已是 admin
        proc = subprocess.Popen([exe, "/sagerun:1", "/D", "C"], shell=False,
                                creationflags=0x08000000)  # CREATE_NO_WINDOW
        # 等待完成；cleanmgr 可能耗时较长，无超时
        ret = proc.wait()
        if ret != 0:
            raise RuntimeError(f"cleanmgr 异常退出（返回码 {ret}），可能权限不足或磁盘被占用")
        LOG.ok("cleanmgr 静默清理已完成")


# Dism++ 空间回收 —— 启动程序 + 置顶引导窗（因 DuiLib 自绘，UIA 无法定位内部控件）
# 优先 x64：实测 x86 在 64 位系统上有概率立即退出（返回码 1），x64 稳定
DISMPP_DEFAULT_PATHS = [
    r"D:\Applications\图吧工具箱\图吧工具箱202507\tools\其他工具\Dism++\Dism++x64.exe",
    r"D:\Applications\图吧工具箱\图吧工具箱202507\tools\其他工具\Dism++\Dism++x86.exe",
]


def _dismpp_window_exists() -> bool:
    """检测系统是否已存在 Dism++ 主窗口（用于判断启动是否成功）。"""
    try:
        import ctypes
        found = []

        @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)
        def cb(h, _):
            if ctypes.windll.user32.IsWindowVisible(h):
                length = ctypes.windll.user32.GetWindowTextLengthW(h)
                if length:
                    buf = ctypes.create_unicode_buffer(length + 1)
                    ctypes.windll.user32.GetWindowTextW(h, buf, length + 1)
                    if "Dism" in buf.value:
                        found.append(h)
            return True

        ctypes.windll.user32.EnumWindows(cb, 0)
        return bool(found)
    except Exception:
        return False


def find_dismpp_path() -> str:
    custom = reg_get("dismpp_path", "")
    if custom and os.path.isfile(custom):
        return custom
    for p in DISMPP_DEFAULT_PATHS:
        if os.path.isfile(p):
            return p
    return ""


@register
class TaskDismPP(Task):
    key = "dismpp"
    name = "Dism++ 空间回收"
    icon = "🧰"
    order = 60
    interactive = True   # 需要用户手动点击，run_all 应排除
    desc = ("启动 Dism++ 进行「空间回收」（保留默认勾选 → 扫描 → 清理）\n"
            "本工具采用「自动启动 + 置顶引导窗」方案：\n"
            "程序启动 Dism++，按置顶引导窗提示操作，完成后点击「已完成」\n"
            "⚠ 扫描与清理耗时可能较长，期间请勿取消或中止")

    def available(self):
        p = find_dismpp_path()
        return (bool(p), "路径已就绪" if p else "未找到 Dism++，请在「路径设置」中指定")

    def describe(self):
        p = find_dismpp_path()
        return ("确认执行 Dism++ 空间回收？",
                f"将启动：\n  {p}\n\n"
                f"启动后会弹出置顶引导窗，请按提示在 Dism++ 中完成 4 次点击：\n"
                f"  1) 左侧找到「常用工具」并点击\n"
                f"  2) 展开后点击「空间回收」\n"
                f"  3) 右侧点击「扫描」并等待扫描完成（数分钟）\n"
                f"  4) 扫描完成后点击「清理」并确认\n\n"
                f"⚠ 扫描与清理过程耗时较长，请勿关闭引导窗与 Dism++。")

    # Dism++ 的真实执行走的是 App._run_dismpp_guided()（主线程 + 引导窗），
    # 这里的 run() 仅作占位/单元测试用：探测 + 报错。
    def run(self):
        raise RuntimeError("Dism++ 任务应通过 App._run_dismpp_guided() 调用")


# --------------------------------------------------------------------------- #
# 7.5 Fluent 自绘组件（tkinter 原生控件无法做圆角，统一用 Canvas 绘制）
# --------------------------------------------------------------------------- #

class FluentCard(tk.Canvas):
    """圆角卡片容器：外层 Canvas 画圆角背景+描边，inner 为承载内容的普通 Frame。"""

    def __init__(self, master, radius=R_WIN, fill=None, border=None,
                 padx=1, pady=1, **kw):
        # 默认值不再写死为某个主题色，而是惰性从 THEME 解析 —— 主题切换后被重建时
        # 会拿到新值；已有的实例也可以通过 set_fill / set_border 单独刷新
        if fill is None:
            fill = THEME["card"]
        if border is None:
            border = THEME["border"]
        try:
            outer_bg = master.cget("bg")
        except Exception:
            outer_bg = THEME["bg"]
        # 关键：Canvas 的 bg 用 fill 而不是 master.bg —— 高 DPI (200%) 下
        # 内嵌 Frame 与圆角多边形之间可能有 1-2px 子像素缝隙，若 Canvas bg 是
        # 主题背景色就会在卡片边缘露出一条「亮线」（主窗口的浅色底色透出来）。
        # 把 Canvas 自身也涂成 fill 颜色，任何缝隙都只显示卡片色。
        super().__init__(master, bd=0, highlightthickness=0,
                         highlightbackground=fill, bg=fill, **kw)
        self._r, self._fill, self._border = radius, fill, border
        self._padx, self._pady = padx, pady
        self.inner = tk.Frame(self, bg=fill, bd=0, highlightthickness=0)
        self._win = self.create_window(padx, pady, anchor="nw", window=self.inner)
        self.bind("<Configure>", self._redraw)

    def set_fill(self, color: str):
        self._fill = color
        self.inner.configure(bg=color)
        self._redraw()

    def set_border(self, color: str):
        self._border = color
        self._redraw()

    def _redraw(self, _event=None):
        w, h = self.winfo_width(), self.winfo_height()
        if w <= 2 or h <= 2:
            return
        self.delete("__bg")
        self.create_polygon(round_rect_points(1, 1, w - 1, h - 1, self._r),
                            fill=self._fill, outline=self._border, width=1,
                            tags="__bg")
        self.tag_lower("__bg")
        self.coords(self._win, self._padx, self._pady)
        self.itemconfigure(self._win,
                           width=max(1, w - 2 * self._padx),
                           height=max(1, h - 2 * self._pady))


class FluentButton(tk.Frame):
    """圆角按钮：standard / accent / danger / subtle 四种样式，含悬停与按下态。

    ★ v0.2.x 重构：从 Canvas+create_text 改为 Frame + Canvas 背景层 + 独立 Label。
      原因：tkinter Canvas.create_text 在 Windows 200% DPI 下存在已知 bug——
      文字会被绘制两次并错位叠加（每个字符都呈现"双重"效果）；
      Canvas 内嵌 Label (create_window) 同样会触发该 bug。
      正确做法：Canvas 仅作为画圆角的背景层，Label 作为兄弟控件直接 place 在
      Frame 上 —— 这样 Label 由系统原生渲染，DPI 自动处理、不再重叠。
    """

    @staticmethod
    def _styles_now():
        return {
            "standard": dict(face=BTN_FACE, hover=BTN_HOVER, press=BTN_PRESS,
                             border=BTN_BORDER, fg=TEXT, weight="normal"),
            "accent":   dict(face=ACCENT, hover=ACCENT_HOVER, press=ACCENT_PRESS,
                             border=ACCENT_PRESS, fg="#FFFFFF", weight="bold"),
            "danger":   dict(face=ERRC, hover="#D13438", press="#A4262C",
                             border="#A4262C", fg="#FFFFFF", weight="bold"),
            "subtle":   dict(face=BG, hover="#EAEAEA", press="#E0E0E0",
                             border=BORDER, fg=TEXT, weight="normal"),
        }

    def __init__(self, master, text="", command=None, kind="standard",
                 width=None, height=44, padx=24, icon="", font_size=10):
        try:
            outer_bg = master.cget("bg")
        except Exception:
            outer_bg = THEME["bg"]
        self._kind = kind
        self._cmd = command
        self._hover = self._press = False
        self._enabled = True
        self._label = f"{icon}  {text}" if icon else text

        st = self._styles_now().get(kind, self._styles_now()["standard"])
        self._f = tkfont.Font(family=FONT, size=font_size, weight=st["weight"])

        # 计算按钮宽度（measure 乘 1.45 系数 + padx）
        if width:
            w = width
        else:
            m = self._f.measure(self._label)
            w = max(80, int(m * 1.45) + padx * 2)

        # 1. 外层 Frame（透明容器）
        super().__init__(master, bg=outer_bg, width=w, height=height)
        self.pack_propagate(False)

        # 2. Canvas 画圆角背景（铺满 Frame；不嵌入任何 widget，只画 polygon）
        self._cv = tk.Canvas(self, bd=0, highlightthickness=0, bg=outer_bg,
                             width=w, height=height, cursor="hand2")
        self._cv.place(x=0, y=0, relwidth=1.0, relheight=1.0)

        # 3. Label 显示文字 —— 与 Canvas 是兄弟控件而非 Canvas 的 child，
        #    这样 Label 由系统原生渲染，不会触发 Canvas 内嵌的双重绘制 bug
        self._lbl = tk.Label(self, text=self._label, font=self._f,
                             bg=st["face"], fg=st["fg"], bd=0, highlightthickness=0,
                             cursor="hand2")
        self._lbl.place(relx=0.5, rely=0.5, anchor="center")

        # 4. 事件绑定（Frame/Canvas/Label 都要绑，因为事件可能发生在任意区域）
        for w in (self, self._cv, self._lbl):
            w.bind("<Enter>", self._on_enter, add="+")
            w.bind("<Leave>", self._on_leave, add="+")
            w.bind("<ButtonPress-1>", self._on_press, add="+")
            w.bind("<ButtonRelease-1>", self._on_release, add="+")

        self._cv.bind("<Configure>", lambda e: self._draw())

    def _on_enter(self, _e):
        self._hover = True
        self._draw()

    def _on_leave(self, _e):
        self._hover = self._press = False
        self._draw()

    def _on_press(self, _e):
        if self._enabled:
            self._press = True
            self._draw()

    def _on_release(self, _e):
        if not self._enabled:
            return
        self._press = False
        self._draw()
        if self._cmd:
            self._cmd()

    def set_enabled(self, on: bool):
        self._enabled = on
        cur = "hand2" if on else "arrow"
        try:
            self.configure(cursor=cur)
            self._cv.configure(cursor=cur)
            self._lbl.configure(cursor=cur)
        except Exception:
            pass
        self._draw()

    def set_text(self, text: str):
        self._label = text
        self._lbl.configure(text=text)
        # 重新计算宽度
        m = self._f.measure(text)
        w = max(80, int(m * 1.45) + 36)
        self.configure(width=w)
        self._cv.configure(width=w)

    def set_kind(self, kind: str):
        """运行时切换样式（如设置对话框里选中态高亮）。"""
        self._kind = kind
        st = self._styles_now().get(kind, self._styles_now()["standard"])
        try:
            self._f.configure(weight=st["weight"])
        except Exception:
            self._f = tkfont.Font(family=FONT, size=self._f.cget("size"),
                                  weight=st["weight"])
            self._lbl.configure(font=self._f)
        self._draw()

    def _draw(self):
        """重绘圆角背景 + 同步 Label 颜色。"""
        st = self._styles_now().get(self._kind, self._styles_now()["standard"])
        if not self._enabled:
            fill, fg, bd = BTN_DISABLED, MUTED, BORDER
        elif self._press:
            fill, fg, bd = st["press"], st["fg"], st["border"]
        elif self._hover:
            fill, fg, bd = st["hover"], st["fg"], st["border"]
        else:
            fill, fg, bd = st["face"], st["fg"], st["border"]

        cw = self._cv.winfo_width()
        ch = self._cv.winfo_height()
        if cw <= 2 or ch <= 2:
            return
        self._cv.delete("__bg")
        self._cv.create_polygon(round_rect_points(1, 1, cw - 1, ch - 1, R_CTL),
                                fill=fill, outline=bd, width=1, tags="__bg")
        self._cv.tag_lower("__bg")
        # Label 颜色（系统原生，不会有 DPI 双重渲染 bug）
        self._lbl.configure(bg=fill, fg=fg, font=self._f)


class FluentTile(tk.Frame):
    """功能磁贴：整块可点击的卡片，含图标、标题、可选副标题与悬停态。

    ★ v0.2.x 重构：与 FluentButton 一致，Canvas 仅作圆角背景层，文字（图标/标题/
      副标题）全部用原生 Label 渲染——规避 Windows 200% DPI 下 Canvas.create_text
      的双重绘制 bug（之前主界面磁贴文字在 200% 缩放下会重影/错位）。
    """

    def __init__(self, master, icon="", title="", subtitle="",
                 command=None, height=88):
        try:
            outer_bg = master.cget("bg")
        except Exception:
            outer_bg = BG
        super().__init__(master, bg=outer_bg, height=height, cursor="hand2")
        self.pack_propagate(False)
        self._cmd = command
        self._hover = self._press = False
        self._enabled = True
        self._icon, self._title, self._sub = icon, title, subtitle
        self._f_icon = tkfont.Font(family=FONT, size=15)
        self._f_title = tkfont.Font(family=FONT, size=10, weight="bold")
        self._f_sub = tkfont.Font(family=FONT, size=8)
        self._h = height
        # emoji 字体宽度测量常为 0（字体不含 emoji 字形时），故最小给 36 像素
        self._icon_w = max(36, self._f_icon.measure(self._icon) if self._icon else 0)

        # 1. Canvas 仅画圆角背景（铺满 Frame，不画任何文字）
        self._cv = tk.Canvas(self, bd=0, highlightthickness=0, bg=outer_bg,
                             cursor="hand2")
        self._cv.place(x=0, y=0, relwidth=1.0, relheight=1.0)

        # 2. 图标 Label（原生渲染）
        self._lbl_icon = tk.Label(self, text=self._icon, font=self._f_icon,
                                  bg=outer_bg, fg=TEXT, bd=0, cursor="hand2")
        self._lbl_icon.place(x=18, y=height // 2, anchor="w")

        # 3. 标题 / 副标题 Label（原生渲染）
        x_text = 18 + self._icon_w + 8
        self._lbl_title = tk.Label(self, text=self._title, font=self._f_title,
                                   bg=outer_bg, fg=TEXT, bd=0, cursor="hand2",
                                   anchor="w")
        self._lbl_sub = tk.Label(self, text=subtitle, font=self._f_sub,
                                 bg=outer_bg, fg=SUBTEXT, bd=0, cursor="hand2",
                                 anchor="w")
        self._place_text()
        if not subtitle:
            self._lbl_sub.place_forget()

        # 4. 事件绑定（Frame / Canvas / 各 Label 都要绑）
        for w in (self, self._cv, self._lbl_icon, self._lbl_title, self._lbl_sub):
            w.bind("<Enter>", self._on_enter, add="+")
            w.bind("<Leave>", self._on_leave, add="+")
            w.bind("<ButtonPress-1>", self._on_press, add="+")
            w.bind("<ButtonRelease-1>", self._on_release, add="+")
        self._cv.bind("<Configure>", lambda e: self._draw())

    def _place_text(self):
        """按是否有副标题，定位标题/副标题 Label。"""
        x_text = 18 + self._icon_w + 8
        if self._sub:
            self._lbl_title.place_configure(x=x_text, y=self._h // 2 - 9, anchor="w")
            self._lbl_sub.place_configure(x=x_text, y=self._h // 2 + 10, anchor="w")
        else:
            self._lbl_title.place_configure(x=x_text, y=self._h // 2, anchor="w")

    # ---- 状态 ---- #
    def _on_enter(self, _e):
        self._hover = True
        self._draw()

    def _on_leave(self, _e):
        self._hover = self._press = False
        self._draw()

    def _on_press(self, _e):
        if self._enabled:
            self._press = True
            self._draw()

    def _on_release(self, _e):
        if not self._enabled:
            return
        self._press = False
        self._draw()
        if self._cmd:
            self._cmd()

    def set_enabled(self, on: bool, subtitle: str = ""):
        self._enabled = on
        self._sub = subtitle
        self.configure(cursor="hand2" if on else "arrow")
        self._lbl_sub.configure(text=subtitle)
        if subtitle:
            self._place_text()
            if not self._lbl_sub.winfo_ismapped():
                self._lbl_sub.place(x=18 + self._icon_w + 8,
                                    y=self._h // 2 + 10, anchor="w")
        else:
            self._lbl_sub.place_forget()
            self._place_text()
        self._draw()

    def set_subtitle(self, text: str):
        self._sub = text
        self._lbl_sub.configure(text=text)
        if text:
            self._place_text()
            if not self._lbl_sub.winfo_ismapped():
                self._lbl_sub.place(x=18 + self._icon_w + 8,
                                    y=self._h // 2 + 10, anchor="w")
        else:
            self._lbl_sub.place_forget()
            self._place_text()
        self._draw()

    def _draw(self):
        w, h = self.winfo_width(), self.winfo_height()
        if w <= 2 or h <= 2:
            return
        if not self._enabled:
            fill, bd, tfg, sfg = TILE_DISABLED, BORDER, MUTED, TILE_DISABLED_SUB
        elif self._press:
            fill, bd, tfg, sfg = BTN_PRESS, BORDER_STR, TEXT, SUBTEXT
        elif self._hover:
            fill, bd, tfg, sfg = CARD_HOVER, BORDER_STR, TEXT, SUBTEXT
        else:
            fill, bd, tfg, sfg = CARD, BORDER, TEXT, SUBTEXT
        self._cv.delete("all")
        self._cv.create_polygon(round_rect_points(1, 1, w - 1, h - 1, R_WIN),
                                fill=fill, outline=bd, width=1)
        # Label 颜色同步（系统原生渲染，无 DPI 双重绘制问题）
        self._lbl_icon.configure(bg=fill, fg=tfg if self._enabled else MUTED)
        self._lbl_title.configure(bg=fill, fg=tfg)
        self._lbl_sub.configure(bg=fill, fg=sfg)


class Pill(tk.Frame):
    """胶囊徽章（如管理员权限状态）。

    ★ v0.2.x 重构：Canvas 仅作圆角背景层，文字用原生 Label 渲染——
      规避 Windows 200% DPI 下 Canvas.create_text 的双重绘制 bug。
    """

    def __init__(self, master, text="", fill=None, fg=None, height=32):
        if fill is None:
            fill = THEME["ok_bg"]
        if fg is None:
            fg = THEME["ok"]
        try:
            outer_bg = master.cget("bg")
        except Exception:
            outer_bg = THEME["bg"]
        self._f = tkfont.Font(family=FONT, size=9, weight="bold")
        super().__init__(master, bg=outer_bg, height=height,
                         width=self._f.measure(text) + 46)
        self.pack_propagate(False)
        self._fill, self._fg, self._text = fill, fg, text
        self._h = height
        self._cv = tk.Canvas(self, bd=0, highlightthickness=0, bg=outer_bg)
        self._cv.place(x=0, y=0, relwidth=1.0, relheight=1.0)
        self._lbl = tk.Label(self, text="● " + text, font=self._f,
                             bg=fill, fg=fg, bd=0)
        self._lbl.place(relx=0.5, rely=0.5, anchor="center")
        self._cv.bind("<Configure>", lambda e: self._draw())

    def set(self, text: str, fill: str, fg: str):
        self._text, self._fill, self._fg = text, fill, fg
        self.configure(width=self._f.measure(text) + 46)
        self._lbl.configure(text="● " + text, bg=fill, fg=fg)
        self._draw()

    def _draw(self):
        w, h = self.winfo_width(), self.winfo_height()
        if w <= 2 or h <= 2:
            return
        self._cv.delete("all")
        self._cv.create_polygon(round_rect_points(1, 1, w - 1, h - 1, h / 2),
                                fill=self._fill, outline=self._fill)
        self._lbl.configure(bg=self._fill, fg=self._fg)


# --------------------------------------------------------------------------- #
# 7.6 简易 Tooltip（避免引入额外依赖）
# --------------------------------------------------------------------------- #

def make_tooltip(widget, text: str, delay_ms: int = 380):
    """给任意控件绑定一段悬停说明。显示在控件上方居中。"""
    state = {"tip": None, "after_id": None}

    def _show():
        if state["tip"] is not None:
            return
        try:
            x = widget.winfo_rootx() + widget.winfo_width() // 2
            y = widget.winfo_rooty() - 32
            tip = tk.Toplevel(widget)
            tip.wm_overrideredirect(True)
            tip.wm_geometry(f"+{x}+{y}")
            tip.configure(bg=THEME["border_strong"])
            inner = tk.Frame(tip, bg=THEME["text"], padx=1, pady=1)
            inner.pack()
            tk.Label(inner, text=text, font=(FONT, 8), bg=THEME["text"],
                     fg=THEME["bg"], padx=8, pady=4, justify="left"
                     ).pack()
            state["tip"] = tip
        except Exception:
            pass

    def _hide(_e=None):
        if state["after_id"]:
            try: widget.after_cancel(state["after_id"])
            except Exception: pass
            state["after_id"] = None
        if state["tip"] is not None:
            try: state["tip"].destroy()
            except Exception: pass
            state["tip"] = None

    def _enter(_e):
        state["after_id"] = widget.after(delay_ms, _show)

    widget.bind("<Enter>", _enter, add="+")
    widget.bind("<Leave>", _hide, add="+")
    widget.bind("<ButtonPress-1>", _hide, add="+")


def fluent_scrollbar_style(style: ttk.Style):
    """Win11 细条滚动条：扁平滑块、无箭头感（保留箭头但压缩）。"""
    try:
        thumb = SCROLL_THUMB
        for name, trough in (("Fluent.Vertical.TScrollbar", THEME["bg"]),
                             ("Fluent.Horizontal.TScrollbar", THEME["bg"])):
            style.configure(name, background=thumb, troughcolor=trough,
                            bordercolor=trough, lightcolor=thumb,
                            darkcolor=thumb, arrowsize=11, width=12)
            style.map(name, background=[("pressed", "#8A8A8A"),
                                        ("active", "#A6A6A6")])
        # 卡片内部（白底）版本：滑道与卡片同色，避免灰条突兀
        for name, trough in (("Card.Vertical.TScrollbar", THEME["card"]),
                             ("Card.Horizontal.TScrollbar", THEME["card"])):
            style.configure(name, background=thumb, troughcolor=trough,
                            bordercolor=trough, lightcolor=thumb,
                            darkcolor=thumb, arrowsize=11, width=12)
            style.map(name, background=[("pressed", "#8A8A8A"),
                                        ("active", "#A6A6A6")])
    except Exception:
        pass


# --------------------------------------------------------------------------- #
# 8. 界面组件
# --------------------------------------------------------------------------- #

class DismPPGuide(tk.Toplevel):
    """Dism++ 4 步引导窗：置顶，贴在 Dism++ 窗口右侧。

    行为规范（v0.3.0）：
      • 无底部按钮——不再要求用户点击确认。
      • 自动机制：轮询 Dism++ 进程与窗口，一旦检测到 Dism++ 已关闭，
        本引导窗自动关闭。
      • 若用户在 Dism++ 关闭前手动关闭本窗（点 X / 系统关闭），
        置位会话级标记，本次会话内后续启动 Dism++ 不再弹出引导窗。
    """

    STEPS = [
        "在左侧列表中找到「常用工具」并点击",
        "在展开项中找到「空间回收」并点击",
        "在右侧页面点击「扫描」按钮，等待扫描完成（可能数分钟）",
        "扫描完成后点击「清理」按钮，在弹出的确认框中点「是」",
    ]

    # 窗口尺寸：去掉底栏后，标题 + 4 步骤 + 警示 可完整显示
    WIN_W = 620
    WIN_H = 640
    # Label 内容 wrap 像素宽度：留 24px 边距后约 572
    WRAP_W = 572

    def __init__(self, master, proc: subprocess.Popen):
        super().__init__(master)
        self.proc = proc
        self.title("Dism++ 操作引导")
        self.configure(bg=BG)
        self.attributes("-topmost", True)
        self.resizable(False, False)
        self.transient(master)
        self.update_idletasks()

        # 定位到 Dism++ 窗口右侧
        self._place_near_dismpp()

        # 用户手动关闭（点 X 或系统关闭）：记录会话级标记，本次会话不再弹出
        self.protocol("WM_DELETE_WINDOW", self._on_manual_close)

        head = tk.Frame(self, bg=ACCENT, height=56)
        head.pack(side="top", fill="x")
        head.pack_propagate(False)
        tk.Label(head, text="  Dism++ 操作引导", font=(FONT, 12, "bold"),
                 bg=ACCENT, fg="white").pack(side="left", padx=14, pady=8)
        tk.Label(head, text="窗口置顶", font=(FONT, 8), bg=ACCENT, fg="#D6EBFA"
                 ).pack(side="right", padx=14)

        # 内容区（在 head 之下展开），加 wraplength 防止长句被裁
        body = tk.Frame(self, bg=BG)
        body.pack(side="top", fill="both", expand=True, padx=18, pady=(16, 8))

        tk.Label(body, text="Dism++ 已自动启动。请按以下步骤点击：",
                 font=(FONT, 9), bg=BG, fg=SUBTEXT, justify="left",
                 wraplength=self.WRAP_W, anchor="w"
                 ).pack(anchor="w", pady=(0, 10), fill="x")

        for i, s in enumerate(self.STEPS, 1):
            row = tk.Frame(body, bg=BG)
            row.pack(fill="x", pady=6)
            tk.Label(row, text=f"{i}.", font=(FONT, 12, "bold"),
                     bg=BG, fg=PRIMARY, width=3).pack(side="left", anchor="n")
            # wraplength 留 3 字符宽度 ≈ 36 给编号 + 8 间距
            tk.Label(row, text=s, font=(FONT, 10), bg=BG, fg=TEXT,
                     justify="left", wraplength=self.WRAP_W - 36,
                     anchor="w").pack(side="left", fill="x")

        tk.Label(body, text="⚠ 本窗口会在 Dism++ 关闭后自动消失；你也可以随时手动关闭它，关闭后本次操作不再弹出引导。",
                 font=(FONT, 9), bg=BG, fg=WARNC, justify="left",
                 wraplength=self.WRAP_W
                 ).pack(anchor="w", pady=(14, 0), fill="x")

        self._polling = True
        self.after(800, self._poll_dismpp)

    def _place_near_dismpp(self):
        try:
            import ctypes.wintypes as wt
            found = []

            @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)
            def cb(h, _):
                length = ctypes.windll.user32.GetWindowTextLengthW(h)
                if length:
                    buf = ctypes.create_unicode_buffer(length + 1)
                    ctypes.windll.user32.GetWindowTextW(h, buf, length + 1)
                    if "Dism" in buf.value and ctypes.windll.user32.IsWindowVisible(h):
                        found.append(h)
                return True
            ctypes.windll.user32.EnumWindows(cb, 0)
            if found:
                rect = wt.RECT()
                ctypes.windll.user32.GetWindowRect(found[0], ctypes.byref(rect))
                x, y = rect.right + 10, rect.top
                w, h = self.WIN_W, self.WIN_H
                sw = ctypes.windll.user32.GetSystemMetrics(0)
                sh = ctypes.windll.user32.GetSystemMetrics(1)
                if x + w > sw:
                    x = max(0, rect.left - w - 10)
                if x < 0:
                    x = (sw - w) // 2
                if y + h > sh:
                    y = max(0, sh - h - 20)
                if y < 0:
                    y = 20
                self.geometry(f"{w}x{h}+{x}+{y}")
                return
        except Exception:
            pass
        self.geometry(f"{self.WIN_W}x{self.WIN_H}")

    def _poll_dismpp(self):
        if not self._polling:
            return
        # 仅当进程退出 AND 窗口也消失时，才判定 Dism++ 已关闭
        # 避免 Dism++ 弹出确认对话框临时隐藏时误判
        if self.proc.poll() is not None and not _dismpp_window_exists():
            self._on_auto_close()
            return
        self.after(800, self._poll_dismpp)

    def _on_auto_close(self):
        """Dism++ 已关闭的自动收尾：不打"已手动关闭"标记，后续仍可正常弹出。"""
        self._polling = False
        LOG.info("Dism++ 已关闭，引导窗自动关闭")
        self.destroy()

    def _on_manual_close(self):
        """用户手动关闭（点 X / 系统关闭）：置位会话标记，本次会话内不再弹出。"""
        self._polling = False
        try:
            self.master._dismpp_guide_dismissed = True
        except Exception:
            pass
        LOG.info("用户手动关闭引导窗（Dism++ 仍保持打开），本次会话内不再弹出")
        self.destroy()


class ConfirmDialog(tk.Toplevel):
    """二次确认弹窗：显示将要执行的操作详情，用户确认后方可继续。"""

    def __init__(self, master, title: str, body: str):
        super().__init__(master)
        self.result = False
        self.title(title)
        self.configure(bg=BG)
        self.resizable(True, True)
        self.transient(master)
        self.grab_set()

        self.geometry("720x600")
        self.minsize(580, 460)
        self.update_idletasks()
        self._center(master)

        # 关键：先 pack 底栏并显式 side="bottom"，再让内容区用 expand 填满中间剩余空间
        # 否则在某些尺寸/主题下底栏会被裁掉
        bar = tk.Frame(self, bg=BG)
        bar.pack(side="bottom", fill="x", padx=20, pady=(12, 18))
        FluentButton(bar, text="取消", kind="standard", height=44,
                     command=self._cancel).pack(side="right", padx=(10, 0))
        FluentButton(bar, text="确认执行", kind="accent", height=44,
                     command=self._ok).pack(side="right")

        head = tk.Frame(self, bg=BG)
        head.pack(side="top", fill="x", padx=20, pady=(18, 8))
        tk.Label(head, text="⚠ 请确认操作", font=(FONT, 14, "bold"),
                 bg=BG, fg=TEXT).pack(anchor="w")
        # 关键修复：副标题加 wraplength + justify=left，确保多行文字不溢出
        tk.Label(head, text="此操作将删除文件，执行后不可恢复。确认无误后点击「确认执行」。",
                 font=(FONT, 9), bg=BG, fg=SUBTEXT, justify="left",
                 wraplength=680, anchor="w").pack(anchor="w", pady=(2, 0), fill="x")

        # 内容区放在 head 和 bar 之间，expand 填满剩余
        box = FluentCard(self, radius=R_WIN, fill=CARD, border=BORDER)
        box.pack(side="top", fill="both", expand=True, padx=20, pady=6)
        txt = tk.Text(box.inner, wrap="word", font=("Consolas", 9), bg=CARD,
                      fg=TEXT, relief="flat", bd=0, padx=12, pady=10,
                      spacing1=2, highlightthickness=0)
        sb = ttk.Scrollbar(box.inner, style="Card.Vertical.TScrollbar",
                           command=txt.yview)
        txt.configure(yscrollcommand=sb.set)
        txt.insert("1.0", body)
        txt.configure(state="disabled")
        sb.pack(side="right", fill="y")
        txt.pack(side="left", fill="both", expand=True)

        self.bind("<Escape>", lambda e: self._cancel())
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.wait_window()

    def _center(self, master):
        self.update_idletasks()
        w, h = self.winfo_width(), self.winfo_height()
        x = master.winfo_rootx() + (master.winfo_width() - w) // 2
        y = master.winfo_rooty() + (master.winfo_height() - h) // 2
        self.geometry(f"+{max(x,0)}+{max(y,0)}")

    def _ok(self):
        self.result = True
        self.destroy()

    def _cancel(self):
        self.result = False
        self.destroy()


class ErrorDialog(tk.Toplevel):
    """失败时弹出的报错窗口，内含本次完整日志，便于反馈与优化。"""

    def __init__(self, master, title: str, err_text: str, full_log: str):
        super().__init__(master)
        self.title(title)
        self.configure(bg=BG)
        self.geometry("780x560")
        self.minsize(640, 460)
        self.transient(master)
        self.update_idletasks()
        x = master.winfo_rootx() + (master.winfo_width() - 780) // 2
        y = master.winfo_rooty() + (master.winfo_height() - 560) // 2
        self.geometry(f"+{max(x,0)}+{max(y,0)}")

        # 底栏：先 pack 并 side="bottom" 强制固定在底部（★ 此前曾重复 pack 一次，已删除）
        bar = tk.Frame(self, bg=BG)
        bar.pack(side="bottom", fill="x", padx=20, pady=(12, 18))
        FluentButton(bar, text="关闭", kind="standard", height=44,
                     command=self.destroy).pack(side="right", padx=(10, 0))
        FluentButton(bar, text="导出日志", kind="accent", height=44,
                     command=self._export).pack(side="right")

        head = tk.Frame(self, bg=BG)
        head.pack(side="top", fill="x", padx=20, pady=(18, 8))
        tk.Label(head, text="❌ 执行失败", font=(FONT, 14, "bold"),
                 bg=BG, fg=ERRC).pack(anchor="w")
        tk.Label(head, text="可点击「导出日志」保存后反馈，便于定位与修复。",
                 font=(FONT, 9), bg=BG, fg=SUBTEXT, justify="left",
                 wraplength=740, anchor="w").pack(anchor="w", pady=(4, 0), fill="x")

        box = FluentCard(self, radius=R_WIN, fill=CARD, border=BORDER)
        box.pack(side="top", fill="both", expand=True, padx=20, pady=6)
        txt = tk.Text(box.inner, wrap="none", font=("Consolas", 9), bg=CARD,
                      fg=TEXT, relief="flat", bd=0, padx=12, pady=10,
                      highlightthickness=0)
        sb = ttk.Scrollbar(box.inner, style="Card.Vertical.TScrollbar",
                           command=txt.yview)
        txt.configure(yscrollcommand=sb.set)
        txt.insert("1.0", err_text + "\n\n" + "=" * 70 +
                   "\n本次完整日志\n" + "=" * 70 + "\n" + full_log)
        txt.configure(state="disabled")
        sb.pack(side="right", fill="y")
        txt.pack(side="left", fill="both", expand=True)

        self._log = txt.get("1.0", "end-1c")

    def _export(self):
        p = filedialog.asksaveasfilename(
            parent=self, defaultextension=".log",
            initialfile=f"cleaner-log-{datetime.now():%Y%m%d-%H%M%S}.log",
            filetypes=[("日志文件", "*.log"), ("文本文件", "*.txt")])
        if p:
            try:
                with open(p, "w", encoding="utf-8") as f:
                    f.write(self._log)
                messagebox.showinfo("已导出", f"日志已保存到：\n{p}", parent=self)
            except Exception as e:
                messagebox.showerror("导出失败", str(e), parent=self)


# --------------------------------------------------------------------------- #
# 9. 主窗口
# --------------------------------------------------------------------------- #

class App(tk.Tk):

    def __init__(self):
        super().__init__()
        init_theme()          # 探测并锁定实际 UI 字体（须在 Tk 根窗口创建之后）
        self.title(APP_NAME)
        self.configure(bg=BG)
        # 高度上调以保证日志卡 + 底栏按钮始终完整可见（不依赖 expand 的弹性分配）
        # v0.3.0：默认与最小高度各上调 ~70px，多出的纵向空间由唯一可扩展的
        # 日志区独占，使「运行日志」初始显示更高
        self.geometry("1140x1030")
        self.minsize(1040, 940)

        self._q: queue.Queue = queue.Queue()
        self._busy = False
        self._tasks: dict[str, Task] = {}
        # 用户若在某次 Dism++ 引导窗关闭前手动关掉了它，则本次会话内
        # 后续再启动 Dism++ 不再弹出引导窗（尊重用户选择）
        self._dismpp_guide_dismissed = False

        # 先创建任务对象（包含状态/路径/进度），再构建纯展示用的 UI
        # —— 这样 rebuild_ui() 销毁并重建控件时不会丢失任务状态
        self._create_tasks()
        self._build_ui()
        LOG.add_sink(lambda line, lvl: self._q.put(("log", line, lvl)))
        self.after(80, self._drain)
        self._restore_log()

        LOG.info(f"{APP_NAME} v{APP_VER} 启动")
        LOG.info(f"管理员权限: {'是' if is_admin() else '否'}")
        LOG.info(f"系统临时目录: {temp_dir()}")

        # 注册到模块级 _APP_REF，供 apply_theme() 找到本实例触发 UI 重建
        _APP_REF.append(self)

    def _create_tasks(self) -> None:
        """实例化所有任务。调用一次即可；主题切换不会重建任务对象。"""
        if self._tasks:
            return
        for cls in TASK_REGISTRY:
            t = cls()
            self._tasks[t.key] = t

    def rebuild_ui(self) -> None:
        """主题切换时调用：销毁所有子控件并重建（保留任务实例与日志总线）。

        ★ 关键：rebuild_ui 不会销毁 root 本身，但 root.configure(bg=BG)
          是在 __init__ 时调用的；这里必须再次同步，否则切到浅色后
          root 客户区仍是深色 —— 表现为「切换主题后显示问题」（root
          与卡片之间的颜色断层，看上去像有一条深色「外框」）。
        """
        self.configure(bg=BG)
        # 主题切换前先关闭可能打开的子窗口（避免它们保持旧色）
        for w in list(self.winfo_children()):
            try:
                if isinstance(w, tk.Toplevel):
                    w.destroy()
            except Exception:
                pass
        for w in list(self.winfo_children()):
            try:
                w.destroy()
            except Exception:
                pass
        self._build_ui()
        self._restore_log()
        self._fit_help_height()
        self.refresh_tasks()

    def _restore_log(self) -> None:
        """重建 UI 后从内存日志总线回填历史日志，避免主题切换清空日志显示。

        ★ 注意：LOG._lines 存储的是已格式化的整行字符串
          "[HH:MM:SS] [LEVEL] msg"，并非 (line, level) 元组；
          需从中解析出 level 再回填（_on_log 接收 (整行, level)）。
        """
        try:
            with LOG._lock:
                lines = list(LOG._lines)
        except Exception:
            lines = []
        for entry in lines:
            lvl = "INFO"
            if isinstance(entry, str):
                j = entry.find("] [")
                if j != -1:
                    tail = entry[j + 3:]
                    k = tail.find("]")
                    if k != -1:
                        cand = tail[:k]
                        if cand.isalpha():
                            lvl = cand
            self._on_log(entry, lvl)

    # ---------------- UI 构建 ---------------- #

    def _build_ui(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass
        fluent_scrollbar_style(style)

        # ★ 关键修复：底栏用 side="bottom" 强制固定在窗口底部，pack_propagate(False)
        #   + 显式高度 80px（按钮 38px 高度 + 上下 padding），不再被 expand 的日志区挤压到看不见
        bar = tk.Frame(self, bg=BG, height=90)
        bar.pack(side="bottom", fill="x", padx=20, pady=(0, 14))
        bar.pack_propagate(False)
        # 右侧按钮先 pack（按 right→left 视觉顺序）
        FluentButton(bar, text="退出", kind="standard", height=44,
                     command=self.quit_app).pack(side="right")
        FluentButton(bar, text="一键清理全部", kind="accent", height=44,
                     command=self.run_all).pack(side="right", padx=(0, 10))
        # 左侧按钮：仅保留「设置」（「重新自动检测路径」已迁入设置弹窗，逻辑更内聚）
        FluentButton(bar, text="设置", kind="standard", height=44,
                     command=self.open_settings).pack(side="left", padx=(0, 8))

        # 顶栏：Win11 风格 —— 与窗口同底、大号半粗标题 + 胶囊状态徽章 + 1px 分隔线
        top = tk.Frame(self, bg=BG, height=86)
        top.pack(side="top", fill="x")
        top.pack_propagate(False)
        tk.Label(top, text=APP_NAME, font=(FONT, 18, "bold"),
                 bg=BG, fg=TEXT).pack(side="left", padx=(24, 0), pady=(24, 0))
        tk.Label(top, text=APP_VER, font=(FONT, 9),
                 bg=BG, fg=MUTED).pack(side="left", padx=(10, 0), pady=(32, 0))

        admin_ok = is_admin()
        self._pill = Pill(top, "管理员权限已获取" if admin_ok else "未获管理员权限",
                          OK_BG if admin_ok else ERR_BG,
                          OKC if admin_ok else ERRC)
        self._pill.pack(side="right", padx=24, pady=(27, 0))
        tk.Frame(self, bg=BORDER, height=1).pack(side="top", fill="x")

        # 功能磁贴区（副标题用蓝色，与「功能说明」/主标题色一致）
        body = tk.Frame(self, bg=BG)
        body.pack(side="top", fill="x", padx=20, pady=(16, 4))
        tk.Label(body, text="功能", font=(FONT, 10, "bold"),
                 bg=BG, fg=ACCENT_TEXT).pack(anchor="w")

        grid = tk.Frame(body, bg=BG)
        grid.pack(side="top", fill="x", pady=(8, 0))
        for i in range(3):
            grid.columnconfigure(i, weight=1, uniform="tile")

        self._help_samples: list[str] = []
        self._help_h = 0
        self._help_w = 0
        # ★ 关键变更：不再在此处新建 Task 对象；任务在 _create_tasks() 创建一次后
        #   主题切换重建 UI 时复用同一份实例（保留进度/缓存大小等运行时状态）
        for idx, t in enumerate(sorted(self._tasks.values(), key=lambda x: x.order)):
            self._make_button(grid, t, idx)

        # 悬停说明区（★ 高度在运行时按实际字体度量动态计算，彻底规避 DPI 差异）
        help_outer = tk.Frame(self, bg=BG)
        help_outer.pack(side="top", fill="x", padx=20, pady=(14, 6))
        hrow = tk.Frame(help_outer, bg=BG)
        hrow.pack(side="top", fill="x")
        tk.Label(hrow, text="功能说明", font=(FONT, 10, "bold"),
                 bg=BG, fg=ACCENT_TEXT).pack(side="left")
        tk.Label(hrow, text="·  将鼠标悬停在上方功能卡片上查看",
                 font=(FONT, 8), bg=BG, fg=MUTED).pack(side="left", padx=(8, 0))

        self.help_card = FluentCard(help_outer, radius=R_WIN, fill=CARD, border=BORDER)
        self.help_card.configure(height=112)
        self.help_card.pack(side="top", fill="x", pady=(6, 0))
        self.help_text = tk.Text(self.help_card.inner, height=1, wrap="word",
                                 font=(FONT, 9), bg=CARD, fg=TEXT, relief="flat",
                                 bd=0, padx=14, pady=10, spacing1=1,
                                 highlightthickness=0, cursor="arrow")
        self.help_text.pack(fill="both", expand=True)
        self.help_text.configure(state="disabled")
        # 注意用 add="+"：FluentCard 自身已绑定 Configure 做圆角重绘，不能覆盖
        self.help_card.bind("<Configure>", lambda e: self._fit_help_height(), add="+")
        self._set_help(DEFAULT_HELP)
        self.after(150, self._fit_help_height)

        # 日志区（仅此处用 expand=True 填充 bar 之上、help 之下的中间剩余空间）
        logf = tk.Frame(self, bg=BG)
        logf.pack(side="top", fill="both", expand=True, padx=20, pady=(8, 4))
        lh = tk.Frame(logf, bg=BG)
        lh.pack(side="top", fill="x")
        tk.Label(lh, text="运行日志", font=(FONT, 10, "bold"),
                 bg=BG, fg=ACCENT_TEXT).pack(side="left")
        self.status_var = tk.StringVar(value="就绪")
        tk.Label(lh, textvariable=self.status_var, font=(FONT, 9),
                 bg=BG, fg=SUBTEXT).pack(side="left", padx=10)
        FluentButton(lh, text="清空日志", kind="subtle", height=36, font_size=9,
                     padx=16,
                     command=lambda: (LOG.clear(), self.log_text.delete("1.0", "end"))
                     ).pack(side="right")

        self.log_card = FluentCard(logf, radius=R_WIN, fill=CARD, border=BORDER)
        self.log_card.pack(side="top", fill="both", expand=True, pady=(6, 0))
        self.log_text = tk.Text(self.log_card.inner, wrap="word", height=20,
                                font=(FONT, 9), bg=CARD, fg=TEXT,
                                relief="flat", bd=0, padx=12, pady=10,
                                spacing1=1, highlightthickness=0)
        sb = ttk.Scrollbar(self.log_card.inner, style="Card.Vertical.TScrollbar",
                           command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=sb.set)
        self.log_text.tag_config("OK", foreground=OKC)
        self.log_text.tag_config("WARN", foreground=WARNC)
        self.log_text.tag_config("ERROR", foreground=ERRC)
        self.log_text.tag_config("INFO", foreground=TEXT)
        sb.pack(side="right", fill="y")
        self.log_text.pack(side="left", fill="both", expand=True)

    def _make_button(self, parent, task: Task, idx: int):
        ok, reason = task.available()
        tile = FluentTile(parent, icon=task.icon, title=task.name,
                          subtitle="" if ok else reason,
                          command=lambda: self.run_task(task.key), height=88)
        tile.grid(row=idx // 3, column=idx % 3, sticky="nsew", padx=6, pady=6)
        parent.grid_rowconfigure(idx // 3, minsize=78)
        tile.set_enabled(ok, subtitle="" if ok else reason)

        # 说明文本样本：同时登记「可用」与「不可用」两种形态，
        # 取最长者作为说明区高度基准，避免切换状态时文字被截断
        self._help_samples.append(task.desc)
        self._help_samples.append(f"{task.desc}\n⛔ 当前不可用：{reason}")
        hover_text = task.desc if ok else f"{task.desc}\n⛔ 当前不可用：{reason}"
        # 绑定只读当前值，避免 refresh_tasks 反复 bind 造成处理器叠加
        tile._hover_text = hover_text
        # add="+"：磁贴内部已用 Enter/Leave 做悬停高亮，此处只能追加不能覆盖
        tile.bind("<Enter>", lambda e, w=tile: self._set_help(getattr(w, "_hover_text", "")),
                  add="+")
        tile.bind("<Leave>", lambda e: self._set_help(DEFAULT_HELP), add="+")
        task._card = tile
        task._btn = tile

    # ---------------- 说明区高度自适应 ---------------- #

    def _fit_help_height(self):
        """
        运行时按真实渲染结果计算说明区高度。
        做法：把每条候选说明临时灌入 Text，用 Tk 自己的换行结果
        （count(displaylines)）取最大显示行数，再用 dlineinfo 取真实行高。
        相比按字符宽度模拟换行，这是精确值 —— 不受 DPI、字体、词级换行规则影响。
        """
        if getattr(self, "_fitting", False):
            return
        try:
            w = self.help_card.winfo_width()
            if w <= 20:
                return
            self._fitting = True
            samples = list(self._help_samples) + [DEFAULT_HELP]
            prev = self.help_text.get("1.0", "end-1c")
            self.help_text.configure(state="normal")

            max_dl, line_h = 1, 0
            for s in samples:
                self.help_text.delete("1.0", "end")
                self.help_text.insert("1.0", s)
                self.help_text.update_idletasks()
                # 首行始终可见，用它取得真实行高（含 spacing1）
                if not line_h:
                    info = self.help_text.dlineinfo("1.0")
                    if info:
                        line_h = info[3]
                # 注意：tkinter 的 Text.count 在部分版本返回元组 (n,)，必须归一化为整数
                n = self.help_text.count("1.0", "end", "displaylines")
                if isinstance(n, (tuple, list)):
                    n = n[0] if n else 0
                n = int(n or 0)
                if n:
                    max_dl = max(max_dl, n)

            self.help_text.delete("1.0", "end")
            self.help_text.insert("1.0", prev)
            self.help_text.configure(state="disabled")

            if not line_h:
                line_h = tkfont.Font(family=FONT, size=9).metrics("linespace") + 1
            # 20 = Text 上下内边距各 10；6 = 安全余量
            need = int(math.ceil(max_dl * line_h)) + 20 + 6
            if need != self._help_h:
                self._help_h = need
                self.help_card.configure(height=need)
            # 宽度若相对上次测量发生变化，说明布局仍在收敛，下一帧再确认一次
            if w != getattr(self, "_help_w", None):
                self._help_w = w
                self.after(80, self._fit_help_height)
        except Exception:
            pass
        finally:
            self._fitting = False

    # ---------------- 任务调度 ---------------- #

    def _set_help(self, text: str):
        """写入功能说明（支持多行），并立即按当前实际宽度校准高度。"""
        self.help_text.configure(state="normal")
        self.help_text.delete("1.0", "end")
        self.help_text.insert("1.0", text)
        self.help_text.configure(state="disabled")
        # 每次写入都重新测量：此时布局已稳定，宽度一定是最新的，
        # 避免依赖 Configure 事件时序（Tk 分帧布局时首帧宽度可能是旧值）
        self._fit_help_height()

    def _set_busy(self, busy: bool, tip="就绪"):
        self._busy = busy
        self.status_var.set(tip)
        self.configure(cursor="watch" if busy else "")
        for t in self._tasks.values():
            ok, _ = t.available()
            if hasattr(t, "_btn"):
                t._btn.set_enabled((not busy) and ok)

    def run_task(self, key: str):
        if self._busy:
            return
        t = self._tasks[key]

        # Dism++ 走主线程引导模式（UIA 无法定位 DuiLib 自绘控件）
        if key == "dismpp":
            self._run_dismpp_guided(t)
            return

        def after(res):
            title, body = res
            if not ConfirmDialog(self, title, body).result:
                LOG.info(f"用户取消：{t.name}")
                return
            self._launch(lambda: t.run(), t.name)

        self._run_async(t.describe, after, f"正在扫描：{t.name}")

    def _run_dismpp_guided(self, t: Task):
        """Dism++ 特殊流程：启动程序 → 等待窗口 → 显示置顶引导窗 → 关闭。"""
        ok, reason = t.available()
        if not ok:
            messagebox.showwarning("不可用", reason, parent=self)
            return
        try:
            title, body = t.describe()
        except Exception as e:
            ErrorDialog(self, "无法执行", f"{type(e).__name__}: {e}", LOG.text())
            return
        if not ConfirmDialog(self, title, body).result:
            LOG.info(f"用户取消：{t.name}")
            return

        path = find_dismpp_path()
        self._set_busy(True, "正在执行：Dism++ 空间回收（请按引导窗操作）")
        LOG.info("=" * 60)
        LOG.info(f"任务开始：{t.name}")
        LOG.info(f"启动 Dism++: {path}")
        try:
            # CREATE_NEW_PROCESS_GROUP 让 Dism++ 与本进程解耦，避免 terminate 时误杀
            proc = subprocess.Popen(
                [path],
                creationflags=0x00000200,  # CREATE_NEW_PROCESS_GROUP
            )
        except Exception as e:
            LOG.error(f"启动失败: {e}")
            ErrorDialog(self, "启动失败", f"{type(e).__name__}: {e}", LOG.text())
            self._set_busy(False, "就绪")
            return

        # 轮询等待 Dism++ 主窗口出现（最多 10 秒，每 1 秒检查一次）
        # 比单纯 sleep 更鲁棒：Dism++ 启动慢时不会误判失败，启动快时也不浪费时间
        deadline = time.monotonic() + 10
        started = False
        while time.monotonic() < deadline:
            if _dismpp_window_exists():
                started = True
                break
            if proc.poll() is not None:
                break
            time.sleep(1)
        if not started:
            rc = proc.poll()
            if rc is None:
                rc = -1
            LOG.error(f"Dism++ 启动后未在 10 秒内出现主窗口（进程返回码 {rc}）")
            try: proc.terminate()
            except: pass
            ErrorDialog(self, "启动失败",
                        f"Dism++ 启动后未在 10 秒内出现主窗口。\n"
                        f"可能原因：\n"
                        f"  • 路径配置错误，请到「设置 → 路径设置」确认\n"
                        f"  • 被安全软件拦截，请暂时关闭杀毒软件后重试\n"
                        f"  • 缺少运行依赖（Visual C++ 运行库）",
                        LOG.text())
            self._set_busy(False, "就绪")
            return

        LOG.ok("Dism++ 已启动")
        if self._dismpp_guide_dismissed:
            # 用户此前已手动关闭过引导窗 → 尊重选择，本次不再弹出
            LOG.info("引导窗此前已被用户关闭，本次不再弹出（Dism++ 保持打开）")
        else:
            guide = DismPPGuide(self, proc)
            self.wait_window(guide)

        # 兜底关闭 Dism++：仅当用户未手动关闭引导窗时执行
        # （用户手动关闭意味着希望 Dism++ 继续运行自行操作）
        if not self._dismpp_guide_dismissed and proc.poll() is None:
            try: proc.terminate()
            except: pass

        LOG.ok("Dism++ 任务已结束")
        self._set_busy(False, "就绪")

    def _run_async(self, fn, on_done, tip: str):
        """在后台线程执行 fn，结果回到主线程后交给 on_done。"""
        self._set_busy(True, tip)

        def worker():
            try:
                res = (fn(), None)
            except Exception:
                res = (None, traceback.format_exc())
            self._q.put(("async", res, on_done))

        threading.Thread(target=worker, daemon=True).start()

    def run_all(self):
        if self._busy:
            return
        # 排除需要交互的任务（如 Dism++ 引导窗）
        todo = [t for t in self._tasks.values()
                if t.available()[0] and not getattr(t, "interactive", False)]
        if not todo:
            messagebox.showinfo("无可执行项", "当前没有可用的清理任务。", parent=self)
            return
        names = "\n".join(f"  • {t.name}" for t in todo)
        if not ConfirmDialog(self, "确认一键清理全部？",
                             f"将依次执行以下 {len(todo)} 个任务：\n\n{names}\n\n"
                             f"每个任务会单独统计结果，失败不影响后续任务。").result:
            LOG.info("用户取消：一键清理全部")
            return
        self._launch(lambda: [t.run() for t in todo], "一键清理全部")

    def _launch(self, fn, name: str):
        self._set_busy(True, f"正在执行：{name} …")
        LOG.info("=" * 60)
        LOG.info(f"任务开始：{name}")

        def worker():
            err = None
            try:
                fn()
            except Exception:
                err = traceback.format_exc()
            self._q.put(("done", name, err))

        threading.Thread(target=worker, daemon=True).start()

    # ---------------- 日志渲染 ---------------- #

    def _on_log(self, line: str, level: str = "INFO"):
        """向日志 Text 追加一条记录。主题切换重建期间 log_text 可能短暂失效，跳过即可。"""
        try:
            txt = getattr(self, "log_text", None)
            if not txt or not txt.winfo_exists():
                return
        except Exception:
            return
        try:
            txt.insert("end", line + "\n", level)
            txt.see("end")
        except Exception:
            pass

    def _drain(self):
        try:
            while True:
                item = self._q.get_nowait()
                if item[0] == "log":
                    _, line, lvl = item
                    # 主题切换重建 UI 时 log_text 可能短暂失效（已 destroy 或未创建），
                    # 用 _on_log 守护 —— 该函数会自动 skip
                    self._on_log(line, lvl)
                elif item[0] == "async":
                    _, res, on_done = item
                    val, err = res
                    self._set_busy(False, "就绪")
                    if err:
                        LOG.error("准备阶段失败")
                        ErrorDialog(self, "无法执行", err, LOG.text())
                    else:
                        on_done(val)
                elif item[0] == "done":
                    _, name, err = item
                    if err:
                        LOG.error(f"任务失败：{name}")
                        ErrorDialog(self, f"执行失败：{name}", err, LOG.text())
                    else:
                        LOG.ok(f"任务完成：{name}")
                    self._set_busy(False, "就绪")
        except queue.Empty:
            pass
        self.after(80, self._drain)

    # ---------------- 设置 / 退出 ---------------- #

    def open_settings(self):
        w = tk.Toplevel(self)
        w.title("设置")
        w.configure(bg=BG)
        w.geometry("820x680")
        w.minsize(720, 580)
        w.transient(self)
        w.grab_set()

        # 顶部说明（必须 wraplength，否则长句在窄窗口下被裁掉）
        tk.Label(w, text="可在此手动指定各应用路径，并切换主题。所有设置保存在注册表，不生成配置文件。",
                 font=(FONT, 9), bg=BG, fg=SUBTEXT, justify="left",
                 wraplength=740, anchor="w").pack(anchor="w", padx=20, pady=(16, 12))

        # ---- 外观：主题选择 ----
        theme_frame = tk.Frame(w, bg=BG)
        theme_frame.pack(side="top", fill="x", padx=20, pady=(0, 6))
        tk.Label(theme_frame, text="外观：", font=(FONT, 10, "bold"),
                 bg=BG, fg=TEXT).pack(side="left")
        current_theme = reg_get("theme", "") or _THEME_NAME
        if current_theme not in THEMES:
            current_theme = "dark"
        theme_var = tk.StringVar(value=current_theme)

        def select_theme(name: str):
            theme_var.set(name)
            # 用 set_kind 切换按钮高亮（accent = 选中），无需重建窗口
            dark_btn.set_kind("accent" if name == "dark" else "standard")
            light_btn.set_kind("accent" if name == "light" else "standard")

        dark_btn = FluentButton(theme_frame, text="🌙  深色", kind="standard",
                                height=40, font_size=10, padx=20)
        light_btn = FluentButton(theme_frame, text="☀  浅色", kind="standard",
                                 height=40, font_size=10, padx=20)
        # FluentButton 是 Canvas 控件，没有 configure(command=...) 选项，
        # 直接赋内部 _cmd 字段即可生效（_on_release 会调用它）
        dark_btn._cmd = lambda: select_theme("dark")
        light_btn._cmd = lambda: select_theme("light")
        dark_btn.pack(side="left", padx=(8, 4))
        light_btn.pack(side="left", padx=4)
        select_theme(current_theme)  # 初始化高亮

        # 分隔线
        tk.Frame(w, bg=BORDER, height=1).pack(side="top", fill="x", padx=20, pady=10)

        # ---- 路径设置 ----
        # 标题行：左侧标题，右侧「重新自动检测路径」按钮（移到这里的逻辑：
        #   这是它唯一能产生作用的地方 —— 重新扫描所有应用目录，调用方正是路径设置）
        title_row = tk.Frame(w, bg=BG)
        title_row.pack(side="top", fill="x", padx=20, pady=(0, 8))
        tk.Label(title_row, text="路径设置", font=(FONT, 10, "bold"),
                 bg=BG, fg=ACCENT_TEXT).pack(side="left")
        redo_btn = FluentButton(title_row, text="重新自动检测路径", kind="standard",
                                height=40, font_size=10, padx=20)
        redo_btn.pack(side="right")
        make_tooltip(redo_btn,
                     "放弃当前所有手动填写，重新按自动定位规则扫描各应用数据目录\n"
                     "（仅修改内存值，不会自动保存；点底部「保存」后才会写入注册表）")

        path_frame = tk.Frame(w, bg=BG)
        path_frame.pack(side="top", fill="both", expand=True, padx=20, pady=(0, 4))
        path_frame.columnconfigure(1, weight=1)
        entries: dict[str, tk.StringVar] = {}

        def _redetect_paths():
            """放弃所有手动填写，重新按 detect_root 自动定位，并刷新界面。
            不会自动保存 —— 用户仍需点底部「保存」才会写入注册表。"""
            n = 0
            for app, var in entries.items():
                if app == "dismpp":
                    auto = find_dismpp_path()
                else:
                    auto = detect_root(app)
                if auto:
                    var.set(auto)
                    n += 1
            LOG.info(f"重新自动检测路径：已刷新 {n} 项")

        redo_btn._cmd = _redetect_paths

        for i, (app, label) in enumerate(APP_LABEL.items()):
            tk.Label(path_frame, text=f"{label} 数据根目录：",
                     font=(FONT, 10), bg=BG, fg=TEXT
                     ).grid(row=i, column=0, sticky="w", pady=6)
            v = tk.StringVar(value=reg_get(f"{app}_root", "") or detect_root(app))
            e = tk.Entry(path_frame, textvariable=v, font=(FONT, 9), width=58,
                         relief="solid", bd=1)
            e.grid(row=i, column=1, sticky="ew", padx=8)
            FluentButton(path_frame, text="浏览", kind="standard", height=38,
                         font_size=10, padx=16,
                         command=lambda var=v: (
                             var.set(p) if (p := filedialog.askdirectory(parent=w)) else None)
                         ).grid(row=i, column=2)
            entries[app] = v

        # Dism++ 路径（文件选择）
        dis_row = len(APP_LABEL)
        tk.Label(path_frame, text="Dism++ 程序路径：",
                 font=(FONT, 10), bg=BG, fg=TEXT
                 ).grid(row=dis_row, column=0, sticky="w", pady=6)
        v = tk.StringVar(value=reg_get("dismpp_path", "") or find_dismpp_path())
        tk.Entry(path_frame, textvariable=v, font=(FONT, 9), width=58,
                 relief="solid", bd=1).grid(row=dis_row, column=1, sticky="ew", padx=8)
        FluentButton(path_frame, text="浏览", kind="standard", height=38,
                     font_size=10, padx=16,
                     command=lambda var=v: (var.set(p) if (p := filedialog.askopenfilename(
                         parent=w, title="选择 Dism++.exe",
                         filetypes=[("Dism++", "Dism++*.exe"),
                                    ("可执行文件", "*.exe")])) else None)
                     ).grid(row=dis_row, column=2)
        entries["dismpp"] = v

        # 提示文字（带 wraplength 防截断）
        hint1 = ("未检测到微信？手动填写形如  D:\\21654\\Documents\\xwechat_files  的目录。"
                 "留空则每次按自动定位重试。")
        hint2 = ("Dism++ 默认从图吧工具箱 202507 路径自动查找；找不到时手动指定 exe 路径。")
        tk.Label(path_frame, text=hint1, font=(FONT, 8), bg=BG, fg=SUBTEXT,
                 wraplength=580, justify="left", anchor="w"
                 ).grid(row=dis_row + 1, column=1, sticky="w", pady=(4, 0))
        tk.Label(path_frame, text=hint2, font=(FONT, 8), bg=BG, fg=SUBTEXT,
                 wraplength=580, justify="left", anchor="w"
                 ).grid(row=dis_row + 2, column=1, sticky="w", pady=(2, 0))

        def save():
            for app, var in entries.items():
                if app == "dismpp":
                    reg_set("dismpp_path", var.get().strip())
                else:
                    reg_set(f"{app}_root", var.get().strip())
            # 主题：写注册表 + 若有变化则立即应用
            new_theme = theme_var.get()
            reg_set("theme", new_theme)
            if new_theme != _THEME_NAME:
                apply_theme(new_theme)
            LOG.info("设置已保存")
            w.destroy()
            self.refresh_tasks()

        bar = tk.Frame(w, bg=BG, height=78)
        bar.pack(side="bottom", fill="x", padx=20, pady=(0, 14))
        bar.pack_propagate(False)
        FluentButton(bar, text="保存", kind="accent", height=44,
                     command=save).pack(side="right", padx=(10, 0))
        FluentButton(bar, text="取消", kind="standard", height=44,
                     command=w.destroy).pack(side="right")

    def refresh_tasks(self):
        self._help_samples = []
        for t in self._tasks.values():
            ok, reason = t.available()
            # 可用时不显示任何副文字（用户要求去掉「可用」字样）；不可用才显示原因
            sub = "" if ok else reason
            if hasattr(t, "_btn"):
                t._btn.set_enabled(ok, subtitle=sub)
                t._btn._hover_text = t.desc if ok else f"{t.desc}\n⛔ 当前不可用：{reason}"
            self._help_samples.append(t.desc)
            self._help_samples.append(f"{t.desc}\n⛔ 当前不可用：{reason}")
        # 状态文案行数可能变化，重新测量说明区高度
        self._help_h = 0
        self.after(50, self._fit_help_height)
        LOG.info("已重新检测各软件数据目录")

    def quit_app(self):
        LOG.info("正在退出，清理残留…")
        self.destroy()


# --------------------------------------------------------------------------- #
# 10. 启动入口
# --------------------------------------------------------------------------- #

def cleanup_self_residue():
    """退出时清理 PyInstaller onefile 的解压目录残留。"""
    try:
        d = getattr(sys, "_MEIPASS", "")
        if d and os.path.isdir(d):
            shutil.rmtree(d, ignore_errors=True)
    except Exception:
        pass


def main():
    set_dpi_aware()

    # 启动时根据注册表中上次保存的主题色板初始化（深色为默认）
    try:
        saved_theme = reg_get("theme", "") or "dark"
        if saved_theme in THEMES:
            set_theme(saved_theme)
    except Exception:
        pass

    # 启动即自动提权（--no-elevate 供开发调试使用）
    if "--no-elevate" not in sys.argv and "--elevated" not in sys.argv and not is_admin():
        if elevate():
            sys.exit(0)
        # 用户拒绝 UAC：以普通权限继续（功能会受限，日志中会体现）
        root = tk.Tk(); root.withdraw()
        messagebox.showwarning(
            "未获取管理员权限",
            "部分清理（系统文件、被占用临时文件）可能因权限不足而失败。\n"
            "建议重新运行并在 UAC 弹窗中点击「是」。")
        root.destroy()

    atexit.register(cleanup_self_residue)
    app = App()
    app.mainloop()
    cleanup_self_residue()


if __name__ == "__main__":
    main()
