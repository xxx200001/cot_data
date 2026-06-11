"""
semantic_qa_v1_closing.py — 收尾两步
1. 修 129 处 grounding 破坏: dispenser/faucet 文本回退到 label 物体名
2. 补全 FLAG: fireplace/kettle/stove/cooker/grill/bathtub 等同类 no_ignite/no_boil
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

changes = []
files = sorted(glob.glob(os.path.join(DATA, "**", "*.json"), recursive=True))

# === 需要 FLAG 的 turn_on 物体 (同类词表缺口) ===
# no_ignite: 需要点燃/生火的物体
no_ignite = ["fireplace", "fire pit", "fire place", "fireplace sconce"]
# no_boil: 需要烧水/加热的物体 (turn_on 勉强可用但不精确)
no_boil = ["kettle", "stove", "cooker", "grill", "stovetop", "stove top",
           "oven and stove", "gas stove", "hot plate", "hotplate", "burner"]
# bathtub 特殊: 既有 grounding 问题又需要 FLAG
# candle 已处理, 不重复

grounding_fixed = 0
flag_added = 0

for fpath in files:
    with open(fpath, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    modified = False
    scene = data.get("scene_id", "")
    
    for tidx, task in enumerate(data.get("tasks", [])):
        for step in task.get("plan", []):
            objs = list(step.get("labels", {}).values())
            at = step.get("atomic_step", "")
            
            for aa in step.get("atomic_actions", []):
                aid = aa["action_id"]
                
                # ============================================
                # STEP 1: 修 grounding 破坏
                # R05: "Fill the shampoo dispenser." → 回退为 "Fill the shampoo."
                # R15: "Turn on the bathtub faucet." → 回退为 "Turn on the bathtub."
                # ============================================
                
                # R05: fill + shampoo/liquid_soap, 文本被改成了 dispenser
                if aid == "fill" and has_tag(aa, "semantic_repair_v5:fill_content_to_container"):
                    if "dispenser" in at.lower():
                        # 找到 label 里的实际物体名
                        for obj in objs:
                            n = norm(obj)
                            if n in ("shampoo", "liquid soap", "liquid_soap"):
                                old_at = step["atomic_step"]
                                step["atomic_step"] = f"Fill the {obj}."
                                add_tag(aa, "semantic_qa_v1:grounding_fix_dispenser")
                                changes.append({"file": os.path.relpath(fpath, DATA),
                                    "type": "GROUNDING_FIX", "old": old_at,
                                    "new": step["atomic_step"],
                                    "reason": f"dispenser not in labels; reverted to '{obj}'"})
                                grounding_fixed += 1
                                modified = True
                                break
                
                # R15: turn_on + bathtub, 文本被改成了 "bathtub faucet"
                if aid == "turn_on" and has_tag(aa, "semantic_repair_v5:turn_on_bathtub_text_fix"):
                    if "faucet" in at.lower():
                        for obj in objs:
                            if "bathtub" in norm(obj) or "bath tub" in norm(obj):
                                old_at = step["atomic_step"]
                                step["atomic_step"] = f"Turn on the {obj}."
                                add_tag(aa, "semantic_qa_v1:grounding_fix_faucet")
                                # 同时 FLAG 为词表缺口
                                add_tag(aa, "vocab_gap:no_faucet_action")
                                changes.append({"file": os.path.relpath(fpath, DATA),
                                    "type": "GROUNDING_FIX+FLAG", "old": old_at,
                                    "new": step["atomic_step"],
                                    "reason": f"faucet not in labels; reverted to '{obj}' + flagged"})
                                grounding_fixed += 1
                                flag_added += 1
                                modified = True
                                break
                
                # ============================================
                # STEP 2: 补全 FLAG — 同类词表缺口
                # ============================================
                if aid == "turn_on" and not has_tag(aa, "vocab_gap:"):
                    for obj in objs:
                        n = norm(obj)
                        # no_ignite: fireplace 系
                        if any(kw in n for kw in no_ignite):
                            add_tag(aa, "vocab_gap:no_ignite_action")
                            changes.append({"file": os.path.relpath(fpath, DATA),
                                "type": "FLAG", "action": aid, "object": obj,
                                "tag": "vocab_gap:no_ignite_action"})
                            flag_added += 1
                            modified = True
                            break
                        # no_boil: kettle/stove/cooker/grill 系
                        if any(kw in n for kw in no_boil):
                            add_tag(aa, "vocab_gap:no_boil_action")
                            changes.append({"file": os.path.relpath(fpath, DATA),
                                "type": "FLAG", "action": aid, "object": obj,
                                "tag": "vocab_gap:no_boil_action"})
                            flag_added += 1
                            modified = True
                            break
                
                # turn_off 同类也标
                if aid == "turn_off" and not has_tag(aa, "vocab_gap:"):
                    for obj in objs:
                        n = norm(obj)
                        if any(kw in n for kw in no_ignite):
                            add_tag(aa, "vocab_gap:no_ignite_action")
                            flag_added += 1
                            modified = True
                            break
                        if any(kw in n for kw in no_boil):
                            add_tag(aa, "vocab_gap:no_boil_action")
                            flag_added += 1
                            modified = True
                            break
    
    if modified:
        with open(fpath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")

# 保存 changes
csv_path = os.path.join(QA_OUT, "changes_closing.csv")
if changes:
    keys = set()
    for c in changes: keys.update(c.keys())
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=sorted(keys))
        w.writeheader()
        w.writerows(changes)

print(f"Grounding fixed: {grounding_fixed}")
print(f"Flags added: {flag_added}")
print(f"Changes log: {csv_path}")

# ============================================
# 全量门禁校验
# ============================================
print("\n=== GATE CHECK ===")
valid = {"wipe","straighten","pick_up","turn_on","inspect","place_on","scrub","dust",
         "reposition","open","close","push","smooth","carry","fluff","lift","place_in",
         "dump","set_control","turn_off","store","hang","fold","set_up","load","pour",
         "fill","rinse","polish","align","start_machine","stack","vacuum","set","plug_in",
         "dispose","shake_out","cover","pull","tighten","lock","attach","flush","mop",
         "tuck","press","unplug","unlock","pack"}

total = 0; invalid = 0
grounding_inject = 0  # atomic_step 含 label 里没有的名词
dispenser_in_text = 0; faucet_in_text = 0

# FLAG 覆盖检查
unflagged = defaultdict(int)
turn_on_objects = defaultdict(int)

for fpath in files:
    d = json.load(open(fpath, "r", encoding="utf-8"))
    for t in d.get("tasks", []):
        for s in t.get("plan", []):
            objs = [v for v in s.get("labels", {}).values()]
            obj_norms = set(norm(o) for o in objs)
            at = s.get("atomic_step", "")
            
            for aa in s.get("atomic_actions", []):
                total += 1
                if aa["action_id"] not in valid:
                    invalid += 1
                
                # grounding 注入检查
                if "dispenser" in at.lower() and not any("dispenser" in norm(o) for o in objs):
                    dispenser_in_text += 1
                if " faucet" in at.lower() and not any("faucet" in norm(o) for o in objs):
                    faucet_in_text += 1
                
                # FLAG 覆盖检查
                ms = aa.get("mapping_source") or ""
                if aa["action_id"] == "turn_on":
                    for obj in objs:
                        n = norm(obj)
                        needs_flag = False
                        if "candle" in n: needs_flag = True
                        if any(kw in n for kw in no_ignite): needs_flag = True
                        if any(kw in n for kw in no_boil): needs_flag = True
                        if "bathtub" == n: needs_flag = True
                        if needs_flag and "vocab_gap" not in ms:
                            unflagged[f"turn_on+{obj}"] += 1

print(f"Total actions: {total}")
print(f"Invalid action_id: {invalid}")
print(f"Grounding inject - dispenser: {dispenser_in_text}")
print(f"Grounding inject - faucet: {faucet_in_text}")
print(f"Unflagged vocab_gap combos: {len(unflagged)}")
if unflagged:
    for k, v in sorted(unflagged.items(), key=lambda x: -x[1])[:10]:
        print(f"  {k}: {v}")
print("=== DONE ===")
