"""
语义修复脚本 - 批量修复 atomic action 数据中的语义不合理组合。
每个修复规则都会生成修改记录，并逐批 commit。

修复优先级（从最严重开始）：
Round 1: fill + 非容器物体 (bathrobe, bath_towel, tissue, paper_towel, toilet_paper)
Round 2: fluff + 家具本体 (couch, sofa, armchair, bed, sofa_chair, sofa_seat)
Round 3: smooth + crib
Round 4: turn_on + clock (wind → set_control)
Round 5: fill + 内容物而非容器 (shampoo, liquid_soap → 改物体名为 dispenser)
Round 6: fill + printer → load + printer
Round 7: load + 打包小物件 (towel, toothbrush, shampoo → place_in / store)
Round 8: plug_in + hose → attach + hose  
Round 9: turn_on + shower_wall → turn_on + shower
Round 10: load + wardrobe (方向反了)
Round 11: fill + bathrobe/bath_towel "prepare" → hang
"""

import json
import os
import glob
import copy
from collections import defaultdict
from datetime import datetime

ROOT = r"d:\微信文件\xwechat_files\wxid_mviguy0cna1m22_c0e5\msg\file\2026-06\cot_data\cot_data\gemini_tasks_output_hm3d_atomic"
LOG_DIR = r"d:\微信文件\xwechat_files\wxid_mviguy0cna1m22_c0e5\msg\file\2026-06\cot_data\cot_data\repair_logs"

os.makedirs(LOG_DIR, exist_ok=True)


def load_all_files():
    """加载所有 JSON 文件"""
    pattern = os.path.join(ROOT, "**", "*.json")
    files = sorted(glob.glob(pattern, recursive=True))
    data = {}
    for fpath in files:
        with open(fpath, "r", encoding="utf-8") as f:
            data[fpath] = json.load(f)
    return data


def save_file(fpath, data):
    """保存 JSON 文件"""
    with open(fpath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def norm(s):
    return s.lower().strip().replace("_", " ")


def apply_repairs(data_dict, repair_func, rule_name):
    """
    对所有数据应用修复函数，返回修改记录。
    repair_func(step, task, scene_id) -> list of changes or None
    """
    changes = []
    files_modified = set()

    for fpath, data in data_dict.items():
        scene_id = data.get("scene_id", "")
        for task in data.get("tasks", []):
            task_desc = task.get("task", "")
            for step in task.get("plan", []):
                step_changes = repair_func(step, task, scene_id)
                if step_changes:
                    for c in step_changes:
                        c["file"] = os.path.relpath(fpath, ROOT)
                        c["scene_id"] = scene_id
                        c["task"] = task_desc
                        c["step_id"] = step.get("step_id")
                    changes.extend(step_changes)
                    files_modified.add(fpath)

    # 保存修改后的文件
    for fpath in files_modified:
        save_file(fpath, data_dict[fpath])

    # 保存修复日志
    log = {
        "rule": rule_name,
        "timestamp": datetime.now().isoformat(),
        "total_changes": len(changes),
        "files_modified": len(files_modified),
        "changes": changes,
    }
    log_path = os.path.join(LOG_DIR, f"{rule_name}.json")
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)

    print(f"  [{rule_name}] {len(changes)} changes across {len(files_modified)} files")
    return changes


# =============================================================
# Round 1: fill + 不可 fill 的非容器物体
# bathrobe, bath towel, tissue, paper towel, toilet paper
# → 根据原始 step 语义改为更合理的动作
# =============================================================
def repair_fill_non_container(step, task, scene_id):
    """fill + bathrobe/bath_towel/tissue/paper_towel/toilet_paper → hang/place_on/store"""
    changes = []
    step_labels = step.get("labels", {})
    objects = list(step_labels.values())
    atomic_actions = step.get("atomic_actions", [])
    orig_step = step.get("step", "")
    
    bad_objects_hang = ["bathrobe", "bath towel", "bath_towel"]
    bad_objects_store = ["tissue", "paper towel", "paper_towel", "toilet paper", "toilet_paper"]
    
    for aa in atomic_actions:
        if aa.get("action_id") != "fill":
            continue
        for obj in objects:
            n = norm(obj)
            if any(b in n for b in bad_objects_hang):
                old_action = aa["action_id"]
                old_step_text = step.get("atomic_step", "")
                
                # "Prepare the bathrobe" → "Hang the bathrobe"
                aa["action_id"] = "hang"
                aa["mapping_source"] = f"semantic_repair_v5:fill_{n.replace(' ','_')}_to_hang"
                step["atomic_step"] = step["atomic_step"].replace("Fill ", "Hang ").replace("fill ", "hang ")
                
                changes.append({
                    "old_action": old_action, "new_action": "hang",
                    "object": obj,
                    "old_atomic_step": old_step_text,
                    "new_atomic_step": step["atomic_step"],
                    "reason": f"'{old_action}' on '{obj}' is semantically wrong; bathrobe/towel should be hung"
                })
                break
            elif any(b in n for b in bad_objects_store):
                old_action = aa["action_id"]
                old_step_text = step.get("atomic_step", "")
                
                # "Refill the toilet paper" → "Store the toilet paper"
                aa["action_id"] = "store"
                aa["mapping_source"] = f"semantic_repair_v5:fill_{n.replace(' ','_')}_to_store"
                step["atomic_step"] = step["atomic_step"].replace("Fill ", "Store ").replace("fill ", "store ")
                
                changes.append({
                    "old_action": old_action, "new_action": "store",
                    "object": obj,
                    "old_atomic_step": old_step_text,
                    "new_atomic_step": step["atomic_step"],
                    "reason": f"'{old_action}' on '{obj}' is semantically wrong; paper/tissue should be stored/restocked"
                })
                break
    return changes if changes else None


# =============================================================
# Round 2: fluff + 家具本体 → straighten
# 原始 step 往往是 "fluff pillows ON the couch"，
# 但原子化后变成了 "fluff the couch"（物体错了）
# =============================================================
def repair_fluff_furniture(step, task, scene_id):
    """fluff + couch/sofa/armchair/bed/sofa_chair/sofa_seat → straighten (整理家具)"""
    changes = []
    step_labels = step.get("labels", {})
    objects = list(step_labels.values())
    atomic_actions = step.get("atomic_actions", [])
    
    furniture = ["couch", "sofa", "armchair", "sofa chair", "sofa seat", "sofa_chair", "sofa_seat"]
    # 排除真正有 pillow/cushion 的情况
    
    for aa in atomic_actions:
        if aa.get("action_id") != "fluff":
            continue
        for obj in objects:
            n = norm(obj)
            # 只在物体本身是家具时修复（如果 labels 里有 pillow/cushion 就不改）
            if any(f in n for f in furniture) and not any(p in n for p in ["pillow", "cushion"]):
                # 检查 labels 里有没有 pillow
                all_labels = list(step_labels.values())
                has_pillow = any("pillow" in norm(l) or "cushion" in norm(l) for l in all_labels)
                if has_pillow:
                    continue  # labels 里有 pillow，fluff pillow on sofa 合理
                
                old_action = aa["action_id"]
                old_step_text = step.get("atomic_step", "")
                
                aa["action_id"] = "straighten"
                aa["mapping_source"] = f"semantic_repair_v5:fluff_furniture_to_straighten"
                step["atomic_step"] = step["atomic_step"].replace("Fluff ", "Straighten ").replace("fluff ", "straighten ")
                
                changes.append({
                    "old_action": old_action, "new_action": "straighten",
                    "object": obj,
                    "old_atomic_step": old_step_text,
                    "new_atomic_step": step["atomic_step"],
                    "reason": f"Cannot fluff furniture '{obj}' directly; changed to straighten"
                })
                break
    return changes if changes else None


# =============================================================
# Round 3: smooth + crib → straighten
# =============================================================
def repair_smooth_crib(step, task, scene_id):
    """smooth + crib → straighten crib"""
    changes = []
    step_labels = step.get("labels", {})
    objects = list(step_labels.values())
    atomic_actions = step.get("atomic_actions", [])
    
    for aa in atomic_actions:
        if aa.get("action_id") != "smooth":
            continue
        for obj in objects:
            if "crib" in norm(obj):
                old_action = aa["action_id"]
                old_step_text = step.get("atomic_step", "")
                
                aa["action_id"] = "straighten"
                aa["mapping_source"] = "semantic_repair_v5:smooth_crib_to_straighten"
                step["atomic_step"] = step["atomic_step"].replace("Smooth ", "Straighten ").replace("smooth ", "straighten ")
                
                changes.append({
                    "old_action": old_action, "new_action": "straighten",
                    "object": obj,
                    "old_atomic_step": old_step_text,
                    "new_atomic_step": step["atomic_step"],
                    "reason": "Crib is a frame, not fabric; smooth → straighten"
                })
                break
    return changes if changes else None


# =============================================================
# Round 4: turn_on + clock → set_control
# "Wind the clock" → "Turn on the clock" 不对
# =============================================================
def repair_turn_on_clock(step, task, scene_id):
    """turn_on + clock/wall_clock/antique_clock → set_control"""
    changes = []
    step_labels = step.get("labels", {})
    objects = list(step_labels.values())
    atomic_actions = step.get("atomic_actions", [])
    
    for aa in atomic_actions:
        if aa.get("action_id") != "turn_on":
            continue
        for obj in objects:
            n = norm(obj)
            # 匹配 clock 但排除 alarm_clock (闹钟 turn on 可接受)
            if "clock" in n and "alarm" not in n:
                old_action = aa["action_id"]
                old_step_text = step.get("atomic_step", "")
                
                aa["action_id"] = "set_control"
                aa["relation"] = None
                aa["mapping_source"] = "semantic_repair_v5:turn_on_clock_to_set_control"
                step["atomic_step"] = step["atomic_step"].replace("Turn on ", "Adjust ").replace("turn on ", "adjust ")
                
                changes.append({
                    "old_action": old_action, "new_action": "set_control",
                    "object": obj,
                    "old_atomic_step": old_step_text,
                    "new_atomic_step": step["atomic_step"],
                    "reason": "Clocks are wound/set, not turned on; → set_control"
                })
                break
    return changes if changes else None


# =============================================================
# Round 5: fill + shampoo/liquid_soap → fill + [obj] dispenser
# 修改 atomic_step 文本使语义更准确
# =============================================================
def repair_fill_content_not_container(step, task, scene_id):
    """fill + shampoo/liquid_soap → 保持 fill 但 atomic_step 加 dispenser"""
    changes = []
    step_labels = step.get("labels", {})
    objects = list(step_labels.values())
    atomic_actions = step.get("atomic_actions", [])
    
    content_items = {"shampoo": "shampoo dispenser", "liquid soap": "liquid soap dispenser", "liquid_soap": "liquid soap dispenser"}
    
    for aa in atomic_actions:
        if aa.get("action_id") != "fill":
            continue
        for obj in objects:
            n = norm(obj)
            for content, container in content_items.items():
                if content == n:
                    old_step_text = step.get("atomic_step", "")
                    
                    aa["mapping_source"] = f"semantic_repair_v5:fill_content_to_container"
                    # 修改 atomic_step 使其语义更准确
                    new_text = f"Fill the {container}."
                    step["atomic_step"] = new_text
                    
                    changes.append({
                        "old_action": "fill", "new_action": "fill",
                        "object": obj, "corrected_target": container,
                        "old_atomic_step": old_step_text,
                        "new_atomic_step": step["atomic_step"],
                        "reason": f"fill targets the container, not the content; '{obj}' → '{container}'"
                    })
                    break
    return changes if changes else None


# =============================================================
# Round 6: fill + printer → load + printer
# =============================================================
def repair_fill_printer(step, task, scene_id):
    """fill + printer → load + printer"""
    changes = []
    step_labels = step.get("labels", {})
    objects = list(step_labels.values())
    atomic_actions = step.get("atomic_actions", [])
    
    for aa in atomic_actions:
        if aa.get("action_id") != "fill":
            continue
        for obj in objects:
            if "printer" in norm(obj):
                old_action = aa["action_id"]
                old_step_text = step.get("atomic_step", "")
                
                aa["action_id"] = "load"
                aa["mapping_source"] = "semantic_repair_v5:fill_printer_to_load"
                step["atomic_step"] = step["atomic_step"].replace("Fill ", "Load ").replace("fill ", "load ").replace("Use the printer to fill items.", "Load the printer.")
                
                changes.append({
                    "old_action": old_action, "new_action": "load",
                    "object": obj,
                    "old_atomic_step": old_step_text,
                    "new_atomic_step": step["atomic_step"],
                    "reason": "Printers are loaded (with paper), not filled"
                })
                break
    return changes if changes else None


# =============================================================
# Round 7: turn_on + shower_wall → turn_on (fix object reference in atomic_step)
# =============================================================
def repair_turn_on_shower_wall(step, task, scene_id):
    """turn_on + shower_wall → atomic_step says 'shower' not 'shower wall'"""
    changes = []
    step_labels = step.get("labels", {})
    objects = list(step_labels.values())
    atomic_actions = step.get("atomic_actions", [])
    
    for aa in atomic_actions:
        if aa.get("action_id") != "turn_on":
            continue
        for obj in objects:
            if norm(obj) == "shower wall":
                old_step_text = step.get("atomic_step", "")
                
                aa["mapping_source"] = "semantic_repair_v5:shower_wall_to_shower"
                step["atomic_step"] = step["atomic_step"].replace("shower wall", "shower").replace("shower_wall", "shower")
                
                changes.append({
                    "old_action": "turn_on", "new_action": "turn_on",
                    "object": obj,
                    "old_atomic_step": old_step_text,
                    "new_atomic_step": step["atomic_step"],
                    "reason": "You turn on the shower, not the shower wall"
                })
                break
    return changes if changes else None


# =============================================================
# Round 8: plug_in + hose → attach + hose
# =============================================================
def repair_plug_in_hose(step, task, scene_id):
    """plug_in + hose → attach + hose"""
    changes = []
    step_labels = step.get("labels", {})
    objects = list(step_labels.values())
    atomic_actions = step.get("atomic_actions", [])
    
    for aa in atomic_actions:
        if aa.get("action_id") != "plug_in":
            continue
        for obj in objects:
            if "hose" in norm(obj):
                old_action = aa["action_id"]
                old_step_text = step.get("atomic_step", "")
                
                aa["action_id"] = "attach"
                aa["mapping_source"] = "semantic_repair_v5:plug_in_hose_to_attach"
                step["atomic_step"] = step["atomic_step"].replace("Plug in ", "Attach ").replace("plug in ", "attach ")
                
                changes.append({
                    "old_action": old_action, "new_action": "attach",
                    "object": obj,
                    "old_atomic_step": old_step_text,
                    "new_atomic_step": step["atomic_step"],
                    "reason": "Hoses are attached/connected, not plugged in"
                })
                break
    return changes if changes else None


# =============================================================
# Round 9: fill + cabinet → store (in cabinet)
# =============================================================
def repair_fill_cabinet(step, task, scene_id):
    """fill + cabinet → store"""
    changes = []
    step_labels = step.get("labels", {})
    objects = list(step_labels.values())
    atomic_actions = step.get("atomic_actions", [])
    
    for aa in atomic_actions:
        if aa.get("action_id") != "fill":
            continue
        for obj in objects:
            n = norm(obj)
            if n == "cabinet":
                old_action = aa["action_id"]
                old_step_text = step.get("atomic_step", "")
                
                aa["action_id"] = "store"
                aa["mapping_source"] = "semantic_repair_v5:fill_cabinet_to_store"
                step["atomic_step"] = step["atomic_step"].replace("Fill ", "Store items in ").replace("fill ", "store items in ")
                
                changes.append({
                    "old_action": old_action, "new_action": "store",
                    "object": obj,
                    "old_atomic_step": old_step_text,
                    "new_atomic_step": step["atomic_step"],
                    "reason": "Cabinets are stored into, not filled"
                })
                break
    return changes if changes else None


# =============================================================
# Round 10: fill + tissue_box / toilet_paper_dispenser / paper_towel_dispenser → store
# 这些 dispenser 是"补充"，用 store 更准确
# =============================================================
def repair_fill_dispensers(step, task, scene_id):
    """fill + tissue_box/toilet_paper_dispenser/paper_towel_dispenser → store"""
    changes = []
    step_labels = step.get("labels", {})
    objects = list(step_labels.values())
    atomic_actions = step.get("atomic_actions", [])
    
    dispenser_items = ["tissue box", "tissue_box", "toilet paper dispenser", "paper towel dispenser"]
    
    for aa in atomic_actions:
        if aa.get("action_id") != "fill":
            continue
        for obj in objects:
            n = norm(obj)
            if any(d in n for d in dispenser_items):
                old_action = aa["action_id"]
                old_step_text = step.get("atomic_step", "")
                
                aa["action_id"] = "store"
                aa["mapping_source"] = "semantic_repair_v5:fill_dispenser_to_store"
                step["atomic_step"] = step["atomic_step"].replace("Fill ", "Restock ").replace("fill ", "restock ")
                
                changes.append({
                    "old_action": old_action, "new_action": "store",
                    "object": obj,
                    "old_atomic_step": old_step_text,
                    "new_atomic_step": step["atomic_step"],
                    "reason": f"Dispensers are restocked/stored, not filled with liquid"
                })
                break
    return changes if changes else None


# =============================================================
# Round 11: load + wardrobe (方向反了)
# "Pack clothes FROM wardrobe" → "Load items INTO wardrobe" 方向错误
# → pick_up (从衣柜取东西)
# =============================================================
def repair_load_wardrobe(step, task, scene_id):
    """load + wardrobe → pick_up (if packing FROM wardrobe)"""
    changes = []
    step_labels = step.get("labels", {})
    objects = list(step_labels.values())
    atomic_actions = step.get("atomic_actions", [])
    orig_step = step.get("step", "")
    
    for aa in atomic_actions:
        if aa.get("action_id") != "load":
            continue
        for obj in objects:
            if "wardrobe" in norm(obj):
                # 检查原始步骤是 "from wardrobe" 还是 "into wardrobe"
                if "from" in orig_step.lower():
                    old_action = aa["action_id"]
                    old_step_text = step.get("atomic_step", "")
                    
                    aa["action_id"] = "pick_up"
                    aa["mapping_source"] = "semantic_repair_v5:load_from_wardrobe_to_pick_up"
                    step["atomic_step"] = f"Pick up items from the {obj}."
                    
                    changes.append({
                        "old_action": old_action, "new_action": "pick_up",
                        "object": obj,
                        "old_atomic_step": old_step_text,
                        "new_atomic_step": step["atomic_step"],
                        "reason": "Direction reversed: packing FROM wardrobe should be pick_up, not load INTO"
                    })
                    break
    return changes if changes else None


def main():
    print("=" * 70)
    print("Semantic Repair Pipeline")
    print("=" * 70)
    
    print("\nLoading all files...")
    data = load_all_files()
    print(f"Loaded {len(data)} files\n")
    
    # 按优先级执行修复
    repairs = [
        ("R01_fill_non_container", repair_fill_non_container),
        ("R02_fluff_furniture", repair_fluff_furniture),
        ("R03_smooth_crib", repair_smooth_crib),
        ("R04_turn_on_clock", repair_turn_on_clock),
        ("R05_fill_content_not_container", repair_fill_content_not_container),
        ("R06_fill_printer", repair_fill_printer),
        ("R07_turn_on_shower_wall", repair_turn_on_shower_wall),
        ("R08_plug_in_hose", repair_plug_in_hose),
        ("R09_fill_cabinet", repair_fill_cabinet),
        ("R10_fill_dispensers", repair_fill_dispensers),
        ("R11_load_from_wardrobe", repair_load_wardrobe),
    ]
    
    total = 0
    for name, func in repairs:
        changes = apply_repairs(data, func, name)
        total += len(changes)
    
    print(f"\n{'=' * 70}")
    print(f"Total repairs: {total}")
    print(f"Logs saved to: {LOG_DIR}")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    main()
