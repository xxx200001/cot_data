"""补丁: 修复 v1 脚本的匹配遗漏"""
import json, glob, os, csv, re
from datetime import datetime

ROOT = r"d:\微信文件\xwechat_files\wxid_mviguy0cna1m22_c0e5\msg\file\2026-06\cot_data\cot_data"
DATA = os.path.join(ROOT, "gemini_tasks_output_hm3d_atomic")
QA_OUT = os.path.join(ROOT, "qa_output")

def norm(s): return s.lower().strip().replace("_", " ")
def has_tag(aa, tag): return tag in (aa.get("mapping_source") or "")
def add_tag(aa, tag):
    ms = aa.get("mapping_source") or ""
    if tag not in ms:
        aa["mapping_source"] = (ms + ";" + tag) if ms else tag

changes = []
def record(fpath, scene, tidx, sid, etype, old_a, new_a, old_t, new_t, reason):
    changes.append({"file": os.path.relpath(fpath, DATA), "scene_id": scene,
        "task_idx": tidx, "step_id": sid, "error_type": etype,
        "old_action": old_a, "new_action": new_a,
        "old_atomic_step": old_t, "new_atomic_step": new_t, "reason": reason})

files = sorted(glob.glob(os.path.join(DATA, "**", "*.json"), recursive=True))

for fpath in files:
    with open(fpath, "r", encoding="utf-8") as f:
        data = json.load(f)
    modified = False
    scene = data.get("scene_id", "")
    
    for tidx, task in enumerate(data.get("tasks", [])):
        for step in task.get("plan", []):
            objs = list(step.get("labels", {}).values())
            orig_step = step.get("step", "")
            
            for aa in step.get("atomic_actions", []):
                aid = aa["action_id"]
                
                # 1. FLAG candle: turn_on + candle/candlestick/candle_holder
                if aid == "turn_on" and not has_tag(aa, "vocab_gap:"):
                    for obj in objs:
                        if "candle" in norm(obj):
                            add_tag(aa, "vocab_gap:no_ignite_action")
                            modified = True
                            break
                
                # 2. FIX rinse+dishwasher: broader match
                if aid == "rinse" and not has_tag(aa, "semantic_qa_v1:fix_patient_drift"):
                    for obj in objs:
                        if "dishwasher" in norm(obj):
                            # 从 atomic_step 检查受事是否是 dishwasher
                            at = step.get("atomic_step", "")
                            if "dishwasher" in at.lower():
                                # 从 step 原文提取真正受事
                                # 模式: "Rinse the X", "Wash the X in the dishwasher"
                                m = re.search(r'(?:rinse|wash|clean)\s+(?:the\s+)?(\w+)', orig_step, re.I)
                                if m:
                                    true_patient = m.group(1).lower()
                                    if true_patient not in ("dishwasher",):
                                        old_t = step["atomic_step"]
                                        step["atomic_step"] = f"Rinse the {true_patient} in the {obj}."
                                        aa["relation"] = "in"
                                        add_tag(aa, "semantic_qa_v1:fix_patient_drift_rinse")
                                        record(fpath, scene, tidx, step["step_id"], "B",
                                               "rinse", "rinse", old_t, step["atomic_step"],
                                               f"Patient drift: '{true_patient}' is the real patient")
                                        modified = True
                                        break
                
                # 3. FIX remaining store→load (toilet paper etc)
                if aid == "store":
                    for obj in objs:
                        if any(t in norm(obj) for t in ["toilet paper", "tissue", "paper towel"]):
                            old_t = step["atomic_step"]
                            aa["action_id"] = "load"
                            add_tag(aa, "semantic_qa_v1:store-->load")
                            step["atomic_step"] = step["atomic_step"].replace("Store ", "Load ").replace("store ", "load ").replace("Restock ", "Load ").replace("restock ", "load ")
                            record(fpath, scene, tidx, step["step_id"], "FIX",
                                   "store", "load", old_t, step["atomic_step"],
                                   f"store偏离refill意图; load更贴合补装{obj}")
                            modified = True
                            break
    
    if modified:
        with open(fpath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")

# Append to changes.csv
csv_path = os.path.join(QA_OUT, "changes_patch.csv")
if changes:
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(changes[0].keys()))
        w.writeheader()
        w.writerows(changes)

print(f"Patch applied: {len(changes)} additional changes")

# Verify remaining
candle=0; rinse_dw=0; store_tp=0
for fpath in files:
    d=json.load(open(fpath,'r',encoding='utf-8'))
    for t in d.get('tasks',[]):
        for s in t.get('plan',[]):
            objs=[v for v in s.get('labels',{}).values()]
            for aa in s.get('atomic_actions',[]):
                aid=aa['action_id']
                for obj in objs:
                    nn=norm(obj)
                    if aid=='turn_on' and 'candle' in nn and 'vocab_gap' not in (aa.get('mapping_source') or ''): candle+=1
                    if aid=='rinse' and 'dishwasher' in nn and 'semantic_qa_v1' not in (aa.get('mapping_source') or ''): rinse_dw+=1
                    if aid=='store' and any(x in nn for x in ['toilet paper','tissue','paper towel']): store_tp+=1
print(f"Remaining: candle={candle} rinse_dw={rinse_dw} store_tp={store_tp}")
