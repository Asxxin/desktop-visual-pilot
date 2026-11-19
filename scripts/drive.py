# -*- coding: utf-8 -*-
"""
desktop-visual-pilot · 真机桌面驱动核心

不依赖 MCP，直接用 win32gui/win32api + PIL 驱动真机 Windows 桌面。
两种用法：

  A) 单命令模式（checkpoint 交互，推荐）——每次执行一个动作并截图：
     python drive.py shot  --out shot.png
     python drive.py windows
     python drive.py launch --exe "C:\\path\\app.exe"
     python drive.py focus  --title "项目工作台" --maximize
     python drive.py click  --x 120 --y 432 --out after_click.png
     python drive.py dblclick --x 120 --y 432 --out after.png
     python drive.py move   --x 500 --y 300
     python drive.py type   --text "hello"
     python drive.py key    --keys "ctrl,shift,esc"
     python drive.py scroll --x 600 --y 400 --clicks -3
     python drive.py drag   --x1 100 --y1 100 --x2 300 --y2 200 --out after.png
     python drive.py region --x 30 --y 180 --w 200 --h 300 --zoom 4 --out zoom.png

  B) 批处理模式——把动作写进 JSON 一次跑完（无需中途干预时）：
     python drive.py batch --file actions.json --outdir ./shots

设计原则（重要）：
- 每个动作后可选截图落盘；agent 在动作之间可停下来给用户看画面、接反馈。
- 所有输出为 JSON（stdout），便于 agent 解析。
- 窗口定位用 win32gui 枚举；坐标是屏幕物理像素（1920x1080 实机实测）。
- 无 uiautomation 依赖（windows-mcp venv 没装），坐标靠"截图→放大裁剪读字"精确定位。
"""

import sys, io, os, json, time, argparse, subprocess

# 统一 UTF-8 输出（Windows 控制台默认 GBK 会崩中文）
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

def _libs():
    import win32gui, win32con, win32api
    from PIL import ImageGrab, Image
    return win32gui, win32con, win32api, ImageGrab, Image

def jout(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=2))

# ---------- 窗口 ----------
def list_windows(filter_kw=None):
    wg = _libs()[0]
    rows = []
    def cb(h, _):
        if wg.IsWindowVisible(h):
            t = wg.GetWindowText(h); c = wg.GetClassName(h)
            if not t.strip():
                return
            if filter_kw and filter_kw not in t:
                return
            rows.append({"hwnd": h, "class": c, "title": t[:120]})
    wg.EnumWindows(cb, None)
    return rows

def find_window(title_kw):
    """按标题关键字找窗口，返回 hwnd。放宽匹配：包含即可。"""
    wg = _libs()[0]
    best = None
    def cb(h, _):
        nonlocal best
        if wg.IsWindowVisible(h):
            t = wg.GetWindowText(h)
            if title_kw and title_kw in t and wg.GetClassName(h) not in ('CabinetWClass', 'Progman'):
                best = (h, t)
    wg.EnumWindows(cb, None)
    return best

# ---------- 截图 ----------
def shot(out, region=None, zoom=1):
    ImageGrab, Image = _libs()[3], _libs()[4]
    img = ImageGrab.grab()
    if region:
        x, y, w, h = region
        img = img.crop((x, y, x + w, y + h))
        if zoom != 1:
            img = img.resize((w * zoom, h * zoom))
    if out:
        os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
        img.save(out)
    return {"out": out, "size": list(img.size)}

# ---------- 输入 ----------
def click(x, y, dbl=False, button='left'):
    wg, wc, wa = _libs()[0], _libs()[1], _libs()[2]
    wa.SetCursorPos((x, y)); time.sleep(0.12)
    down = wc.MOUSEEVENTF_LEFTDOWN if button == 'left' else wc.MOUSEEVENTF_RIGHTDOWN
    up = wc.MOUSEEVENTF_LEFTUP if button == 'left' else wc.MOUSEEVENTF_RIGHTUP
    n = 2 if dbl else 1
    for _ in range(n):
        wa.mouse_event(down, 0, 0, 0, 0); time.sleep(0.08)
        wa.mouse_event(up, 0, 0, 0, 0); time.sleep(0.08)
    return {"clicked": [x, y], "dbl": dbl, "button": button}

def move(x, y):
    _libs()[2].SetCursorPos((x, y)); time.sleep(0.1)
    return {"moved": [x, y]}

def drag(x1, y1, x2, y2):
    wa, wc = _libs()[2], _libs()[1]
    wa.SetCursorPos((x1, y1)); time.sleep(0.15)
    wa.mouse_event(wc.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0); time.sleep(0.15)
    # 分步移动，避免有些控件丢中间事件
    steps = 12
    for i in range(1, steps + 1):
        wa.SetCursorPos((x1 + (x2 - x1) * i // steps, y1 + (y2 - y1) * i // steps))
        time.sleep(0.03)
    time.sleep(0.15)
    wa.mouse_event(wc.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
    return {"drag": [x1, y1, x2, y2]}

def scroll(x, y, clicks):
    wa, wc = _libs()[2], _libs()[1]
    wa.SetCursorPos((x, y)); time.sleep(0.1)
    wa.mouse_event(wc.MOUSEEVENTF_WHEEL, 0, 0, clicks * 120, 0)
    return {"scrolled": [x, y, clicks]}

def type_text(text):
    """用剪贴板粘贴（支持中文/特殊字符），避免 SendInput 逐字符对中文失效。"""
    wa, wc = _libs()[2], _libs()[1]
    import win32clipboard
    win32clipboard.OpenClipboard(); win32clipboard.EmptyClipboard()
    win32clipboard.SetClipboardData(win32clipboard.CF_UNICODETEXT, text)
    win32clipboard.CloseClipboard()
    wa.keybd_event(0x11, 0x1D, wc.KEYEVENTF_KEYUP, 0)  # 松开可能的 ctrl
    wa.keybd_event(0x11, 0x1D, 0, 0)  # ctrl down
    wa.keybd_event(0x56, 0x2F, 0, 0)  # V down
    wa.keybd_event(0x56, 0x2F, wc.KEYEVENTF_KEYUP, 0)
    wa.keybd_event(0x11, 0x1D, wc.KEYEVENTF_KEYUP, 0)
    return {"typed": text}

def key(keys):
    """组合键：逗号分隔，如 ctrl,shift,esc / enter / alt,f4。"""
    wc, wa = _libs()[1], _libs()[2]
    VK = {
        'ctrl': 0x11, 'shift': 0x10, 'alt': 0x12, 'enter': 0x0D, 'esc': 0x1B,
        'tab': 0x09, 'backspace': 0x08, 'delete': 0x2E, 'space': 0x20,
        'home': 0x24, 'end': 0x23, 'up': 0x26, 'down': 0x28, 'left': 0x25, 'right': 0x27,
        'f1': 0x70, 'f2': 0x71, 'f5': 0x74, 'f11': 0x7A, 'f12': 0x7B,
    }
    seq = [k.strip().lower() for k in keys.split(',') if k.strip()]
    codes = [VK.get(k, ord(k.upper()) if len(k) == 1 else None) for k in seq]
    codes = [c for c in codes if c is not None]
    for c in codes:
        wa.keybd_event(c, 0, 0, 0)
    time.sleep(0.05)
    for c in reversed(codes):
        wa.keybd_event(c, 0, wc.KEYEVENTF_KEYUP, 0)
    return {"keys": seq, "codes": codes}

def focus(title_kw, maximize=False):
    wg, wc = _libs()[0], _libs()[1]
    found = find_window(title_kw)
    if not found:
        return {"ok": False, "error": "WINDOW_NOT_FOUND", "kw": title_kw}
    h, t = found
    if maximize:
        wg.ShowWindow(h, wc.SW_MAXIMIZE)
    else:
        wg.ShowWindow(h, wc.SW_RESTORE)
    time.sleep(0.4)
    try:
        wg.SetForegroundWindow(h)
    except Exception as e:
        return {"ok": True, "hwnd": h, "title": t, "fg_warn": str(e)}
    time.sleep(0.5)
    return {"ok": True, "hwnd": h, "title": t, "foreground": wg.GetForegroundWindow()}

def launch(exe, wait=12, title_kw=None, maximize=False):
    """启动 EXE 并等待窗口出现。
    注意：沙箱会随脚本退出清理子进程 → 用 launch 后，后续动作要在同一会话连续执行；
    或目标程序本身开机自启常驻。"""
    subprocess.Popen([exe], shell=False)
    kw = title_kw or os.path.splitext(os.path.basename(exe))[0]
    found = None
    for i in range(wait):
        found = find_window(kw)
        if found:
            break
        time.sleep(1)
    if not found:
        return {"ok": False, "error": "WINDOW_NOT_FOUND_AFTER_LAUNCH", "kw": kw, "exe": exe}
    h, t = found
    if maximize:
        wg, wc = _libs()[0], _libs()[1]
        wg.ShowWindow(h, wc.SW_MAXIMIZE); time.sleep(0.4)
        try: wg.SetForegroundWindow(h)
        except Exception: pass
    return {"ok": True, "pid_window_hwnd": h, "title": t, "wait_sec": i, "maximized": maximize}

# ---------- dispatch ----------
def do(action, a):
    if action == 'windows':
        return {"windows": list_windows(a.get('filter'))}
    if action == 'shot':
        # argparse 未提供时值为 None；四个坐标都给了才算区域截图
        if all(a.get(k) is not None for k in ('x', 'y', 'w', 'h')):
            reg = (a['x'], a['y'], a['w'], a['h'])
        else:
            reg = None
        return shot(a.get('out'), reg, a.get('zoom', 1))
    if action == 'region':
        return shot(a.get('out'), (a['x'], a['y'], a['w'], a['h']), a.get('zoom', 1))
    if action == 'launch':
        return launch(a['exe'], a.get('wait', 12), a.get('title_kw'), a.get('maximize', False))
    if action == 'focus':
        return focus(a['title'], a.get('maximize', False))
    if action == 'click':
        r = click(a['x'], a['y'], a.get('dbl', False), a.get('button', 'left'))
        if a.get('wait'): time.sleep(a['wait'])
        if a.get('out'): r.update(shot(a['out']))
        return r
    if action == 'dblclick':
        r = click(a['x'], a['y'], True, a.get('button', 'left'))
        if a.get('wait'): time.sleep(a['wait'])
        if a.get('out'): r.update(shot(a['out']))
        return r
    if action == 'move':
        return move(a['x'], a['y'])
    if action == 'drag':
        r = drag(a['x1'], a['y1'], a['x2'], a['y2'])
        if a.get('out'): r.update(shot(a['out']))
        return r
    if action == 'scroll':
        r = scroll(a['x'], a['y'], a['clicks'])
        if a.get('wait'): time.sleep(a['wait'])
        if a.get('out'): r.update(shot(a['out']))
        return r
    if action == 'type':
        return type_text(a['text'])
    if action == 'key':
        r = key(a['keys'])
        if a.get('wait'): time.sleep(a['wait'])
        if a.get('out'): r.update(shot(a['out']))
        return r
    if action == 'batch':
        return run_batch(a['file'], a.get('outdir', '.'))
    return {"error": "UNKNOWN_ACTION", "action": action}

def run_batch(path, outdir):
    cfg = json.load(open(path, encoding='utf-8'))
    os.makedirs(outdir, exist_ok=True)
    results = []
    for i, step in enumerate(cfg.get('steps', [])):
        act = step.get('action'); args = dict(step)
        args.pop('action', None)
        args.pop('note', None)
        if 'out' in args and not os.path.isabs(args['out']):
            args['out'] = os.path.join(outdir, args['out'])
        try:
            r = do(act, args)
            r['step'] = i + 1
            r['note'] = step.get('note', '')
            results.append(r)
        except Exception as e:
            results.append({"step": i + 1, "action": act, "error": str(e)})
        if step.get('sleep'):
            time.sleep(step['sleep'])
    return {"batch": True, "count": len(results), "results": results}

def main():
    p = argparse.ArgumentParser(description='desktop-visual-pilot 真机驱动')
    p.add_argument('action', help='动作名，见文件顶部说明')
    p.add_argument('--out', help='截图输出路径')
    p.add_argument('--file', help='batch 动作 JSON 文件')
    p.add_argument('--outdir', default='.', help='batch 截图目录')
    p.add_argument('--exe', help='launch 目标 exe')
    p.add_argument('--title_kw', help='launch 时窗口标题关键字')
    p.add_argument('--title', help='focus 窗口标题关键字')
    p.add_argument('--wait', type=float, help='等待秒数')
    p.add_argument('--maximize', action='store_true')
    p.add_argument('--x', type=int); p.add_argument('--y', type=int)
    p.add_argument('--x1', type=int); p.add_argument('--y1', type=int)
    p.add_argument('--x2', type=int); p.add_argument('--y2', type=int)
    p.add_argument('--w', type=int); p.add_argument('--h', type=int)
    p.add_argument('--zoom', type=int, default=1)
    p.add_argument('--dbl', action='store_true')
    p.add_argument('--button', default='left', choices=['left', 'right'])
    p.add_argument('--clicks', type=int, default=0)
    p.add_argument('--text', help='type 的文本')
    p.add_argument('--keys', help='key 组合键，逗号分隔')
    p.add_argument('--filter', help='windows 标题过滤关键字')
    a = p.parse_args()
    try:
        r = do(a.action, vars(a))
        jout(r)
    except Exception as e:
        jout({"error": "EXCEPTION", "action": a.action, "msg": str(e)})
        sys.exit(1)

if __name__ == '__main__':
    main()
