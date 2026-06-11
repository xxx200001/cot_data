"""
vocab_ext_dryrun.py — 干跑: 只产出 plan.csv, 不写数据
规则: R1(light), R2(unload), R3(iron), R4(FLAG), F1-F3(错映射修复)
"""
import json, glob, os, re, csv
from collections import defaultdict

ROOT = r"d:\微信文件\xwechat_files\wxid_mviguy0cna1m22_c0e5\msg\file\2026-06\cot_data\cot_data"
DATA = os.path.join(ROOT, "gemini_tasks_output_hm3d_atomic")
QA_OUT = os.path.join(ROOT, "qa_output")
os.makedirs(QA_OUT, exist_ok=True)

def norm(s): return s.lower().strip().replace("_", " ")
def step_verb(s):
    m = re.match(r"^(\w+)\s", s)
    return m.group(1).lower() if m else ""
def has_tag(aa, tag): return tag in (aa.get("mapping_source") or "")

# === 白名单/黑名单 ===
CANDLE_WL = {"candle", "candlestick", "candle holder", "candle_holder", "fireplace sconce"}
def is_candle(obj_norms):
    return any(any(kw in n for kw in CANDLE_WL) for n in obj_norms)

LIGHT_EXCLUDE = {"lamp", "flashlight", "light fixture", "ceiling light", "floor lamp",
    "table lamp", "desk lamp", "night light", "pendant light", "chandelier",
    "wall light", "sconce light", "fireplace", "hearth"}
def is_light_excluded(obj_norms):
    for n in obj_norms:
        if "fireplace" in n and "sconce" not in n:
            return True
        if "hearth" in n:
            return True
        if any(n == ex or n.startswith(ex + " ") or n.endswith(" " + ex) for ex in LIGHT_EXCLUDE if ex not in ("fireplace", "hearth")):
            return True
    return False

UNLOAD_WL = {"dishwasher", "washing machine", "washer", "dryer", "washer-dryer", "washer dryer"}
APPLIANCE_WL = {"kettle", "stove", "stovetop", "stove top", "oven", "oven and stove",
    "microwave oven", "microwave", "toaster oven", "toaster", "rice cooker", "cooker",
    "heater", "electric heater", "sauna heater", "sauna oven", "water heater",
    "furnace", "grill", "hot plate", "hotplate", "burner", "gas stove", "radiator"}
FIREPLACE_WL = {"fireplace", "hearth"}

plan = []
stats = defaultdict(int)
f3_verdicts = []

files = sorted(glob.glob(os.path.join(DATA, "**", "*.json"), recursive=True))

for fpath in files:
    d = json.load(open(fpath, "r", encoding="utf-8"))
    rel_path = os.path.relpath(fpath, DATA)
    
    for tidx, task in enumerate(d.get("tasks", [])):
        for step in task.get("plan", []):
            orig = step.get("step", "")
            verb = step_verb(orig)
            at = step.get("atomic_step", "")
            objs = list(step.get("labels", {}).values())
            obj_norms = [norm(o) for o in objs]
            sid = step.get("step_id")
            
            for aa in step.get("atomic_actions", []):
                aid = aa["action_id"]
                ms = aa.get("mapping_source") or ""
                rel = aa.get("relation")
                
                # Skip already processed
                if "vocab_extension_v1" in ms:
                    continue
                
                # ============ R1: light ============
                if aid == "turn_on" and is_candle(obj_norms) and not is_light_excluded(obj_norms):
                    new_at = at.replace("Turn on ", "Light ").replace("turn on ", "light ")
                    plan.append({"file": rel_path, "task_idx": tidx, "step_id": sid,
                        "rule": "R1_light", "old_action": aid, "new_action": "light",
                        "old_atomic_step": at, "new_atomic_step": new_at,
                        "relation_op": "no_change", "ms_op": "+vocab_extension_v1:turn_on->light; -vocab_gap:no_ignite_action",
                        "step_orig": orig[:80]})
                    stats["R1_light"] += 1
                
                # ============ R2: unload ============
                if aid in ("open", "dump") and verb == "unload":
                    if any(any(kw in n for kw in UNLOAD_WL) for n in obj_norms):
                        # 从 step 原文提取完整意图
                        m_patient = re.match(r"unload\s+(.*)", orig, re.I)
                        if m_patient:
                            new_at = f"Unload {m_patient.group(1).rstrip('.')}."
                        else:
                            new_at = at.replace("Open ", "Unload ").replace("Dump ", "Unload ")
                        plan.append({"file": rel_path, "task_idx": tidx, "step_id": sid,
                            "rule": "R2_unload", "old_action": aid, "new_action": "unload",
                            "old_atomic_step": at, "new_atomic_step": new_at,
                            "relation_op": "null_if_no_prep", "ms_op": f"+vocab_extension_v1:{aid}->unload",
                            "step_orig": orig[:80]})
                        stats["R2_unload"] += 1
                
                # ============ R3: iron ============
                if aid in ("straighten", "smooth", "store") and verb == "iron":
                    # 从 step 原文重写
                    m_iron = re.match(r"iron\s+(.*)", orig, re.I)
                    if m_iron:
                        new_at = f"Iron {m_iron.group(1).rstrip('.')}."
                    else:
                        new_at = at.replace("Straighten ", "Iron ").replace("Smooth ", "Iron ")
                    new_rel = rel
                    rel_op = "no_change"
                    # 检查是否有 ironing board 作为处所
                    if any("ironing" in n or "iron board" in n for n in obj_norms):
                        if "on the" in new_at.lower() or "ironing" in new_at.lower():
                            new_rel = "on"
                            rel_op = "set_on"
                    plan.append({"file": rel_path, "task_idx": tidx, "step_id": sid,
                        "rule": "R3_iron", "old_action": aid, "new_action": "iron",
                        "old_atomic_step": at, "new_atomic_step": new_at,
                        "relation_op": rel_op, "ms_op": f"+vocab_extension_v1:{aid}->iron",
                        "step_orig": orig[:80]})
                    stats["R3_iron"] += 1
                
                # ============ R4a: tune FLAG 补齐 ============
                if aid == "set_control" and verb == "tune" and "vocab_gap:no_tune_action" not in ms:
                    plan.append({"file": rel_path, "task_idx": tidx, "step_id": sid,
                        "rule": "R4_tune_flag", "old_action": aid, "new_action": aid,
                        "old_atomic_step": at, "new_atomic_step": at,
                        "relation_op": "no_change", "ms_op": "+vocab_gap:no_tune_action",
                        "step_orig": orig[:80]})
                    stats["R4_tune_flag"] += 1
                
                # ============ R4b: roll FLAG ============
                if verb == "roll" and aid in ("carry", "smooth", "inspect", "straighten"):
                    if "vocab_gap:roll" not in ms:
                        plan.append({"file": rel_path, "task_idx": tidx, "step_id": sid,
                            "rule": "R4_roll_flag", "old_action": aid, "new_action": aid,
                            "old_atomic_step": at, "new_atomic_step": at,
                            "relation_op": "no_change", "ms_op": "+vocab_gap:roll",
                            "step_orig": orig[:80]})
                        stats["R4_roll_flag"] += 1
                
                # ============ R4c: 家电 FLAG 清理 ============
                if aid in ("turn_on", "turn_off") and "vocab_gap:" in ms:
                    # 判断物体类别
                    is_appliance = any(any(kw in n for kw in APPLIANCE_WL) for n in obj_norms)
                    is_fp = any(("fireplace" in n and "sconce" not in n and "tool" not in n) or n == "hearth" for n in obj_norms)
                    is_fp_tool = any("fireplace tool" in n for n in obj_norms)
                    is_cndl = is_candle(obj_norms)
                    is_bath = any("bathtub" in n for n in obj_norms)
                    
                    if is_appliance and not is_cndl and not is_fp:
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
                    elif is_fp_tool and not is_cndl:
                        # fireplace tool set: 保留 FLAG (turn_on 不合理但无更好选项)
                        pass  # 不在清理范围内
                    elif is_bath and "vocab_gap:no_faucet_action" in ms:
                        plan.append({"file": rel_path, "task_idx": tidx, "step_id": sid,
                            "rule": "R4_bathtub_clean", "old_action": aid, "new_action": aid,
                            "old_atomic_step": at, "new_atomic_step": at,
                            "relation_op": "no_change",
                            "ms_op": "-vocab_gap:no_faucet_action; +idiom_ok:turn_on_appliance",
                            "step_orig": orig[:80]})
                        stats["R4_bathtub_clean"] += 1
                
                # ============ F1: brew → start_machine (from inspect) ============
                if verb == "brew" and aid == "inspect":
                    m_brew = re.match(r"brew\s+(.*)", orig, re.I)
                    patient = m_brew.group(1).rstrip(".") if m_brew else ""
                    # 从 labels 找 coffee machine
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
                
                # ============ F2: warm → turn_on/start_machine (from inspect) ============
                if verb == "warm" and aid == "inspect":
                    device = [o for o in objs if any(k in norm(o) for k in ("toaster","oven","stove","microwave","grill"))]
                    coffee = [o for o in objs if any(k in norm(o) for k in ("coffee",))]
                    if coffee:
                        new_aid = "start_machine"
                        dev_name = coffee[0]
                    elif device:
                        new_aid = "turn_on"
                        dev_name = device[0]
                    else:
                        dev_name = objs[0] if objs else "device"
                        new_aid = "turn_on"
                    new_at = f"{'Start' if new_aid=='start_machine' else 'Turn on'} the {dev_name}."
                    plan.append({"file": rel_path, "task_idx": tidx, "step_id": sid,
                        "rule": "F2_warm_inspect", "old_action": aid, "new_action": new_aid,
                        "old_atomic_step": at, "new_atomic_step": new_at,
                        "relation_op": "no_change",
                        "ms_op": f"+vocab_extension_v1:inspect->{new_aid}",
                        "step_orig": orig[:80]})
                    stats["F2_warm_inspect"] += 1
                
                # ============ F3: repair → within-vocab remap ============
                if verb == "repair" and aid in ("reposition", "turn_on"):
                    # 需要逐条判定, 先收集
                    f3_verdicts.append({
                        "file": rel_path, "task_idx": tidx, "step_id": sid,
                        "old_action": aid, "atomic_step": at,
                        "step_orig": orig[:100], "objects": ", ".join(objs),
                        "verdict": "", "new_action": "", "reason": ""
                    })
                    stats["F3_repair_pending"] += 1

# ============ 保存 plan.csv ============
csv_path = os.path.join(QA_OUT, "vocab_ext_plan.csv")
if plan:
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(plan[0].keys()))
        w.writeheader()
        w.writerows(plan)

# ============ 保存 F3 verdicts (待判定) ============
f3_path = os.path.join(QA_OUT, "f3_repair_verdicts.csv")
if f3_verdicts:
    with open(f3_path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(f3_verdicts[0].keys()))
        w.writeheader()
        w.writerows(f3_verdicts)

# ============ 输出对照表 ============
expected = {"R1_light": 176, "R2_unload": 54, "R3_iron": 27, "R4_tune_flag": 13,
    "R4_roll_flag": 79, "R4_appliance_clean": 539, "R4_fireplace_soft": 549,
    "R4_bathtub_clean": 14, "F1_brew_inspect": 1, "F2_warm_inspect": 3, "F3_repair_pending": 69}

print("=" * 70)
print(f"{'Rule':<25} {'Actual':<10} {'Expected':<10} {'Delta':<10} {'Status'}")
print("-" * 70)
for rule in sorted(set(list(expected.keys()) + list(stats.keys()))):
    actual = stats.get(rule, 0)
    exp = expected.get(rule, "?")
    if isinstance(exp, int):
        delta = actual - exp
        pct = abs(delta) / max(exp, 1) * 100
        status = "OK" if pct <= 10 else f"WARN ({pct:.0f}%)"
    else:
        delta = "?"
        status = "?"
    print(f"{rule:<25} {actual:<10} {str(exp):<10} {str(delta):<10} {status}")

print(f"\nTotal plan entries: {len(plan)}")
print(f"F3 pending verdicts: {len(f3_verdicts)}")
print(f"\nPlan CSV: {csv_path}")
print(f"F3 CSV: {f3_path}")
