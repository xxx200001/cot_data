"""
add_new_actions.py — 新增 7 个原子动作并更新数据
New actions: light, tune, unload, charge, brew, repair, iron

策略: 通过 step 原文的首动词匹配，确认意图后更新 action_id 和 atomic_step
"""
import json, glob, os, re, csv
from collections import defaultdict

ROOT = r"d:\微信文件\xwechat_files\wxid_mviguy0cna1m22_c0e5\msg\file\2026-06\cot_data\cot_data"
DATA = os.path.join(ROOT, "gemini_tasks_output_hm3d_atomic")
QA_OUT = os.path.join(ROOT, "qa_output")

def norm(s): return s.lower().strip().replace("_", " ")
def has_tag(aa, tag): return tag in (aa.get("mapping_source") or "")
def add_tag(aa, tag):
    ms = aa.get("mapping_source") or ""
    if tag not in ms:
        aa["mapping_source"] = (ms + ";" + tag) if ms else tag
def remove_tag(aa, tag):
    ms = aa.get("mapping_source") or ""
    ms = ms.replace(";" + tag, "").replace(tag + ";", "").replace(tag, "")
    aa["mapping_source"] = ms if ms else None

def step_verb(step_text):
    """提取 step 原文的首动词"""
    m = re.match(r"^(\w+)\s", step_text)
    return m.group(1).lower() if m else ""

changes = []
stats = defaultdict(int)
files = sorted(glob.glob(os.path.join(DATA, "**", "*.json"), recursive=True))

for fpath in files:
    with open(fpath, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    modified = False
    for tidx, task in enumerate(data.get("tasks", [])):
        for step in task.get("plan", []):
            orig = step.get("step", "")
            verb = step_verb(orig)
            objs = [v for v in step.get("labels", {}).values()]
            obj_norms = [norm(o) for o in objs]
            
            for aa in step.get("atomic_actions", []):
                aid = aa["action_id"]
                old_aid = aid
                old_at = step.get("atomic_step", "")
                new_aid = None
                new_at = None
                
                # ============================================================
                # 1. light: candle/candlestick/candle_holder/fireplace_sconce
                #    turn_on + candle类 → light
                # ============================================================
                if aid == "turn_on" and has_tag(aa, "vocab_gap:no_ignite_action"):
                    if any("candle" in n or "candlestick" in n for n in obj_norms):
                        new_aid = "light"
                        new_at = old_at.replace("Turn on ", "Light ").replace("turn on ", "light ")
                        remove_tag(aa, "vocab_gap:no_ignite_action")
                        stats["light_candle"] += 1
                    elif any("sconce" in n for n in obj_norms):
                        new_aid = "light"
                        new_at = old_at.replace("Turn on ", "Light ").replace("turn on ", "light ")
                        remove_tag(aa, "vocab_gap:no_ignite_action")
                        stats["light_sconce"] += 1
                
                # ============================================================
                # 2. tune: guitar
                #    set_control + guitar → tune
                # ============================================================
                if aid == "set_control" and has_tag(aa, "vocab_gap:no_tune_action"):
                    if any("guitar" in n for n in obj_norms):
                        new_aid = "tune"
                        new_at = old_at.replace("Adjust ", "Tune ").replace("adjust ", "tune ")
                        remove_tag(aa, "vocab_gap:no_tune_action")
                        stats["tune_guitar"] += 1
                
                # ============================================================
                # 3. unload: washing machine, dishwasher, dryer
                #    step verb = unload, 当前 action = open → unload
                # ============================================================
                if verb == "unload" and aid == "open":
                    new_aid = "unload"
                    new_at = old_at.replace("Open ", "Unload ").replace("open ", "unload ")
                    stats["unload"] += 1
                
                # ============================================================
                # 4. charge: laptop, phone, tablet
                #    step verb = charge, 当前 action = plug_in → charge
                # ============================================================
                if verb == "charge" and aid == "plug_in":
                    new_aid = "charge"
                    new_at = old_at.replace("Plug in ", "Charge ").replace("plug in ", "charge ")
                    stats["charge"] += 1
                
                # ============================================================
                # 5. brew: coffee machine, coffee maker
                #    step verb = brew, 当前 action = start_machine → brew
                # ============================================================
                if verb == "brew" and aid == "start_machine":
                    new_aid = "brew"
                    # atomic_step 可能是 "Start the coffee machine."
                    new_at = old_at.replace("Start ", "Brew with ").replace("start ", "brew with ")
                    stats["brew"] += 1
                # brew 映射到 turn_on 的也改
                if verb == "brew" and aid == "turn_on":
                    new_aid = "brew"
                    new_at = old_at.replace("Turn on ", "Brew with ").replace("turn on ", "brew with ")
                    stats["brew_from_turn_on"] += 1
                
                # ============================================================
                # 6. repair: shelf, door, fence, etc.
                #    step verb = repair, 当前 action = reposition/attach/tighten → repair
                # ============================================================
                if verb == "repair" and aid in ("reposition", "attach", "tighten", "straighten", "inspect", "set_up"):
                    new_aid = "repair"
                    # 从 step 原文提取受事来构造 atomic_step
                    m = re.match(r"repair\s+(.*)", orig, re.I)
                    if m:
                        patient = m.group(1).rstrip(".")
                        new_at = f"Repair {patient}."
                    else:
                        new_at = old_at  # fallback
                    stats["repair"] += 1
                
                # ============================================================
                # 7. iron: clothes, shirt, etc.
                #    step verb = iron, 当前 action = straighten/smooth → iron
                # ============================================================
                if verb == "iron" and aid in ("straighten", "smooth"):
                    new_aid = "iron"
                    new_at = old_at.replace("Straighten ", "Iron ").replace("straighten ", "iron ").replace("Smooth ", "Iron ").replace("smooth ", "iron ")
                    stats["iron"] += 1
                
                # 应用修改
                if new_aid and new_at:
                    aa["action_id"] = new_aid
                    step["atomic_step"] = new_at
                    add_tag(aa, f"new_action_v1:{old_aid}-->{new_aid}")
                    modified = True
                    changes.append({
                        "file": os.path.relpath(fpath, DATA),
                        "task_idx": tidx, "step_id": step.get("step_id"),
                        "old_action": old_aid, "new_action": new_aid,
                        "old_text": old_at, "new_text": new_at,
                        "step_orig": orig[:80]
                    })
    
    if modified:
        with open(fpath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")

# 保存 changes log
csv_path = os.path.join(QA_OUT, "changes_new_actions.csv")
if changes:
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(changes[0].keys()))
        w.writeheader()
        w.writerows(changes)

print("=== New Actions Applied ===")
total = 0
for k, v in sorted(stats.items()):
    print(f"  {k}: {v}")
    total += v
print(f"\n  TOTAL: {total}")

# 验证: 统计新词表
print("\n=== 验证 ===")
action_counts = defaultdict(int)
total_actions = 0
remaining_gaps = 0
for fpath in files:
    d = json.load(open(fpath, "r", encoding="utf-8"))
    for t in d.get("tasks", []):
        for s in t.get("plan", []):
            for aa in s.get("atomic_actions", []):
                action_counts[aa["action_id"]] += 1
                total_actions += 1
                if "vocab_gap:" in (aa.get("mapping_source") or ""):
                    remaining_gaps += 1

print(f"Total actions: {total_actions}")
print(f"Unique action types: {len(action_counts)} (was 49, now {len(action_counts)})")
print(f"Remaining vocab_gap entries: {remaining_gaps}")

print("\nNew action counts:")
new_actions = ["light", "tune", "unload", "charge", "brew", "repair", "iron"]
for a in new_actions:
    print(f"  {a}: {action_counts.get(a, 0)}")
