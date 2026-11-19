# -*- coding: utf-8 -*-
"""
desktop-visual-pilot · 验收判定

对一张真机截图做客观判定，避免"我觉得对了"的主观结论。
判定方式（可组合）：
  --expect-text   OCR 不可用时，用像素/人工看；此脚本不装 OCR，仅做图像客观指标
  --not-black     画面非黑（证明截到真实桌面而非 session0 黑屏）
  --min-windows    可见窗口数下限
  --template-diff  与基线截图比对差异像素比例（验证界面确实变化）

用法：
  python verify.py --shot after.png --not-black
  python verify.py --shot after.png --baseline before.png --template-diff 0.5
  python verify.py --shot after.png --expect-size 1920 1080

输出 JSON，agent 据此给用户 ✅/❌ 判定。
"""

import sys, io, os, json, argparse
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from PIL import Image, ImageChops, ImageStat

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--shot', required=True)
    p.add_argument('--baseline')
    p.add_argument('--not-black', action='store_true')
    p.add_argument('--template-diff', type=float, default=0, help='差异像素占比阈值 0-1')
    p.add_argument('--expect-size', nargs=2, type=int)
    a = p.parse_args()

    out = {"shot": a.shot, "checks": {}}
    img = Image.open(a.shot).convert('RGB')
    out['size'] = list(img.size)

    if a.not_black:
        st = ImageStat.Stat(img)
        mean = [round(x, 1) for x in st.mean]
        ok = not all(x < 8 for x in mean)
        out['checks']['not_black'] = {"pass": ok, "mean_rgb": mean}

    if a.expect_size:
        ok = list(img.size) == a.expect_size
        out['checks']['size'] = {"pass": ok, "expected": a.expect_size, "actual": list(img.size)}

    if a.baseline and a.template_diff > 0:
        base = Image.open(a.baseline).convert('RGB')
        if base.size != img.size:
            out['checks']['diff'] = {"pass": False, "error": "size_mismatch"}
        else:
            diff = ImageChops.difference(img, base).convert('L')
            hist = diff.histogram()
            changed = sum(hist[16:])  # 差异>16 视为变化
            ratio = changed / (img.size[0] * img.size[1])
            ok = ratio >= a.template_diff
            out['checks']['diff'] = {"pass": ok, "ratio": round(ratio, 4), "threshold": a.template_diff}

    out['all_pass'] = all(v.get('pass', False) for v in out['checks'].values()) if out['checks'] else None
    print(json.dumps(out, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
