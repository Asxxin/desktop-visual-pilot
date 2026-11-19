# -*- coding: utf-8 -*-
"""
desktop-visual-pilot · 会话模式与步骤记录

两种模式：
  checkpoint（默认）：每个关键动作后停下 → 展示截图 → 等用户确认/改指令 → 再走下一步
  autopilot（全程授权）：连续执行不停顿，只在关键节点留截图，结束汇总

用法：
  python session.py init  --workdir <目录> [--mode checkpoint|autopilot]
  python session.py status --workdir <目录>
  python session.py mode   --workdir <目录> --mode autopilot|checkpoint
  python session.py step   --workdir <目录> --action "点击合同台账" --shot <截图路径> [--result ok]
  python session.py log    --workdir <目录>              # 打印全部步骤
  python session.py checkpoint --workdir <目录> --question "下一步是否继续？"

状态落盘到 <workdir>/.dvp_session.json，截图汇总在 <workdir>/dvp_shots/。
"""

import sys, io, os, json, time, argparse
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

STATE = '.dvp_session.json'

def state_path(workdir):
    return os.path.join(workdir, STATE)

def load(workdir):
    p = state_path(workdir)
    if not os.path.exists(p):
        return None
    return json.load(open(p, encoding='utf-8'))

def save(workdir, st):
    os.makedirs(workdir, exist_ok=True)
    json.dump(st, open(state_path(workdir), 'w', encoding='utf-8'), ensure_ascii=False, indent=2)

def jout(o):
    print(json.dumps(o, ensure_ascii=False, indent=2))

def main():
    p = argparse.ArgumentParser()
    p.add_argument('cmd', choices=['init', 'status', 'mode', 'step', 'log', 'checkpoint'])
    p.add_argument('--workdir', required=True)
    p.add_argument('--mode', choices=['checkpoint', 'autopilot'])
    p.add_argument('--action', default='')
    p.add_argument('--shot', default='')
    p.add_argument('--result', default='')
    p.add_argument('--question', default='')
    a = p.parse_args()

    os.makedirs(a.workdir, exist_ok=True)
    if a.cmd == 'init':
        st = load(a.workdir)
        if st:
            jout({"status": "already_exists", "mode": st['mode'], "workdir": a.workdir})
            return
        st = {
            "mode": a.mode or 'checkpoint',
            "started_at": time.strftime('%Y-%m-%d %H:%M:%S'),
            "goal": "",
            "steps": [],
            "shots_dir": os.path.join(a.workdir, 'dvp_shots')
        }
        os.makedirs(st['shots_dir'], exist_ok=True)
        save(a.workdir, st)
        jout({"status": "created", "mode": st['mode'], "workdir": a.workdir})
        return

    st = load(a.workdir)
    if not st:
        jout({"error": "NO_SESSION", "hint": "先运行 init"})
        sys.exit(1)

    if a.cmd == 'status':
        jout({"mode": st['mode'], "steps": len(st['steps']), "started_at": st['started_at'],
              "last": st['steps'][-1] if st['steps'] else None})
        return

    if a.cmd == 'mode':
        old = st['mode']
        st['mode'] = a.mode
        st.setdefault('mode_changes', []).append({
            "from": old, "to": a.mode, "at": time.strftime('%Y-%m-%d %H:%M:%S')
        })
        save(a.workdir, st)
        jout({"mode": st['mode'], "previous": old})
        return

    if a.cmd == 'step':
        rec = {
            "n": len(st['steps']) + 1,
            "at": time.strftime('%H:%M:%S'),
            "action": a.action,
            "result": a.result,
            "shot": a.shot
        }
        st['steps'].append(rec)
        save(a.workdir, st)
        jout({"recorded": rec, "mode": st['mode'],
              "next": "展示截图并等待确认" if st['mode'] == 'checkpoint' else "继续执行"})
        return

    if a.cmd == 'log':
        jout({"mode": st['mode'], "steps": st['steps']})
        return

    if a.cmd == 'checkpoint':
        rec = {
            "n": len(st['steps']) + 1,
            "at": time.strftime('%H:%M:%S'),
            "action": 'CHECKPOINT',
            "question": a.question,
            "awaiting": True
        }
        st['steps'].append(rec)
        save(a.workdir, st)
        jout({"checkpoint": a.question, "mode": st['mode'],
              "instruction": "停下，展示最近一张截图，等用户确认或改指令后再继续"})

if __name__ == '__main__':
    main()
