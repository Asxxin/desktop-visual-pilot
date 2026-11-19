# -*- coding: utf-8 -*-
"""
desktop-visual-pilot · 环境自举（换电脑后第一步跑这个）

做三件事：
1) 剥代理拉起 windows-mcp 的 Python venv（含 PIL/win32gui/win32api/comtypes/numpy）
   本机 curl 坏 + 沙箱代理污染 pypi → 必须 env -u 剥掉 HTTP(S)_PROXY 并设 UV_NO_PROXY='*'
2) 找到该 venv 的 python.exe 路径，验证截图/窗口库可用
3) 确认 console 会话有真实桌面（能截到非黑屏画面）

用法：
  python bootstrap.py                       # 探测 + 报告
  python bootstrap.py --json                # 只输出 JSON（给 agent 解析）
  python bootstrap.py --install             # 若 venv 不存在则剥代理拉包

输出中的 PYTHON 路径就是后续 drive.py / session.py 要用的解释器。
"""

import sys, io, os, json, subprocess, glob, argparse
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

UVX = os.path.join(os.path.expanduser('~'), '.local', 'bin', 'uvx.exe')
UV = os.path.join(os.path.expanduser('~'), '.local', 'bin', 'uv.exe')
CACHE = os.path.join(os.environ.get('LOCALAPPDATA', ''), 'uv', 'cache', 'archive-v0')

STRIP_ENV = None
def strip_env():
    global STRIP_ENV
    if STRIP_ENV is not None:
        return STRIP_ENV
    e = dict(os.environ)
    for k in ['HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'http_proxy', 'https_proxy', 'all_proxy']:
        e.pop(k, None)
    e['UV_NO_PROXY'] = '*'; e['NO_PROXY'] = '*'
    STRIP_ENV = e
    return e

def find_venv_python():
    """在 uv cache 里找含 win32gui+PIL 的 python.exe。"""
    cands = []
    for d in glob.glob(os.path.join(CACHE, 'archive-v0', '*')) if False else glob.glob(os.path.join(CACHE, '*')):
        exe = os.path.join(d, 'Scripts', 'python.exe')
        if os.path.exists(exe):
            cands.append(exe)
    # 也认 archive-v0 直接父
    for d in glob.glob(os.path.join(os.environ.get('LOCALAPPDATA', ''), 'uv', 'cache', 'archive-v0', '*')):
        exe = os.path.join(d, 'Scripts', 'python.exe')
        if os.path.exists(exe) and exe not in cands:
            cands.append(exe)
    for exe in cands:
        try:
            r = subprocess.run([exe, '-c', 'import win32gui,win32api,PIL;print("OK")'],
                               capture_output=True, text=True, timeout=15)
            if 'OK' in r.stdout:
                return exe
        except Exception:
            continue
    return None

def install():
    if not os.path.exists(UVX):
        return {"ok": False, "error": "UVX_NOT_FOUND", "hint": "先装 uv: irm https://astral.sh/uv/install.ps1 | iex （用户本机会话执行）"}
    r = subprocess.run([UVX, '--from', 'windows-mcp', 'python', '-c',
                        'import win32gui,win32api,PIL,comtypes,numpy;print("OK")'],
                       env=strip_env(), capture_output=True, text=True, timeout=300)
    return {"ok": 'OK' in r.stdout, "stdout": r.stdout[-300:], "stderr": r.stderr[-300:]}

def probe(py):
    code = r'''
import sys,io
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding='utf-8',errors='replace')
import win32gui,win32con,win32api
from PIL import ImageGrab,ImageStat
img=ImageGrab.grab()
st=ImageStat.Stat(img.convert('RGB'))
wins=[]
def cb(h,_):
    if win32gui.IsWindowVisible(h):
        t=win32gui.GetWindowText(h)
        if t.strip(): wins.append(t[:50])
win32gui.EnumWindows(cb,None)
print("RESULT="+__import__('json').dumps({
 "screen":list(img.size),
 "mean":[round(x,1) for x in st.mean],
 "black":all(x<8 for x in st.mean),
 "visible_windows":len(wins),
 "sample":wins[:5]
},ensure_ascii=False))
'''
    r = subprocess.run([py, '-c', code], capture_output=True, text=True, timeout=30)
    line = [l for l in r.stdout.splitlines() if l.startswith('RESULT=')]
    if line:
        return json.loads(line[0][7:])
    return {"error": "PROBE_FAILED", "stdout": r.stdout[-300:], "stderr": r.stderr[-300:]}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--json', action='store_true')
    ap.add_argument('--install', action='store_true')
    a = ap.parse_args()

    out = {}
    if a.install:
        out['install'] = install()
    py = find_venv_python()
    out['python'] = py
    out['python_ok'] = bool(py)
    if py:
        out['probe'] = probe(py)
    out['uvx'] = UVX if os.path.exists(UVX) else None
    out['hint'] = ("可桌面自动化" if py and not out.get('probe', {}).get('black')
                   else "需先 --install 拉包，或当前非 console 会话")

    if a.json:
        print(json.dumps(out, ensure_ascii=False))
    else:
        print(json.dumps(out, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
