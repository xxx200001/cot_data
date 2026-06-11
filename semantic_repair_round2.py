"""
语义修复脚本 Round 2 — 修复 v2 检测发现的额外真实问题
"""

import json
import os
import glob
from collections import defaultdict
from datetime import datetime

ROOT = r"d:\微信文件\xwechat_files\wxid_mviguy0cna1m22_c0e5\msg\file\2026-06\cot_data\cot_data\gemini_tasks_output_hm3d_atomic"
LOG_DIR = r"d:\微信文件\xwechat_files\wxid_mviguy0cna1m22_c0e5\msg\file\2026-06\cot_data\cot_data\repair_logs"


def load_all_files():
    pattern = os.path.join(ROOT, "**", "*.json")
    files = sorted(glob.glob(pattern, recursive=True))
    data = {}
    for fpath in files:
        with open(fpath, "r", encoding="utf-8") as f:
            data[fpath] = json.load(f)
    return data


def save_file(fpath, data):
    with open(fpath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def norm(s):
    return s.lower().strip().replace("_", " ")


def apply_repairs(data_dict, repair_func, rule_name):
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
    for fpath in files_modified:
        save_file(fpath, data_dict[fpath])
    log = {"rule": rule_name, "timestamp": datetime.now().isoformat(), "total_changes": len(changes), "files_modified": len(files_modified), "changes": changes}
    log_path = os.path.join(LOG_DIR, f"{rule_name}.json")
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)
    print(f"  [{rule_name}] {len(changes)} changes across {len(files_modified)} files")
    return changes


# ===========================================================
# R12: turn_on + candle/candlestick/candle holder
# "Light the candle" → "Turn on the candle" 不对
# 蜡烛不是电器。但原子动作库里没有 "light"，最接近的是 "turn_on"
# 考虑到这是个合理的 mapping（没有更好的动作），标记为可接受
# 但 atomic_step 文本应该更准确
# → 保持 turn_on 但 不改（这是动作库限制）
# ===========================================================

# ===========================================================
# R12: open + archway — archway 不能 open
# ===========================================================
def repair_open_archway(step, task, scene_id):
    changes = []
    step_labels = step.get("labels", {})
    objects = list(step_labels.values())
    for aa in step.get("atomic_actions", []):
        if aa.get("action_id") != "open":
            continue
        for obj in objects:
            if "archway" in norm(obj):
                old_step_text = step.get("atomic_step", "")
                aa["action_id"] = "inspect"
                aa["mapping_source"] = "semantic_repair_v5:open_archway_to_inspect"
                step["atomic_step"] = f"Inspect the {obj}."
                changes.append({
                    "old_action": "open", "new_action": "inspect",
                    "object": obj,
                    "old_atomic_step": old_step_text,
                    "new_atomic_step": step["atomic_step"],
                    "reason": "Archways cannot be opened; changed to inspect"
                })
                break
    return changes if changes else None


# ===========================================================
# R13: set_control + guitar → 保留 (调弦合理)
# R14: set_control + keyboard/screen/telephone → 保留 (调节设备合理)
# 这些实际上都是合理的使用，不需要修复
# ===========================================================

# ===========================================================
# R15: set_control + cellular_telephone
# "Set the cellular_telephone on the desk" → set_control 不对，
# 这是 "放置" 不是 "调节"
# ===========================================================
def repair_set_control_phone_place(step, task, scene_id):
    """set_control + cellular_telephone when original step is about placing → place_on"""
    changes = []
    step_labels = step.get("labels", {})
    objects = list(step_labels.values())
    orig_step = step.get("step", "")
    
    for aa in step.get("atomic_actions", []):
        if aa.get("action_id") != "set_control":
            continue
        for obj in objects:
            n = norm(obj)
            if "cellular" in n or "telephone" in n or "phone" in n:
                # 检查原始 step 是否是 "set ... on" (放置) 而非 "adjust/dim" (调节)
                lower_step = orig_step.lower()
                if "set" in lower_step and ("on the" in lower_step or "on a" in lower_step):
                    old_action = aa["action_id"]
                    old_step_text = step.get("atomic_step", "")
                    
                    aa["action_id"] = "place_on"
                    aa["relation"] = "on"
                    aa["mapping_source"] = "semantic_repair_v5:set_phone_to_place_on"
                    step["atomic_step"] = step["atomic_step"].replace("Adjust ", "Place ").replace("adjust ", "place ")
                    
                    changes.append({
                        "old_action": old_action, "new_action": "place_on",
                        "object": obj,
                        "old_atomic_step": old_step_text,
                        "new_atomic_step": step["atomic_step"],
                        "reason": "Original step is about placing the phone on a surface, not adjusting it"
                    })
                    break
    return changes if changes else None


# ===========================================================
# R16: close + curtain rod — curtain rod 不能 close，
# 应该是 close curtain (on the rod)
# ===========================================================
def repair_close_curtain_rod(step, task, scene_id):
    changes = []
    step_labels = step.get("labels", {})
    objects = list(step_labels.values())
    for aa in step.get("atomic_actions", []):
        if aa.get("action_id") not in ("close", "open"):
            continue
        for obj in objects:
            if "curtain rod" in norm(obj):
                old_step_text = step.get("atomic_step", "")
                aa["mapping_source"] = "semantic_repair_v5:curtain_rod_to_curtain"
                # 修改 atomic_step 文本
                step["atomic_step"] = step["atomic_step"].replace("curtain rod", "curtain").replace("curtain_rod", "curtain")
                changes.append({
                    "old_action": aa["action_id"], "new_action": aa["action_id"],
                    "object": obj,
                    "old_atomic_step": old_step_text,
                    "new_atomic_step": step["atomic_step"],
                    "reason": "Curtain rod is not opened/closed; the curtain on the rod is"
                })
                break
    return changes if changes else None


# ===========================================================
# R17: stack + case — case 通常不能 stack
# 但 case 可以堆叠 (briefcase, suitcase)，保留
# ===========================================================

# ===========================================================
# R18: fill + shampoo — 上轮修了 atomic_step 但物体标签没变
# 检测规则需要覆盖 "shampoo" → 这不是真问题了 (已修文本)
# 同样 fill + liquid_soap 也已修
# ===========================================================

# ===========================================================  
# R19: turn_on + bathtub → turn_on + faucet (水龙头)
# ===========================================================
def repair_turn_on_bathtub(step, task, scene_id):
    changes = []
    step_labels = step.get("labels", {})
    objects = list(step_labels.values())
    for aa in step.get("atomic_actions", []):
        if aa.get("action_id") != "turn_on":
            continue
        for obj in objects:
            if norm(obj) == "bathtub":
                old_step_text = step.get("atomic_step", "")
                aa["mapping_source"] = "semantic_repair_v5:turn_on_bathtub_text_fix"
                step["atomic_step"] = step["atomic_step"].replace("the bathtub", "the bathtub faucet")
                changes.append({
                    "old_action": "turn_on", "new_action": "turn_on",
                    "object": obj,
                    "old_atomic_step": old_step_text,
                    "new_atomic_step": step["atomic_step"],
                    "reason": "You turn on the faucet, not the bathtub itself"
                })
                break
    return changes if changes else None


# ===========================================================
# R20: open + washing machine: "Empty the washing machine" → "Open washing machine"
# open 是合理的第一步（打开门），但 atomic_step 文本有时不对
# 保留 open，不改
# ===========================================================

# ===========================================================
# R21: open + piano — 打开钢琴盖，合理
# R22: open + umbrella — 打开雨伞，合理
# R23: open + wine_bottle — 开瓶，合理
# 以上都是 openable 白名单遗漏，不是数据问题
# ===========================================================

# ===========================================================
# R24: open + laundry machine — 合理 (打开洗衣机门)
# R25: open + attic hatch — 合理 (打开阁楼舱口)
# close + attic hatch — 合理
# close + shutter/shutters — 合理 (关百叶窗)
# close + shade/shades — 合理
# 以上都是合理操作
# ===========================================================


def main():
    print("=" * 70)
    print("Semantic Repair Pipeline - Round 2")
    print("=" * 70)
    
    print("\nLoading all files...")
    data = load_all_files()
    print(f"Loaded {len(data)} files\n")
    
    repairs = [
        ("R12_open_archway", repair_open_archway),
        ("R13_set_control_phone_place", repair_set_control_phone_place),
        ("R14_close_curtain_rod", repair_close_curtain_rod),
        ("R15_turn_on_bathtub", repair_turn_on_bathtub),
    ]
    
    total = 0
    for name, func in repairs:
        changes = apply_repairs(data, func, name)
        total += len(changes)
    
    print(f"\n{'=' * 70}")
    print(f"Round 2 total repairs: {total}")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    main()
