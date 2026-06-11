"""
semantic_qa_v1_final.py — 按 txt.txt 的 531 行精确清单执行修复
分四类:
1. 漏网A:candle (164) → FLAG vocab_gap:no_ignite_action
2. 漏网A:guitar (65) → FLAG vocab_gap:no_tune_action  
3. 漏网B:rinse受事漂移 (13) → 修正 atomic_step + relation=in
4. 漏网B:vacuum受事漂移 (1) → 修正 atomic_step + relation=at
5. 误伤回滚:fluff→straighten (229) → 回滚为 fluff (v1脚本已做)
6. 改错回滚:set_timer (1) → 回滚为 set_control (v1脚本已做)
7. 建议优化:store→load (58) → store→load (v1脚本部分做了)

本脚本只处理 v1 脚本遗漏的: candle FLAG + rinse修正 + vacuum修正 + 剩余store→load
"""
import json, os, glob, csv, re
from collections import defaultdict

ROOT = r"d:\微信文件\xwechat_files\wxid_mviguy0cna1m22_c0e5\msg\file\2026-06\cot_data\cot_data"
DATA = os.path.join(ROOT, "gemini_tasks_output_hm3d_atomic")
QA_OUT = os.path.join(ROOT, "qa_output")
FIXLIST = r"d:\微信文件\xwechat_files\wxid_mviguy0cna1m22_c0e5\msg\file\2026-06\cot_data\txt.txt"

def norm(s): return s.lower().strip().replace("_", " ")
def has_tag(aa, tag): return tag in (aa.get("mapping_source") or "")
def add_tag(aa, tag):
    ms = aa.get("mapping_source") or ""
    if tag not in ms:
        aa["mapping_source"] = (ms + ";" + tag) if ms else tag

# 解析 fixlist CSV
import csv as csv_mod
fixes = []
with open(FIXLIST, "r", encoding="utf-8") as f:
    reader = csv_mod.DictReader(f)
    for row in reader:
        fixes.append(row)

print(f"Loaded {len(fixes)} fix entries from fixlist")

# 按类别统计
cats = defaultdict(list)
for fix in fixes:
    cat = fix["类别"].split(":")[0]
    cats[cat].append(fix)

for cat, items in sorted(cats.items()):
    print(f"  {cat}: {len(items)}")

# 按文件分组, 构建 (file, task_idx, step_id) → fix 的索引
fix_index = defaultdict(list)
for fix in fixes:
    key = (fix["file"], int(fix["task_idx"]), int(fix["step_id"]))
    fix_index[key].append(fix)

# 加载所有需要修改的文件
files_to_load = set(fix["file"] for fix in fixes)
data_cache = {}
for fname in files_to_load:
    fpath = os.path.join(DATA, fname)
    if os.path.exists(fpath):
        with open(fpath, "r", encoding="utf-8") as f:
            data_cache[fname] = json.load(f)

changes = []
modified_files = set()

for (fname, tidx, sid), fix_list in fix_index.items():
    if fname not in data_cache:
        print(f"  WARNING: file not found: {fname}")
        continue
    
    data = data_cache[fname]
    tasks = data.get("tasks", [])
    if tidx >= len(tasks):
        print(f"  WARNING: task_idx {tidx} out of range in {fname}")
        continue
    
    task = tasks[tidx]
    # 找 step by step_id
    step = None
    for s in task.get("plan", []):
        if s.get("step_id") == sid:
            step = s
            break
    if step is None:
        print(f"  WARNING: step_id {sid} not found in {fname} task {tidx}")
        continue
    
    for fix in fix_list:
        cat = fix["类别"]
        
        # ========================
        # 漏网A:turn_on+candle → FLAG
        # ========================
        if "turn_on+candle" in cat:
            for aa in step.get("atomic_actions", []):
                if aa["action_id"] == "turn_on" and not has_tag(aa, "vocab_gap:"):
                    add_tag(aa, "vocab_gap:no_ignite_action")
                    changes.append({"file": fname, "task_idx": tidx, "step_id": sid,
                        "type": "FLAG", "action": "turn_on", "tag": "vocab_gap:no_ignite_action"})
                    modified_files.add(fname)
        
        # ========================
        # 漏网A:set_control+guitar → FLAG
        # ========================
        elif "set_control+guitar" in cat:
            for aa in step.get("atomic_actions", []):
                if aa["action_id"] == "set_control" and not has_tag(aa, "vocab_gap:"):
                    add_tag(aa, "vocab_gap:no_tune_action")
                    changes.append({"file": fname, "task_idx": tidx, "step_id": sid,
                        "type": "FLAG", "action": "set_control", "tag": "vocab_gap:no_tune_action"})
                    modified_files.add(fname)
        
        # ========================
        # 漏网B:rinse受事漂移
        # ========================
        elif "rinse受事漂移" in cat:
            for aa in step.get("atomic_actions", []):
                if aa["action_id"] == "rinse" and not has_tag(aa, "semantic_qa_v1:fix_patient_drift"):
                    orig = step.get("step", "")
                    # 从 step 原文提取真正受事
                    m = re.search(r'(?:rinse|wash|clean)\s+(?:the\s+)?(\w+)', orig, re.I)
                    if m:
                        true_patient = m.group(1).lower()
                        if true_patient in ("dishwasher",):
                            # 特殊情况: "Wash the dishwasher" → 原文受事就是 dishwasher
                            # 这种情况可能是 "clean the dishwasher itself"
                            # 但清单明确说要改, 所以用 "dishes" 作为默认受事
                            true_patient = "dishes"
                        old_t = step["atomic_step"]
                        objs = list(step.get("labels", {}).values())
                        dw = [o for o in objs if "dishwasher" in norm(o)]
                        dw_name = dw[0] if dw else "dishwasher"
                        step["atomic_step"] = f"Rinse the {true_patient} in the {dw_name}."
                        aa["relation"] = "in"
                        add_tag(aa, "semantic_qa_v1:fix_patient_drift_rinse")
                        changes.append({"file": fname, "task_idx": tidx, "step_id": sid,
                            "type": "FIX_B", "old": old_t, "new": step["atomic_step"],
                            "reason": f"patient drift: {true_patient} is real patient"})
                        modified_files.add(fname)
        
        # ========================
        # 漏网B:vacuum受事漂移
        # ========================
        elif "vacuum受事漂移" in cat:
            for aa in step.get("atomic_actions", []):
                if aa["action_id"] == "vacuum" and not has_tag(aa, "semantic_qa_v1:fix_patient_drift"):
                    old_t = step["atomic_step"]
                    objs = list(step.get("labels", {}).values())
                    clock = [o for o in objs if "clock" in norm(o)]
                    clock_name = clock[0] if clock else "wall clock"
                    step["atomic_step"] = f"Vacuum the floor near the {clock_name}."
                    aa["relation"] = "at"
                    add_tag(aa, "semantic_qa_v1:fix_patient_drift_vacuum")
                    changes.append({"file": fname, "task_idx": tidx, "step_id": sid,
                        "type": "FIX_B", "old": old_t, "new": step["atomic_step"],
                        "reason": "patient drift: vacuum floor near clock, not the clock"})
                    modified_files.add(fname)
        
        # ========================
        # 建议优化:fill→store (改为 load)
        # ========================
        elif "建议优化:fill→store" in cat:
            for aa in step.get("atomic_actions", []):
                if aa["action_id"] == "store" and not has_tag(aa, "semantic_qa_v1:store-->load"):
                    old_t = step["atomic_step"]
                    aa["action_id"] = "load"
                    add_tag(aa, "semantic_qa_v1:store-->load")
                    step["atomic_step"] = step["atomic_step"].replace("Store ", "Load ").replace("store ", "load ").replace("Restock ", "Load ").replace("restock ", "load ")
                    changes.append({"file": fname, "task_idx": tidx, "step_id": sid,
                        "type": "FIX", "old_action": "store", "new_action": "load",
                        "old": old_t, "new": step["atomic_step"]})
                    modified_files.add(fname)
        
        # 误伤回滚 和 改错回滚 已被 v1 脚本处理, 跳过
        elif "误伤回滚" in cat or "改错回滚" in cat:
            pass  # Already handled by semantic_qa_v1.py

# 保存所有修改的文件
for fname in modified_files:
    fpath = os.path.join(DATA, fname)
    with open(fpath, "w", encoding="utf-8") as f:
        json.dump(data_cache[fname], f, ensure_ascii=False, indent=2)
        f.write("\n")

# 保存 changes
csv_path = os.path.join(QA_OUT, "changes_final.csv")
if changes:
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        keys = set()
        for c in changes:
            keys.update(c.keys())
        w = csv_mod.DictWriter(f, fieldnames=sorted(keys))
        w.writeheader()
        w.writerows(changes)

print(f"\nApplied: {len(changes)} changes across {len(modified_files)} files")
print(f"Changes log: {csv_path}")

# 验证
candle_unflagged = 0
guitar_unflagged = 0
rinse_dw = 0
store_tp = 0
for fname in data_cache:
    d = data_cache[fname]
    for t in d.get("tasks", []):
        for s in t.get("plan", []):
            objs = [v for v in s.get("labels", {}).values()]
            for aa in s.get("atomic_actions", []):
                if aa["action_id"] == "turn_on" and any("candle" in norm(o) for o in objs):
                    if "vocab_gap" not in (aa.get("mapping_source") or ""):
                        candle_unflagged += 1
                if aa["action_id"] == "set_control" and any("guitar" in norm(o) for o in objs):
                    if "vocab_gap" not in (aa.get("mapping_source") or ""):
                        guitar_unflagged += 1
                if aa["action_id"] == "rinse" and any("dishwasher" in norm(o) for o in objs):
                    if "semantic_qa_v1" not in (aa.get("mapping_source") or ""):
                        rinse_dw += 1
                if aa["action_id"] == "store" and any(x in norm(o) for o in objs for x in ["toilet paper","tissue","paper towel"]):
                    store_tp += 1

print(f"\nVerification (in affected files only):")
print(f"  Unflagged candle: {candle_unflagged}")
print(f"  Unflagged guitar: {guitar_unflagged}")
print(f"  Unfixed rinse+dw: {rinse_dw}")
print(f"  Remaining store+tp: {store_tp}")
