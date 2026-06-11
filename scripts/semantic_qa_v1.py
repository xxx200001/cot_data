"""
semantic_qa_v1.py — 一次性修复全部 7 类问题
基于人工审核的逐条裁决执行。

修复清单:
1. ROLLBACK_R02: fluff→straighten (229) 全部回滚为 fluff
2. FIX_STORE: fill→store 的 58 条 (toilet paper/tissue/paper towel) 改为 load
3. ROLLBACK_PHONE: 00238 task172 step4 place_on→set_control 回滚
4. FIX_PHONE_TEXT: 8 条 place_on 手机补齐目的地文本和 relation
5. FIX_RINSE_DISHWASHER: 13 条受事漂移修复
6. FIX_VACUUM_WALLCLOCK: 1 条受事漂移修复
7. FLAG_VOCAB_GAP: candle 系 164 + guitar 65 标注 vocab_gap
"""
import json, os, glob, csv, shutil, re
from datetime import datetime
from collections import defaultdict

ROOT = r"d:\微信文件\xwechat_files\wxid_mviguy0cna1m22_c0e5\msg\file\2026-06\cot_data\cot_data"
DATA = os.path.join(ROOT, "gemini_tasks_output_hm3d_atomic")
QA_OUT = os.path.join(ROOT, "qa_output")
SCRIPTS = os.path.join(ROOT, "scripts")
os.makedirs(QA_OUT, exist_ok=True)

def norm(s): return s.lower().strip().replace("_", " ")

def load_all():
    files = sorted(glob.glob(os.path.join(DATA, "**", "*.json"), recursive=True))
    out = {}
    for f in files:
        with open(f, "r", encoding="utf-8") as fh:
            out[f] = json.load(fh)
    return out

def save(fpath, data):
    with open(fpath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")

changes = []

def record(fpath, scene, tidx, sid, etype, old_a, new_a, old_t, new_t, reason):
    changes.append({
        "file": os.path.relpath(fpath, DATA), "scene_id": scene,
        "task_idx": tidx, "step_id": sid, "error_type": etype,
        "old_action": old_a, "new_action": new_a,
        "old_atomic_step": old_t, "new_atomic_step": new_t, "reason": reason
    })

def has_tag(aa, tag):
    return tag in (aa.get("mapping_source") or "")

def add_tag(aa, tag):
    ms = aa.get("mapping_source") or ""
    if tag not in ms:
        aa["mapping_source"] = (ms + ";" + tag) if ms else tag

# ================================================================
# 1. ROLLBACK R02: straighten→fluff (只回滚 semantic_repair_v5:fluff_furniture_to_straighten)
# ================================================================
def fix_rollback_r02(data_dict):
    count = 0
    for fpath, data in data_dict.items():
        scene = data.get("scene_id", "")
        for tidx, task in enumerate(data.get("tasks", [])):
            for step in task.get("plan", []):
                for aa in step.get("atomic_actions", []):
                    if has_tag(aa, "semantic_repair_v5:fluff_furniture_to_straighten"):
                        old_t = step["atomic_step"]
                        aa["action_id"] = "fluff"
                        aa["mapping_source"] = aa["mapping_source"].replace(
                            "semantic_repair_v5:fluff_furniture_to_straighten",
                            "semantic_qa_v1:rollback_r02_straighten-->fluff")
                        step["atomic_step"] = step["atomic_step"].replace("Straighten ", "Fluff ").replace("straighten ", "fluff ")
                        record(fpath, scene, tidx, step["step_id"], "ROLLBACK",
                               "straighten", "fluff", old_t, step["atomic_step"],
                               "R02 was over-correction; couch/sofa items ARE fluffable")
                        count += 1
    print(f"  [1] ROLLBACK_R02: {count}")

# ================================================================
# 2. FIX store→load for toilet paper/tissue/paper towel (58 条)
# ================================================================
def fix_store_to_load(data_dict):
    count = 0
    targets = ["toilet paper", "tissue", "paper towel"]
    for fpath, data in data_dict.items():
        scene = data.get("scene_id", "")
        for tidx, task in enumerate(data.get("tasks", [])):
            for step in task.get("plan", []):
                objs = list(step.get("labels", {}).values())
                for aa in step.get("atomic_actions", []):
                    if aa["action_id"] != "store":
                        continue
                    if not has_tag(aa, "semantic_repair_v5:fill_"):
                        continue
                    for obj in objs:
                        if any(t in norm(obj) for t in targets):
                            old_t = step["atomic_step"]
                            aa["action_id"] = "load"
                            add_tag(aa, "semantic_qa_v1:store-->load")
                            step["atomic_step"] = step["atomic_step"].replace("Store ", "Load ").replace("store ", "load ")
                            record(fpath, scene, tidx, step["step_id"], "FIX",
                                   "store", "load", old_t, step["atomic_step"],
                                   f"store偏离refill意图; load更贴合'补装{obj}'")
                            count += 1
                            break
    print(f"  [2] FIX_STORE→LOAD: {count}")

# ================================================================
# 3. ROLLBACK 00238 phone misfire (task172 step4)
# ================================================================
def fix_rollback_phone(data_dict):
    count = 0
    for fpath, data in data_dict.items():
        if "00238" not in fpath:
            continue
        scene = data.get("scene_id", "")
        for tidx, task in enumerate(data.get("tasks", [])):
            for step in task.get("plan", []):
                orig = step.get("step", "")
                if "set a timer" in orig.lower() or "timer" in orig.lower():
                    for aa in step.get("atomic_actions", []):
                        if aa["action_id"] == "place_on" and has_tag(aa, "semantic_repair_v5:set_phone_to_place_on"):
                            old_t = step["atomic_step"]
                            aa["action_id"] = "set_control"
                            aa["relation"] = None
                            aa["mapping_source"] = aa["mapping_source"].replace(
                                "semantic_repair_v5:set_phone_to_place_on",
                                "semantic_qa_v1:rollback_place_on-->set_control")
                            step["atomic_step"] = "Set a timer on the cellular_telephone."
                            record(fpath, scene, tidx, step["step_id"], "ROLLBACK",
                                   "place_on", "set_control", old_t, step["atomic_step"],
                                   "Setting a timer IS set_control; was wrongly matched as placement")
                            count += 1
    print(f"  [3] ROLLBACK_PHONE: {count}")

# ================================================================
# 4. FIX 8 phone place_on: 补目的地文本 + relation=on
# ================================================================
def fix_phone_text(data_dict):
    count = 0
    for fpath, data in data_dict.items():
        scene = data.get("scene_id", "")
        for tidx, task in enumerate(data.get("tasks", [])):
            for step in task.get("plan", []):
                for aa in step.get("atomic_actions", []):
                    if aa["action_id"] != "place_on":
                        continue
                    if not has_tag(aa, "semantic_repair_v5:set_phone_to_place_on"):
                        continue
                    orig = step.get("step", "")
                    # 从原始 step 提取目的地 "on the ..."
                    m = re.search(r'on\s+(the\s+\w[\w\s]*)', orig, re.I)
                    dest = m.group(1).strip().rstrip('.') if m else ""
                    if dest and dest.lower() not in step["atomic_step"].lower():
                        old_t = step["atomic_step"]
                        obj_labels = list(step.get("labels", {}).values())
                        phone = [o for o in obj_labels if "phone" in norm(o) or "cellular" in norm(o) or "telephone" in norm(o)]
                        phone_name = phone[0] if phone else "cellular_telephone"
                        step["atomic_step"] = f"Place the {phone_name} on {dest}."
                        aa["relation"] = "on"
                        add_tag(aa, "semantic_qa_v1:fix_phone_text")
                        record(fpath, scene, tidx, step["step_id"], "FIX",
                               "place_on", "place_on", old_t, step["atomic_step"],
                               f"Restored destination '{dest}' from original step")
                        count += 1
    print(f"  [4] FIX_PHONE_TEXT: {count}")

# ================================================================
# 5. FIX rinse+dishwasher: 受事漂移 (13 条)
# step: "Rinse the spoon in the dishwasher" → atomic: "Rinse dishwasher"
# 修法: 从 step 提取真正受事, relation=in, 处所=dishwasher
# ================================================================
def fix_rinse_dishwasher(data_dict):
    count = 0
    for fpath, data in data_dict.items():
        scene = data.get("scene_id", "")
        for tidx, task in enumerate(data.get("tasks", [])):
            for step in task.get("plan", []):
                objs = list(step.get("labels", {}).values())
                for aa in step.get("atomic_actions", []):
                    if aa["action_id"] != "rinse":
                        continue
                    for obj in objs:
                        if "dishwasher" not in norm(obj):
                            continue
                        orig = step.get("step", "")
                        # 检查原文是否是 "rinse X in the dishwasher" 模式
                        m = re.search(r'[Rr]inse\s+(the\s+)?(\w+)', orig)
                        if m:
                            true_patient = m.group(2).lower()
                            if true_patient != "dishwasher" and "dishwasher" in norm(obj):
                                old_t = step["atomic_step"]
                                step["atomic_step"] = f"Rinse the {true_patient} in the {obj}."
                                aa["relation"] = "in"
                                add_tag(aa, "semantic_qa_v1:fix_patient_drift_rinse")
                                record(fpath, scene, tidx, step["step_id"], "B",
                                       "rinse", "rinse", old_t, step["atomic_step"],
                                       f"Patient drift: true patient is '{true_patient}', dishwasher is location")
                                count += 1
                                break
    print(f"  [5] FIX_RINSE_DISHWASHER: {count}")

# ================================================================
# 6. FIX vacuum+wall_clock: 受事漂移 (1 条)
# step: "Sweep near the wall clock" → atomic: "Vacuum the wall clock"
# ================================================================
def fix_vacuum_wallclock(data_dict):
    count = 0
    for fpath, data in data_dict.items():
        scene = data.get("scene_id", "")
        for tidx, task in enumerate(data.get("tasks", [])):
            for step in task.get("plan", []):
                objs = list(step.get("labels", {}).values())
                for aa in step.get("atomic_actions", []):
                    if aa["action_id"] != "vacuum":
                        continue
                    for obj in objs:
                        if "wall clock" in norm(obj) or "wallclock" in norm(obj):
                            orig = step.get("step", "")
                            if "near" in orig.lower():
                                old_t = step["atomic_step"]
                                step["atomic_step"] = f"Vacuum near the {obj}."
                                aa["relation"] = "at"
                                add_tag(aa, "semantic_qa_v1:fix_patient_drift_vacuum")
                                record(fpath, scene, tidx, step["step_id"], "B",
                                       "vacuum", "vacuum", old_t, step["atomic_step"],
                                       "Patient drift: vacuuming the floor NEAR the clock, not the clock")
                                count += 1
                                break
    print(f"  [6] FIX_VACUUM_WALLCLOCK: {count}")

# ================================================================
# 7. FLAG vocab gaps: candle系 + guitar
# ================================================================
def flag_vocab_gaps(data_dict):
    count_candle = 0
    count_guitar = 0
    for fpath, data in data_dict.items():
        scene = data.get("scene_id", "")
        for tidx, task in enumerate(data.get("tasks", [])):
            for step in task.get("plan", []):
                objs = list(step.get("labels", {}).values())
                for aa in step.get("atomic_actions", []):
                    if has_tag(aa, "vocab_gap:"):
                        continue
                    # Candle: turn_on + candle/candlestick/candle_holder
                    if aa["action_id"] == "turn_on":
                        for obj in objs:
                            n = norm(obj)
                            if "candle" in n and "candle" not in "electric candle":
                                add_tag(aa, "vocab_gap:no_ignite_action")
                                count_candle += 1
                                break
                    # Guitar: set_control + guitar
                    if aa["action_id"] == "set_control":
                        for obj in objs:
                            if "guitar" in norm(obj):
                                add_tag(aa, "vocab_gap:no_tune_action")
                                count_guitar += 1
                                break
    print(f"  [7] FLAG candle={count_candle}, guitar={count_guitar}")

# ================================================================
def main():
    print("=" * 60)
    print("semantic_qa_v1 — comprehensive fix")
    print("=" * 60)

    # Backup
    backup = os.path.join(ROOT, f"cot_data_backup_{datetime.now().strftime('%Y%m%d_%H%M')}")
    if not os.path.exists(backup):
        print(f"Backing up to {backup} ...")
        shutil.copytree(DATA, os.path.join(backup, "gemini_tasks_output_hm3d_atomic"))
    
    print("Loading...")
    data = load_all()
    print(f"Loaded {len(data)} files\n")

    fix_rollback_r02(data)
    fix_store_to_load(data)
    fix_rollback_phone(data)
    fix_phone_text(data)
    fix_rinse_dishwasher(data)
    fix_vacuum_wallclock(data)
    flag_vocab_gaps(data)

    # Save all modified files
    print("\nSaving...")
    for fpath, d in data.items():
        save(fpath, d)

    # Write changes.csv
    csv_path = os.path.join(QA_OUT, "changes.csv")
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(changes[0].keys()) if changes else [])
        w.writeheader()
        w.writerows(changes)
    
    print(f"\nTotal changes: {len(changes)}")
    print(f"Changes log: {csv_path}")

    # Verify: count all action_ids
    valid = {"wipe","straighten","pick_up","turn_on","inspect","place_on","scrub","dust",
             "reposition","open","close","push","smooth","carry","fluff","lift","place_in",
             "dump","set_control","turn_off","store","hang","fold","set_up","load","pour",
             "fill","rinse","polish","align","start_machine","stack","vacuum","set","plug_in",
             "dispose","shake_out","cover","pull","tighten","lock","attach","flush","mop",
             "tuck","press","unplug","unlock","pack"}
    bad = 0
    total = 0
    for d in data.values():
        for t in d.get("tasks", []):
            for s in t.get("plan", []):
                for aa in s.get("atomic_actions", []):
                    total += 1
                    if aa["action_id"] not in valid:
                        bad += 1
                        print(f"  !! INVALID: {aa['action_id']}")
    print(f"\nVerification: {total} actions, {bad} invalid")
    print("=" * 60)

if __name__ == "__main__":
    main()
