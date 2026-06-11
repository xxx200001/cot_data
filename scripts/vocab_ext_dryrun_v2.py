"""
vocab_ext_dryrun_v2.py — 修复句中动词 bug + 五项返工
与 v1 对比, 只输出 delta(新增/移除)
"""
import json, glob, os, re, csv
from collections import defaultdict

ROOT = r"d:\微信文件\xwechat_files\wxid_mviguy0cna1m22_c0e5\msg\file\2026-06\cot_data\cot_data"
DATA = os.path.join(ROOT, "gemini_tasks_output_hm3d_atomic")
QA_OUT = os.path.join(ROOT, "qa_output")

def norm(s): return s.lower().strip().replace("_", " ")
def has_verb(step_text, verb):
    """全句词边界匹配, 不再锚定句首"""
    return bool(re.search(r'\b' + verb + r'\b', step_text, re.I))
def step_verb(s):
    m = re.match(r"^(\w+)\s", s)
    return m.group(1).lower() if m else ""

CANDLE_WL = {"candle", "candlestick", "candle holder", "candle_holder", "fireplace sconce"}
def is_candle(obj_norms):
    return any(any(kw in n for kw in CANDLE_WL) for n in obj_norms)

LIGHT_EXCLUDE = {"lamp", "flashlight", "light fixture", "ceiling light", "floor lamp",
    "table lamp", "desk lamp", "night light", "pendant light", "chandelier",
    "wall light", "sconce light", "fireplace", "hearth"}
def is_light_excluded(obj_norms):
    for n in obj_norms:
        if "fireplace" in n and "sconce" not in n: return True
        if "hearth" in n: return True
        if any(n == ex or n.startswith(ex + " ") or n.endswith(" " + ex) for ex in LIGHT_EXCLUDE if ex not in ("fireplace", "hearth")):
            return True
    return False

# 返工 #2: 加 washer-dryer
UNLOAD_WL = {"dishwasher", "washing machine", "washer", "dryer", "washer-dryer", "washer dryer", "washer_dryer"}
APPLIANCE_WL = {"kettle", "stove", "stovetop", "stove top", "oven", "oven and stove",
    "microwave oven", "microwave", "toaster oven", "toaster", "rice cooker", "cooker",
    "heater", "electric heater", "sauna heater", "sauna oven", "water heater",
    "furnace", "grill", "hot plate", "hotplate", "burner", "gas stove", "radiator"}

plan = []
stats = defaultdict(int)
f3_verdicts = []
# 返工 #5: 受事漂移修复
extra_fixes = []

files = sorted(glob.glob(os.path.join(DATA, "**", "*.json"), recursive=True))

for fpath in files:
    d = json.load(open(fpath, "r", encoding="utf-8"))
    rel_path = os.path.relpath(fpath, DATA)
    
    for tidx, task in enumerate(d.get("tasks", [])):
        for step in task.get("plan", []):
            orig = step.get("step", "")
            verb0 = step_verb(orig)  # 句首动词, 仅用于 R1/R3 等对象触发的规则
            at = step.get("atomic_step", "")
            objs = list(step.get("labels", {}).values())
            obj_norms = [norm(o) for o in objs]
            sid = step.get("step_id")
            
            for aa in step.get("atomic_actions", []):
                aid = aa["action_id"]
                ms = aa.get("mapping_source") or ""
                rel = aa.get("relation")
                if "vocab_extension_v1" in ms: continue
                
                # ============ R1: light (对象触发, 句首动词不相关) ============
                if aid == "turn_on" and is_candle(obj_norms) and not is_light_excluded(obj_norms):
                    new_at = at.replace("Turn on ", "Light ").replace("turn on ", "light ")
                    plan.append({"file": rel_path, "task_idx": tidx, "step_id": sid,
                        "rule": "R1_light", "old_action": aid, "new_action": "light",
                        "old_atomic_step": at, "new_atomic_step": new_at,
                        "relation_op": "no_change", "ms_op": "+vocab_extension_v1:turn_on->light; -vocab_gap:no_ignite_action",
                        "step_orig": orig[:80]})
                    stats["R1_light"] += 1
                
                # ============ R2: unload (全句匹配) ============
                if aid in ("open", "dump") and has_verb(orig, "unload"):
                    if any(any(kw in n for kw in UNLOAD_WL) for n in obj_norms):
                        m_patient = re.search(r'unload\s+(.*?)(?:\.|$)', orig, re.I)
                        if m_patient:
                            new_at = f"Unload {m_patient.group(1).strip().rstrip('.')}."
                        else:
                            new_at = at.replace("Open ", "Unload ").replace("Dump ", "Unload ")
                        plan.append({"file": rel_path, "task_idx": tidx, "step_id": sid,
                            "rule": "R2_unload", "old_action": aid, "new_action": "unload",
                            "old_atomic_step": at, "new_atomic_step": new_at,
                            "relation_op": "null_if_no_prep", "ms_op": f"+vocab_extension_v1:{aid}->unload",
                            "step_orig": orig[:80]})
                        stats["R2_unload"] += 1
                
                # ============ R3: iron (句首触发, 对象保护) ============
                if aid in ("straighten", "smooth", "store") and verb0 == "iron":
                    m_iron = re.match(r"iron\s+(.*)", orig, re.I)
                    if m_iron:
                        new_at = f"Iron {m_iron.group(1).rstrip('.')}."
                    else:
                        new_at = at.replace("Straighten ", "Iron ").replace("Smooth ", "Iron ")
                    rel_op = "no_change"
                    if any("ironing" in n or "iron board" in n for n in obj_norms):
                        if "on the" in new_at.lower() or "ironing" in new_at.lower():
                            rel_op = "set_on"
                    plan.append({"file": rel_path, "task_idx": tidx, "step_id": sid,
                        "rule": "R3_iron", "old_action": aid, "new_action": "iron",
                        "old_atomic_step": at, "new_atomic_step": new_at,
                        "relation_op": rel_op, "ms_op": f"+vocab_extension_v1:{aid}->iron",
                        "step_orig": orig[:80]})
                    stats["R3_iron"] += 1
                
                # ============ R4a: tune FLAG (全句匹配) ============
                if aid == "set_control" and has_verb(orig, "tune") and "vocab_gap:no_tune_action" not in ms:
                    plan.append({"file": rel_path, "task_idx": tidx, "step_id": sid,
                        "rule": "R4_tune_flag", "old_action": aid, "new_action": aid,
                        "old_atomic_step": at, "new_atomic_step": at,
                        "relation_op": "no_change", "ms_op": "+vocab_gap:no_tune_action",
                        "step_orig": orig[:80]})
                    stats["R4_tune_flag"] += 1
                
                # ============ R4b: roll FLAG (全句匹配) ============
                if has_verb(orig, "roll") and aid in ("carry", "smooth", "inspect", "straighten"):
                    if "vocab_gap:roll" not in ms:
                        plan.append({"file": rel_path, "task_idx": tidx, "step_id": sid,
                            "rule": "R4_roll_flag", "old_action": aid, "new_action": aid,
                            "old_atomic_step": at, "new_atomic_step": at,
                            "relation_op": "no_change", "ms_op": "+vocab_gap:roll",
                            "step_orig": orig[:80]})
                        stats["R4_roll_flag"] += 1
                
                # ============ R4c: 家电 FLAG 清理 ============
                if aid in ("turn_on", "turn_off") and "vocab_gap:" in ms:
                    is_app = any(any(kw in n for kw in APPLIANCE_WL) for n in obj_norms)
                    is_fp = any(("fireplace" in n and "sconce" not in n and "tool" not in n) or n == "hearth" for n in obj_norms)
                    is_fp_tool = any("fireplace tool" in n for n in obj_norms)
                    is_cndl = is_candle(obj_norms)
                    is_bath = any("bathtub" in n for n in obj_norms)
                    
                    if is_app and not is_cndl and not is_fp:
                        plan.append({"file": rel_path, "task_idx": tidx, "step_id": sid,
                            "rule": "R4_appliance_clean", "old_action": aid, "new_action": aid,
                            "old_atomic_step": at, "new_atomic_step": at,
                            "relation_op": "no_change",
                            "ms_op": "-vocab_gap:*; +idiom_ok:turn_on_appliance",
                            "step_orig": orig[:80]})
                        stats["R4_appliance_clean"] += 1
                    elif is_fp and not is_cndl:
                        plan.append({"file": rel_path, "task_idx": tidx, "step_id": sid,
                            "rule": "R4_fireplace_soft", "old_action": aid, "new_action": aid,
                            "old_atomic_step": at, "new_atomic_step": at,
                            "relation_op": "no_change",
                            "ms_op": "-vocab_gap:no_ignite_action; +assume_gas_fireplace",
                            "step_orig": orig[:80]})
                        stats["R4_fireplace_soft"] += 1
                    elif is_bath and "vocab_gap:no_faucet_action" in ms:
                        plan.append({"file": rel_path, "task_idx": tidx, "step_id": sid,
                            "rule": "R4_bathtub_clean", "old_action": aid, "new_action": aid,
                            "old_atomic_step": at, "new_atomic_step": at,
                            "relation_op": "no_change",
                            "ms_op": "-vocab_gap:no_faucet_action; +idiom_ok:turn_on_appliance",
                            "step_orig": orig[:80]})
                        stats["R4_bathtub_clean"] += 1
                
                # ============ F1: brew (全句匹配) ============
                if has_verb(orig, "brew") and aid == "inspect":
                    machine = [o for o in objs if any(k in norm(o) for k in ("coffee", "machine", "maker"))]
                    machine_name = machine[0] if machine else "coffee machine"
                    new_at = f"Start the {machine_name}."
                    plan.append({"file": rel_path, "task_idx": tidx, "step_id": sid,
                        "rule": "F1_brew_inspect", "old_action": aid, "new_action": "start_machine",
                        "old_atomic_step": at, "new_atomic_step": new_at,
                        "relation_op": "no_change",
                        "ms_op": "+vocab_extension_v1:inspect->start_machine",
                        "step_orig": orig[:80]})
                    stats["F1_brew_inspect"] += 1
                
                # ============ F2: warm (全句匹配) ============
                if has_verb(orig, "warm") and aid == "inspect":
                    device = [o for o in objs if any(k in norm(o) for k in ("toaster","oven","stove","microwave","grill","heater","kettle"))]
                    coffee = [o for o in objs if "coffee" in norm(o)]
                    blanket = [o for o in objs if any(k in norm(o) for k in ("blanket","throw","comforter"))]
                    exercise = [o for o in objs if any(k in norm(o) for k in ("treadmill","exercise","gym"))]
                    
                    if blanket:
                        new_aid = "cover"
                        dev_name = blanket[0]
                        new_at = f"Cover with the {dev_name}."
                    elif coffee:
                        new_aid = "start_machine"
                        dev_name = coffee[0]
                        new_at = f"Start the {dev_name}."
                    elif exercise:
                        new_aid = "turn_on"
                        dev_name = exercise[0]
                        new_at = f"Turn on the {dev_name}."
                    elif device:
                        new_aid = "turn_on"
                        dev_name = device[0]
                        new_at = f"Turn on the {dev_name}."
                    else:
                        dev_name = objs[0] if objs else "device"
                        new_aid = "turn_on"
                        new_at = f"Turn on the {dev_name}."
                    plan.append({"file": rel_path, "task_idx": tidx, "step_id": sid,
                        "rule": "F2_warm_inspect", "old_action": aid, "new_action": new_aid,
                        "old_atomic_step": at, "new_atomic_step": new_at,
                        "relation_op": "no_change",
                        "ms_op": f"+vocab_extension_v1:inspect->{new_aid}",
                        "step_orig": orig[:80]})
                    stats["F2_warm_inspect"] += 1
                
                # ============ F3: repair (全句匹配) ============
                if has_verb(orig, "repair") and aid in ("reposition", "turn_on"):
                    f3_verdicts.append({
                        "file": rel_path, "task_idx": tidx, "step_id": sid,
                        "old_action": aid, "atomic_step": at,
                        "step_orig": orig[:100], "objects": ", ".join(objs),
                    })
                    stats["F3_repair_pending"] += 1
            
            # ============ 返工 #5: 受事漂移 00891 t213 s6 ============
            if "00891" in rel_path and tidx == 213 and sid == 6:
                if at == "Store the box.":
                    extra_fixes.append({
                        "file": rel_path, "task_idx": tidx, "step_id": sid,
                        "rule": "EXTRA_patient_drift", "old_action": aid, "new_action": aid,
                        "old_atomic_step": at,
                        "new_atomic_step": "Store the iron in the storage box.",
                        "relation_op": "set_in", "ms_op": "+vocab_extension_v1:patient_drift_fix",
                        "step_orig": orig[:80]})
                    stats["EXTRA_patient_drift"] += 1

# 合并 extra_fixes 到 plan
plan.extend(extra_fixes)

# 保存
csv_path = os.path.join(QA_OUT, "vocab_ext_plan_v2.csv")
if plan:
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(plan[0].keys()))
        w.writeheader()
        w.writerows(plan)

f3_path = os.path.join(QA_OUT, "f3_repair_verdicts_v2.csv")
if f3_verdicts:
    with open(f3_path, "w", encoding="utf-8", newline="") as f:
        keys = list(f3_verdicts[0].keys())
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(f3_verdicts)

# 对照表
print("=" * 70)
print(f"{'Rule':<25} {'v2':<10} {'v1':<10} {'Delta':<10}")
print("-" * 70)
v1 = {"R1_light": 176, "R2_unload": 54, "R3_iron": 27, "R4_tune_flag": 13,
    "R4_roll_flag": 79, "R4_appliance_clean": 539, "R4_fireplace_soft": 549,
    "R4_bathtub_clean": 14, "F1_brew_inspect": 1, "F2_warm_inspect": 3, "F3_repair_pending": 69}
for rule in sorted(set(list(v1.keys()) + list(stats.keys()))):
    a = stats.get(rule, 0)
    b = v1.get(rule, 0)
    d = a - b
    marker = " ← CHANGED" if d != 0 else ""
    print(f"{rule:<25} {a:<10} {b:<10} {d:+d}{marker}")

print(f"\nTotal plan entries (inc F3 pending): {len(plan) + len(f3_verdicts)}")
print(f"Plan CSV: {csv_path}")
print(f"F3 CSV: {f3_path}")

# 打印 delta: 只打 v1→v2 新增的条目
print("\n=== DELTA: new entries in v2 (not in v1) ===")
for p in plan:
    rule = p["rule"]
    if rule in ("F1_brew_inspect", "F2_warm_inspect", "R2_unload", "EXTRA_patient_drift"):
        # 这些是 delta 候选
        print(f"  [{rule}] {p['step_orig'][:60]} | {p['old_action']}->{p['new_action']} | {p['new_atomic_step'][:50]}")
