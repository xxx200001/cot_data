"""judge_unparsed.py — 对 148 条 unparsed 逐条判定"""
import csv, re, os
from collections import Counter

ROOT = r"d:\微信文件\xwechat_files\wxid_mviguy0cna1m22_c0e5\msg\file\2026-06\cot_data\cot_data"
QA = os.path.join(ROOT, "qa_output")

with open(os.path.join(QA, "g_unparsed.csv"), "r", encoding="utf-8-sig") as f:
    rows = list(csv.DictReader(f))

print(f"Total unparsed: {len(rows)}\n")

# 分类
cats = Counter()
verdicts = []

for r in rows:
    step = r["step"]
    at = r["atomic_step"]
    sl = step.lower().strip()
    al = at.lower().strip()
    
    verdict = None
    new_action = None
    new_text = None
    note = ""
    
    # 1. "Put on X" = 穿戴义 (wear/don) → 当前 place_on/store 不对, 但词表没 wear
    if re.match(r'^put on the \w+', sl) or re.match(r'^put on a \w+', sl):
        # "Put on the shoe/apron/backpack/handbag/robe/jewelry"
        obj = re.sub(r'^put on (the |a |an )?', '', sl).strip().rstrip('.')
        verdict = "G2_tidy"
        new_action = "straighten"
        new_text = f"Straighten the {obj}."
        note = "穿戴义无对应动作,降级straighten(整理)"
        cats["put_on_wear"] += 1
    
    # 2. "Put it/them in the X" = 代词受事 → 不可还原, 保持原样打FLAG
    elif re.match(r'^put (it|them) in (the|a) ', sl) or re.match(r'^place (it|them) in (the|a) ', sl):
        verdict = "FLAG"
        new_action = None
        new_text = None
        note = "代词受事无法还原"
        cats["pronoun_patient"] += 1
    
    # 3. "Set X to off/start/level" = 设备控制义 → set_control
    elif re.match(r'^set (the )?\w+.* to ', sl) or re.match(r'^set (the )?\w+.* to ', sl):
        verdict = "FLAG"
        note = "设备控制义,当前action可能已正确(set_control/turn_on)"
        cats["device_control"] += 1
    
    # 4. "Adjust X on/in Y" = 调整义 → straighten
    elif re.match(r'^adjust ', sl):
        obj_m = re.match(r'^adjust (the )?(.*?)( on | in | at ).*$', sl, re.I)
        if obj_m:
            obj = obj_m.group(2).strip()
            verdict = "G2_tidy"
            new_action = "straighten"
            new_text = f"Straighten the {obj}."
            note = "adjust=调整→straighten"
        else:
            obj_m2 = re.match(r'^adjust (the )?(.*?)\.?\s*$', sl, re.I)
            obj = obj_m2.group(2).strip() if obj_m2 else "?"
            verdict = "G2_tidy"
            new_action = "straighten"
            new_text = f"Straighten the {obj}."
            note = "adjust=调整→straighten"
        cats["adjust"] += 1
    
    # 5. "Neatly arrange X on/in Y" = G1 框架 (前缀副词导致解析失败)
    elif re.match(r'^neatly arrange ', sl):
        m = re.match(r'^neatly arrange (the )?(.*?) (on|in|into|onto) (the )?(.*?)\.?\s*$', sl, re.I)
        if m:
            obj = m.group(2).strip()
            prep = m.group(3)
            dest = m.group(5).strip()
            verdict = "G1_fix"
            new_action = "place_in" if prep in ("in","into") else "place_on"
            new_text = f"Place the {obj} {prep} the {dest}."
            note = f"副词前缀导致解析失败,手动G1"
        else:
            verdict = "FLAG"
            note = "neatly arrange 解析失败"
        cats["neatly_arrange"] += 1
    
    # 6. "Re-position X" = reposition (连字符导致解析失败)
    elif re.match(r'^re-position ', sl):
        obj_m = re.match(r'^re-position (the )?(.*?)\.?\s*$', sl, re.I)
        obj = obj_m.group(2).strip() if obj_m else "?"
        verdict = "G2_tidy"
        new_action = "reposition"
        new_text = f"Reposition the {obj}."
        note = "连字符导致解析失败"
        cats["re-position"] += 1
    
    # 7. "File in the cabinet" = store
    elif re.match(r'^file (in|into) ', sl):
        m = re.match(r'^file (in|into) (the )?(.*?)\.?\s*$', sl, re.I)
        dest = m.group(3).strip() if m else "cabinet"
        verdict = "G1_fix"
        new_action = "store"
        new_text = f"Store the files in the {dest}."
        note = "file=归档→store"
        cats["file_in"] += 1
    
    # 8. "Put in the X" (省略受事) → FLAG
    elif re.match(r'^put in the ', sl):
        verdict = "FLAG"
        note = "省略受事"
        cats["omitted_patient"] += 1
    
    # 9. "Fold X into/on Y" = fold 动词保真
    elif re.match(r'^fold ', sl):
        m = re.match(r'^fold (the )?(.*?) (in|into|on|onto) (the )?(.*?)\.?\s*$', sl, re.I)
        if m:
            obj = m.group(2).strip()
            prep = m.group(3)
            dest = m.group(5).strip()
            verdict = "G1_fix"
            new_action = "fold"
            new_text = f"Fold the {obj} {prep} the {dest}."
            note = "fold保真"
        else:
            verdict = "FLAG"
            note = "fold解析失败"
        cats["fold"] += 1
    
    # 10. "Repot the plant in X" → place_in
    elif re.match(r'^repot ', sl):
        m = re.match(r'^repot (the )?(.*?) (in|into) (the )?(.*?)\.?\s*$', sl, re.I)
        if m:
            obj = m.group(2).strip()
            dest = m.group(5).strip()
            verdict = "G1_fix"
            new_action = "place_in"
            new_text = f"Place the {obj} in the {dest}."
            note = "repot→place_in"
        else:
            verdict = "FLAG"
            note = "repot解析失败"
        cats["repot"] += 1
    
    # 11. "Serve on the tray" / "Place on X" (省略受事)
    elif re.match(r'^(serve|place) on ', sl):
        verdict = "FLAG"
        note = "省略受事"
        cats["omitted_patient"] += 1
    
    # 12. "Reorganize X in Y" → G1
    elif re.match(r'^reorganize ', sl):
        m = re.match(r'^reorganize (the )?(.*?) (in|on) (the )?(.*?)\.?\s*$', sl, re.I)
        if m:
            obj = m.group(2).strip()
            prep = m.group(3)
            dest = m.group(5).strip()
            verdict = "G1_fix"
            new_action = "place_in" if prep == "in" else "place_on"
            new_text = f"Place the {obj} {prep} the {dest}."
            note = "reorganize→place"
        else:
            verdict = "FLAG"
            note = "reorganize解析失败"
        cats["reorganize"] += 1
    
    # 13. "Refill X at Y" → fill 保真 (G4 漏网)
    elif re.match(r'^refill ', sl):
        m = re.match(r'^refill (the )?(.*?) at (the )?(.*?)\.?\s*$', sl, re.I)
        if m:
            obj = m.group(2).strip()
            dest = m.group(4).strip()
            verdict = "G1_fix"
            new_action = "fill"
            new_text = f"Fill the {obj} at the {dest}."
            note = "refill→fill"
        else:
            verdict = "FLAG"
            note = "refill解析失败"
        cats["refill"] += 1
    
    # 14. "Group/Gather/Sort/Align/Hide/Empty X into/on Y"
    elif re.match(r'^(group|gather|sort|align|hide|empty|update) ', sl):
        m = re.match(r'^(\w+) (the )?(.*?) (in|into|on|onto|from) (the )?(.*?)\.?\s*$', sl, re.I)
        if m:
            verb = m.group(1).lower()
            obj = m.group(3).strip()
            prep = m.group(4)
            dest = m.group(6).strip()
            if verb in ("align",):
                verdict = "G1_fix"; new_action = "align"
                new_text = f"Align the {obj} {prep} the {dest}."
            else:
                verdict = "G1_fix"
                new_action = "place_in" if prep in ("in","into") else "place_on"
                new_text = f"Place the {obj} {prep} the {dest}."
            note = f"{verb}→{new_action}"
        else:
            verdict = "FLAG"
            note = f"解析失败"
        cats["misc_verb"] += 1
    
    # 15. "Turn up the heat on X" → set_control/turn_on 语义, FLAG
    elif re.match(r'^turn ', sl):
        verdict = "FLAG"
        note = "设备控制义"
        cats["device_control"] += 1
    
    # 16. "Put on a record on the music player" / "Put on some soft music"
    elif "put on" in sl and ("music" in sl or "record" in sl):
        verdict = "FLAG"
        note = "播放音乐义,无对应动作"
        cats["play_music"] += 1
    
    # 17. "Position the exhibition panel in the next hall" → G1
    elif re.match(r'^position ', sl):
        m = re.match(r'^position (the )?(.*?) (in|on) (the )?(.*?)\.?\s*$', sl, re.I)
        if m:
            obj = m.group(2).strip()
            prep = m.group(3)
            dest = m.group(5).strip()
            verdict = "G1_fix"
            new_action = "place_in" if prep == "in" else "place_on"
            new_text = f"Place the {obj} {prep} the {dest}."
            note = "position→place"
        else:
            verdict = "FLAG"
            note = "position解析失败"
        cats["position"] += 1
    
    # Fallback
    if verdict is None:
        verdict = "FLAG"
        note = f"未分类: {sl[:40]}"
        cats["unclassified"] += 1
    
    verdicts.append({
        "file": r["file"], "task_idx": r["task_idx"], "step_id": r["step_id"],
        "step": step, "atomic_step": at,
        "verdict": verdict, "new_action": new_action or "",
        "new_text": new_text or "", "note": note
    })

# 统计
print("=== 分类统计 ===")
for k, v in cats.most_common():
    print(f"  {k}: {v}")

v_counter = Counter(v["verdict"] for v in verdicts)
print(f"\n=== Verdict 汇总 ===")
for k, v in v_counter.most_common():
    print(f"  {k}: {v}")

# 保存
out = os.path.join(QA, "g_unparsed_verdicts.csv")
with open(out, "w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(verdicts[0].keys()))
    w.writeheader()
    w.writerows(verdicts)
print(f"\nVerdicts saved to: {out}")

# 打印可修复的样本
print("\n=== G1_fix / G2_tidy 样本 ===")
for v in verdicts:
    if v["verdict"] in ("G1_fix", "G2_tidy"):
        print(f"  [{v['verdict']}] step: {v['step'][:55]}")
        print(f"    old: {v['atomic_step'][:55]}")
        print(f"    new: {v['new_text'][:55]} [{v['new_action']}]")
        print(f"    note: {v['note']}")
        print()
