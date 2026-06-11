"""
vocab_ext_apply.py — S4 数据应用脚本
应用 R1-R4、F1-F3 及 EXTRA 规则，写入 JSON，输出 changes_vocab_ext.csv。
"""
import json, glob, os, re, csv
from collections import defaultdict

ROOT = r"d:\微信文件\xwechat_files\wxid_mviguy0cna1m22_c0e5\msg\file\2026-06\cot_data\cot_data"
DATA = os.path.join(ROOT, "gemini_tasks_output_hm3d_atomic")
QA_OUT = os.path.join(ROOT, "qa_output")

def norm(s): return s.lower().strip().replace("_", " ")
def has_verb(step_text, verb): return bool(re.search(r'\b' + verb + r'\b', step_text, re.I))
def step_verb(s):
    m = re.match(r"^(\w+)\s", s)
    return m.group(1).lower() if m else ""

CANDLE_WL = {"candle", "candlestick", "candle holder", "candle_holder", "fireplace sconce"}
def is_candle(obj_norms): return any(any(kw in n for kw in CANDLE_WL) for n in obj_norms)

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

UNLOAD_WL = {"dishwasher", "washing machine", "washer", "dryer", "washer-dryer", "washer dryer", "washer_dryer"}
APPLIANCE_WL = {"kettle", "stove", "stovetop", "stove top", "oven", "oven and stove",
    "microwave oven", "microwave", "toaster oven", "toaster", "rice cooker", "cooker",
    "heater", "electric heater", "sauna heater", "sauna oven", "water heater",
    "furnace", "grill", "hot plate", "hotplate", "burner", "gas stove", "radiator"}

# 加载 F3 判决字典
f3_dict = {}
with open(os.path.join(QA_OUT, "f3_repair_verdicts_judged.csv"), "r", encoding="utf-8") as f:
    for r in csv.DictReader(f):
        key = f"{r['file']}::{r['task_idx']}::{r['step_id']}::{r['old_action']}"
        f3_dict[key] = r

def modify_tag(ms_str, op):
    # 解析 ms_op 形如: +vocab_extension_v1:turn_on->light; -vocab_gap:no_ignite_action
    ms = ms_str or ""
    ops = [x.strip() for x in op.split(";")]
    for o in ops:
        if o.startswith("+"):
            tag = o[1:]
            if tag not in ms:
                ms = (ms + ";" + tag) if ms else tag
        elif o.startswith("-"):
            tag = o[1:]
            if tag.endswith("*"):
                prefix = tag[:-1]
                parts = ms.split(";")
                ms = ";".join([p for p in parts if not p.startswith(prefix)])
            else:
                ms = ms.replace(";" + tag, "").replace(tag + ";", "").replace(tag, "")
    return ms if ms else None

changes = []
stats = defaultdict(int)
files = sorted(glob.glob(os.path.join(DATA, "**", "*.json"), recursive=True))

for fpath in files:
    with open(fpath, "r", encoding="utf-8") as f:
        d = json.load(f)
    rel_path = os.path.relpath(fpath, DATA).replace("\\", "/")
    
    modified = False
    for tidx, task in enumerate(d.get("tasks", [])):
        for step in task.get("plan", []):
            orig = step.get("step", "")
            verb0 = step_verb(orig)
            objs = list(step.get("labels", {}).values())
            obj_norms = [norm(o) for o in objs]
            sid = step.get("step_id")
            
            for aa in step.get("atomic_actions", []):
                old_aid = aa["action_id"]
                at = step.get("atomic_step", "")
                old_at = at
                old_rel = aa.get("relation")
                old_ms = aa.get("mapping_source") or ""
                
                if "vocab_extension_v1" in old_ms: continue
                
                new_aid = old_aid
                new_at = at
                new_rel = old_rel
                ms_op = None
                rule_matched = None
                
                # R1
                if old_aid == "turn_on" and is_candle(obj_norms) and not is_light_excluded(obj_norms):
                    rule_matched = "R1_light"
                    new_aid = "light"
                    new_at = at.replace("Turn on ", "Light ").replace("turn on ", "light ")
                    ms_op = "+vocab_extension_v1:turn_on->light; -vocab_gap:no_ignite_action"
                
                # R2
                elif old_aid in ("open", "dump") and has_verb(orig, "unload"):
                    if any(any(kw in n for kw in UNLOAD_WL) for n in obj_norms):
                        rule_matched = "R2_unload"
                        new_aid = "unload"
                        m_pat = re.search(r'unload\s+(.*?)(?:\.|$)', orig, re.I)
                        if m_pat:
                            new_at = f"Unload {m_pat.group(1).strip().rstrip('.')}."
                        else:
                            new_at = at.replace("Open ", "Unload ").replace("Dump ", "Unload ")
                        ms_op = f"+vocab_extension_v1:{old_aid}->unload"
                        if not new_rel: new_rel = None
                
                # R3
                elif old_aid in ("straighten", "smooth", "store") and verb0 == "iron":
                    rule_matched = "R3_iron"
                    new_aid = "iron"
                    m_ir = re.match(r"iron\s+(.*)", orig, re.I)
                    if m_ir:
                        new_at = f"Iron {m_ir.group(1).rstrip('.')}."
                    else:
                        new_at = at.replace("Straighten ", "Iron ").replace("Smooth ", "Iron ")
                    if any("ironing" in n or "iron board" in n for n in obj_norms):
                        if "on the" in new_at.lower() or "ironing" in new_at.lower():
                            new_rel = "on"
                    ms_op = f"+vocab_extension_v1:{old_aid}->iron"
                
                # R4a
                elif old_aid == "set_control" and has_verb(orig, "tune") and "vocab_gap:no_tune_action" not in old_ms:
                    rule_matched = "R4_tune_flag"
                    ms_op = "+vocab_gap:no_tune_action"
                
                # R4b (updated regex)
                elif bool(re.search(r'\b(un|lint-)?roll\b', orig, re.I)) and old_aid in ("carry", "smooth", "inspect", "straighten"):
                    if "vocab_gap:roll" not in old_ms:
                        rule_matched = "R4_roll_flag"
                        ms_op = "+vocab_gap:roll"
                
                # R4c
                elif old_aid in ("turn_on", "turn_off") and "vocab_gap:" in old_ms:
                    is_app = any(any(kw in n for kw in APPLIANCE_WL) for n in obj_norms)
                    is_fp = any(("fireplace" in n and "sconce" not in n and "tool" not in n) or n == "hearth" for n in obj_norms)
                    is_bath = any("bathtub" in n for n in obj_norms)
                    is_cndl = is_candle(obj_norms)
                    
                    if is_app and not is_cndl and not is_fp:
                        rule_matched = "R4_appliance_clean"
                        ms_op = "-vocab_gap:*; +idiom_ok:turn_on_appliance"
                    elif is_fp and not is_cndl:
                        rule_matched = "R4_fireplace_soft"
                        ms_op = "-vocab_gap:no_ignite_action; +assume_gas_fireplace"
                    elif is_bath and "vocab_gap:no_faucet_action" in old_ms:
                        rule_matched = "R4_bathtub_clean"
                        ms_op = "-vocab_gap:no_faucet_action; +idiom_ok:turn_on_appliance"
                
                # F1
                elif has_verb(orig, "brew") and old_aid == "inspect":
                    rule_matched = "F1_brew_inspect"
                    new_aid = "start_machine"
                    mac = [o for o in objs if any(k in norm(o) for k in ("coffee", "machine", "maker"))]
                    mac_name = mac[0] if mac else "coffee machine"
                    new_at = f"Start the {mac_name}."
                    ms_op = "+vocab_extension_v1:inspect->start_machine"
                
                # F2
                elif has_verb(orig, "warm") and old_aid == "inspect":
                    # Exclude the specific entry
                    if "Check the furnace to make sure the room is warm." in orig:
                        pass # keep inspect, no ms_op
                    else:
                        rule_matched = "F2_warm_inspect"
                        dev = [o for o in objs if any(k in norm(o) for k in ("toaster","oven","stove","microwave","grill","heater","kettle","furnace"))]
                        cof = [o for o in objs if "coffee" in norm(o)]
                        blk = [o for o in objs if any(k in norm(o) for k in ("blanket","throw","comforter"))]
                        exe = [o for o in objs if any(k in norm(o) for k in ("treadmill","exercise","gym"))]
                        
                        if blk:
                            new_aid = "cover"
                            new_at = f"Cover with the {blk[0]}."
                        elif cof:
                            new_aid = "start_machine"
                            new_at = f"Start the {cof[0]}."
                        elif exe:
                            new_aid = "turn_on"
                            new_at = f"Turn on the {exe[0]}."
                        elif dev:
                            new_aid = "turn_on"
                            new_at = f"Turn on the {dev[0]}."
                        else:
                            new_aid = "turn_on"
                            new_at = f"Turn on the {objs[0] if objs else 'device'}."
                        ms_op = f"+vocab_extension_v1:inspect->{new_aid}"
                
                # F3
                elif has_verb(orig, "repair") and old_aid in ("reposition", "turn_on"):
                    # 使用 Windows/Linux 兼容的路径匹配，去掉前面的部分，或者替换反斜杠
                    # f3_repair_verdicts_judged.csv 里保存的是原 rel_path，可能是带 \\ 的
                    key1 = f"{rel_path}::{tidx}::{sid}::{old_aid}"
                    key2 = f"{rel_path.replace('/', chr(92))}::{tidx}::{sid}::{old_aid}"
                    key = key1 if key1 in f3_dict else key2
                    
                    if key in f3_dict:
                        v = f3_dict[key]
                        rule_matched = f"F3_repair_{v['verdict']}"
                        if v["verdict"] == "REMAP":
                            new_aid = v["new_action"]
                            cap_old = old_aid.capitalize()
                            cap_new = new_aid.capitalize()
                            new_at = at.replace(cap_old + " ", cap_new + " ").replace(old_aid + " ", new_aid + " ")
                            ms_op = f"+vocab_extension_v1:repair_remap->{new_aid}"
                        else:
                            ms_op = f"+vocab_gap:repair"
                
                # EXTRA 00891
                elif "00891" in rel_path and tidx == 213 and sid == 6 and at == "Store the box.":
                    rule_matched = "EXTRA_patient_drift"
                    new_at = "Store the iron in the storage box."
                    new_rel = "in"
                    ms_op = "+vocab_extension_v1:patient_drift_fix"
                
                # Apply changes
                if rule_matched:
                    if ms_op:
                        new_ms = modify_tag(old_ms, ms_op)
                        aa["mapping_source"] = new_ms
                    if new_aid != old_aid:
                        aa["action_id"] = new_aid
                    if new_at != old_at:
                        step["atomic_step"] = new_at
                    if new_rel != old_rel:
                        aa["relation"] = new_rel
                        
                    modified = True
                    stats[rule_matched] += 1
                    changes.append({
                        "file": rel_path, "task_idx": tidx, "step_id": sid,
                        "rule": rule_matched, "old_action": old_aid, "new_action": new_aid,
                        "old_atomic_step": old_at, "new_atomic_step": new_at,
                        "relation": str(new_rel), "mapping_source_op": str(ms_op),
                        "step_orig": orig[:80]
                    })
                    
    if modified:
        with open(fpath, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
            f.write("\n")

# Save changes CSV
csv_path = os.path.join(QA_OUT, "changes_vocab_ext.csv")
if changes:
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(changes[0].keys()))
        w.writeheader()
        w.writerows(changes)

print("=== Vocab Extension Apply Complete ===")
for k, v in sorted(stats.items()):
    print(f"  {k}: {v}")

print(f"\nTotal modifications: {len(changes)}")
print(f"Log written to: {csv_path}")

# ====== S5 Verification ======
print("\n=== S5 Verification ===")
v_actions = defaultdict(int)
v_gaps = defaultdict(int)
v_candle_turn_on = 0
v_lamp_fp_modified = 0

for fpath in files:
    d = json.load(open(fpath, "r", encoding="utf-8"))
    for t in d.get("tasks", []):
        for s in t.get("plan", []):
            objs = list(s.get("labels", {}).values())
            obj_norms = [norm(o) for o in objs]
            for aa in s.get("atomic_actions", []):
                aid = aa["action_id"]
                ms = aa.get("mapping_source") or ""
                v_actions[aid] += 1
                
                # Check vocab gap
                for tg in re.findall(r'vocab_gap:\w+', ms):
                    v_gaps[tg] += 1
                
                # Check candle
                if aid == "turn_on" and is_candle(obj_norms) and not is_light_excluded(obj_norms):
                    v_candle_turn_on += 1
                    
                # Check new actions only on whitelist
                if aid == "light":
                    if not is_candle(obj_norms):
                        print(f"WARN: light used on non-candle: {objs}")
                if aid == "unload":
                    if not any(any(kw in n for kw in UNLOAD_WL) for n in obj_norms):
                        print(f"WARN: unload used on non-unloadable: {objs}")

print(f"Total Unique Actions: {len(v_actions)} (expected 52)")
print(f"vocab_gap:roll count: {v_gaps['vocab_gap:roll']} (expected 84)")
print(f"Candle turn_on remaining: {v_candle_turn_on} (expected 0)")

if len(v_actions) == 52:
    print("Action space is strictly within the 52 actions.")
else:
    print(f"Action space deviation! Found {len(v_actions)}")
    for a in sorted(v_actions.keys()):
        print(f"  {a}: {v_actions[a]}")

print("Verifying 00844 exclusion...")
v_00844 = False
for fpath in files:
    if "00844-q5QZSEeHe5g" in fpath:
        d = json.load(open(fpath, "r", encoding="utf-8"))
        for t in d.get("tasks", []):
            for s in t.get("plan", []):
                if "Check the furnace to make sure the room is warm." in s.get("step", ""):
                    for aa in s.get("atomic_actions", []):
                        if aa["action_id"] == "inspect" and "vocab_extension_v1" not in (aa.get("mapping_source") or ""):
                            v_00844 = True
if v_00844:
    print("00844 exclusion successful. Action remains inspect with no extension tags.")
else:
    print("00844 exclusion FAILED.")

# Write frequency file
freq_path = os.path.join(ROOT, "gemini_tasks_output_hm3d_atomic_action_frequency_v3.json")
with open(freq_path, "w", encoding="utf-8") as f:
    json.dump({"action_frequencies": dict(v_actions)}, f, indent=2)
print(f"\nUpdated frequencies written to: {freq_path}")
