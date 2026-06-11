"""
扫描所有 atomic action 数据，找出动作-物体语义不合理的组合。

检查规则：
1. 动作不在合法原子动作库中（超出49个已知动作）
2. 动作与物体语义不匹配（如 fold + table, flush + chair, pour + wall 等）
3. 某些动作只适用于特定物体类别
"""

import json
import os
import glob
from collections import defaultdict, Counter

ROOT = r"d:\微信文件\xwechat_files\wxid_mviguy0cna1m22_c0e5\msg\file\2026-06\cot_data\cot_data\gemini_tasks_output_hm3d_atomic"

# ============================================================
# 原子动作库（从频率统计文件中提取的49个动作）
# ============================================================
VALID_ACTIONS = {
    "wipe", "straighten", "pick_up", "turn_on", "inspect", "place_on",
    "scrub", "dust", "reposition", "open", "close", "push", "smooth",
    "carry", "fluff", "lift", "place_in", "dump", "set_control",
    "turn_off", "store", "hang", "fold", "set_up", "load", "pour",
    "fill", "rinse", "polish", "align", "start_machine", "stack",
    "vacuum", "set", "plug_in", "dispose", "shake_out", "cover",
    "pull", "tighten", "lock", "attach", "flush", "mop", "tuck",
    "press", "unplug", "unlock", "pack"
}

# ============================================================
# 动作-物体语义约束规则
# ============================================================

# 这些动作只应施加于特定类别的物体
# key = action, value = 适合的物体关键词列表 (匹配任一即为合理)
ACTION_REQUIRES_OBJECT = {
    "flush": ["toilet", "urinal"],
    "fluff": ["pillow", "cushion", "blanket", "comforter", "duvet", "bedding", "mattress pad", "throw"],
    "fold": ["towel", "blanket", "cloth", "clothing", "sheet", "napkin", "mat", "rug", "curtain", "drape", "fabric", "laundry", "garment", "shirt", "pants", "jacket", "coat", "sweater", "linen", "comforter", "duvet", "bedspread", "quilt", "tablecloth", "bath mat", "bathmat", "shower curtain", "bed sheet"],
    "pour": ["cup", "glass", "bowl", "pot", "pan", "mug", "bottle", "pitcher", "kettle", "container", "bucket", "jug", "vase", "sink", "bathtub", "watering can", "planter"],
    "fill": ["cup", "glass", "bowl", "pot", "pan", "mug", "bottle", "pitcher", "kettle", "container", "bucket", "jug", "vase", "sink", "bathtub", "watering can", "planter", "tank", "tub", "basin", "washer", "washing machine", "dishwasher", "humidifier"],
    "rinse": ["cup", "glass", "bowl", "pot", "pan", "mug", "plate", "dish", "sink", "bathtub", "tub", "cloth", "towel", "sponge", "brush", "utensil", "fork", "knife", "spoon", "cutting board", "colander", "container", "bottle", "jar", "hands", "face", "fruit", "vegetable"],
    "smooth": ["sheet", "blanket", "bedspread", "comforter", "duvet", "tablecloth", "fabric", "curtain", "drape", "cloth", "towel", "rug", "mat", "pillow", "cushion", "linen", "bed sheet", "quilt", "cover", "napkin", "bed", "mattress", "couch", "sofa"],
    "tuck": ["sheet", "blanket", "bedspread", "comforter", "duvet", "bed", "mattress", "pillow", "cushion", "linen", "quilt", "cover", "curtain", "tablecloth"],
    "shake_out": ["rug", "mat", "towel", "blanket", "cloth", "sheet", "tablecloth", "curtain", "drape", "pillow", "cushion", "duvet", "comforter", "bathmat", "bath mat", "doormat", "carpet"],
    "load": ["washer", "washing machine", "dryer", "dishwasher", "oven", "microwave", "machine"],
    "start_machine": ["washer", "washing machine", "dryer", "dishwasher", "machine", "appliance"],
    "mop": ["floor", "tile", "ground"],
    "vacuum": ["floor", "carpet", "rug", "mat", "ground", "couch", "sofa", "chair", "bed", "mattress", "curtain"],
    "plug_in": ["lamp", "light", "appliance", "charger", "device", "machine", "heater", "fan", "iron", "blender", "toaster", "coffee maker", "kettle", "vacuum", "computer", "monitor", "tv", "television", "radio", "speaker", "printer"],
    "unplug": ["lamp", "light", "appliance", "charger", "device", "machine", "heater", "fan", "iron", "blender", "toaster", "coffee maker", "kettle", "vacuum", "computer", "monitor", "tv", "television", "radio", "speaker", "printer"],
    "lock": ["door", "window", "cabinet", "drawer", "gate", "lock", "safe", "box", "chest", "padlock"],
    "unlock": ["door", "window", "cabinet", "drawer", "gate", "lock", "safe", "box", "chest", "padlock"],
    "hang": ["towel", "cloth", "clothing", "coat", "jacket", "shirt", "pants", "hanger", "picture", "painting", "frame", "mirror", "curtain", "drape", "garment", "robe", "apron", "pot holder", "key", "bag", "hat", "hook", "wreath", "decoration", "ornament", "art", "poster", "photo"],
}

# 这些动作不应施加于这些物体（黑名单模式）
ACTION_INCOMPATIBLE_OBJECT = {
    "open": ["picture", "painting", "mirror", "pillow", "cushion", "couch", "sofa", "table", "desk", "chair", "stool", "lamp", "wall", "floor", "ceiling", "rug", "carpet", "mat", "towel", "clock", "plant", "vase", "statue", "book"],
    "close": ["picture", "painting", "mirror", "pillow", "cushion", "couch", "sofa", "table", "desk", "chair", "stool", "lamp", "wall", "floor", "ceiling", "rug", "carpet", "mat", "towel", "clock", "plant", "vase", "statue", "book"],
    "turn_on": ["picture", "painting", "mirror", "pillow", "cushion", "table", "desk", "chair", "stool", "wall", "floor", "ceiling", "rug", "carpet", "mat", "towel", "clock", "plant", "vase", "statue", "book", "box", "bottle", "cup", "plate", "bowl", "basket", "shelf", "rack", "cabinet", "drawer", "door", "window", "curtain", "bed", "mattress", "blanket", "sheet"],
    "turn_off": ["picture", "painting", "mirror", "pillow", "cushion", "table", "desk", "chair", "stool", "wall", "floor", "ceiling", "rug", "carpet", "mat", "towel", "clock", "plant", "vase", "statue", "book", "box", "bottle", "cup", "plate", "bowl", "basket", "shelf", "rack", "cabinet", "drawer", "door", "window", "curtain", "bed", "mattress", "blanket", "sheet"],
    "set_control": ["picture", "painting", "mirror", "pillow", "cushion", "table", "desk", "chair", "stool", "wall", "floor", "ceiling", "rug", "carpet", "mat", "towel", "clock", "plant", "vase", "statue", "book", "box", "bottle", "cup", "plate", "bowl", "basket", "shelf", "rack", "bed", "mattress", "blanket", "sheet", "door", "window", "curtain"],
    "dump": ["lamp", "light", "picture", "painting", "mirror", "pillow", "cushion", "couch", "sofa", "table", "desk", "chair", "stool", "wall", "floor", "ceiling", "bed", "mattress", "door", "window"],
    "scrub": ["lamp", "light", "picture", "painting", "pillow", "cushion", "couch", "sofa", "chair", "stool", "bed", "mattress", "blanket", "sheet", "book", "electronics", "computer", "monitor", "tv", "keyboard", "mouse"],
    "stack": ["lamp", "light", "picture", "painting", "mirror", "couch", "sofa", "chair", "stool", "bed", "mattress", "door", "window", "wall", "floor", "ceiling", "rug", "carpet", "curtain", "sink", "toilet", "bathtub", "shower"],
    "carry": ["wall", "floor", "ceiling", "door", "window", "sink", "toilet", "bathtub", "shower", "oven", "refrigerator", "dishwasher", "washing machine", "dryer", "couch", "sofa", "bed", "bathtub", "staircase"],
    "lift": ["wall", "floor", "ceiling", "door", "window", "sink", "toilet", "bathtub", "shower", "oven", "refrigerator", "dishwasher", "washing machine", "dryer", "couch", "sofa", "bed", "table", "desk", "staircase", "mirror", "painting", "picture"],
    "pick_up": ["wall", "floor", "ceiling", "door", "window", "sink", "toilet", "bathtub", "shower", "oven", "refrigerator", "dishwasher", "washing machine", "dryer", "couch", "sofa", "bed", "table", "desk", "staircase", "mirror", "cabinet", "counter", "stool"],
}


def normalize_object(obj_name):
    """标准化物体名称用于匹配"""
    return obj_name.lower().strip().replace("_", " ")


def check_action_object_pair(action_id, obj_name):
    """
    检查 action-object 组合是否语义合理。
    返回 (is_problematic, reason)
    """
    norm_obj = normalize_object(obj_name)
    
    # 1. 动作不在合法列表
    if action_id not in VALID_ACTIONS:
        return True, f"UNKNOWN_ACTION: '{action_id}' 不在已知原子动作库中"
    
    # 2. 白名单检查：某些动作要求特定物体
    if action_id in ACTION_REQUIRES_OBJECT:
        allowed = ACTION_REQUIRES_OBJECT[action_id]
        matched = any(kw in norm_obj for kw in allowed)
        if not matched:
            return True, f"ACTION_REQUIRES: '{action_id}' 通常只用于 {allowed[:5]}..., 但目标物体是 '{obj_name}'"
    
    # 3. 黑名单检查：某些动作不应用于特定物体
    if action_id in ACTION_INCOMPATIBLE_OBJECT:
        blocked = ACTION_INCOMPATIBLE_OBJECT[action_id]
        for kw in blocked:
            if kw in norm_obj:
                return True, f"INCOMPATIBLE: '{action_id}' 不应用于 '{obj_name}' (matched: '{kw}')"
    
    return False, ""


def scan_all_files():
    """扫描所有 JSON 文件"""
    pattern = os.path.join(ROOT, "**", "*.json")
    files = glob.glob(pattern, recursive=True)
    
    issues = []
    action_object_pairs = Counter()  # (action, object) -> count
    total_steps = 0
    
    for fpath in sorted(files):
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            issues.append({
                "file": fpath,
                "error": f"JSON_PARSE_ERROR: {e}",
                "task": None, "step_id": None, "action_id": None, "object": None
            })
            continue
        
        tasks = data.get("tasks", [])
        scene_id = data.get("scene_id", "unknown")
        
        for task in tasks:
            task_desc = task.get("task", "")
            plan = task.get("plan", [])
            task_labels = task.get("labels", {})
            
            for step in plan:
                total_steps += 1
                step_id = step.get("step_id")
                step_text = step.get("step", "")
                atomic_step = step.get("atomic_step", "")
                step_labels = step.get("labels", {})
                atomic_actions = step.get("atomic_actions", [])
                
                # 提取该步骤涉及的物体
                objects_in_step = list(step_labels.values())
                
                for aa in atomic_actions:
                    action_id = aa.get("action_id", "")
                    
                    for obj_name in objects_in_step:
                        action_object_pairs[(action_id, obj_name)] += 1
                        
                        is_bad, reason = check_action_object_pair(action_id, obj_name)
                        if is_bad:
                            rel_path = os.path.relpath(fpath, ROOT)
                            issues.append({
                                "file": rel_path,
                                "scene_id": scene_id,
                                "task": task_desc,
                                "step_id": step_id,
                                "step": step_text,
                                "atomic_step": atomic_step,
                                "action_id": action_id,
                                "object": obj_name,
                                "reason": reason,
                            })
    
    return issues, action_object_pairs, total_steps, len(files)


def main():
    print("=" * 80)
    print("扫描原子动作-物体语义匹配问题")
    print("=" * 80)
    
    issues, pairs, total_steps, total_files = scan_all_files()
    
    print(f"\n扫描完成: {total_files} 文件, {total_steps} 步骤")
    print(f"发现 {len(issues)} 个潜在语义问题\n")
    
    # 按问题类型分组
    by_type = defaultdict(list)
    for issue in issues:
        reason = issue.get("reason", "")
        if "UNKNOWN_ACTION" in reason:
            by_type["未知动作"].append(issue)
        elif "ACTION_REQUIRES" in reason:
            by_type["动作-物体不匹配(白名单)"].append(issue)
        elif "INCOMPATIBLE" in reason:
            by_type["动作-物体不兼容(黑名单)"].append(issue)
        else:
            by_type["其他"].append(issue)
    
    # 按 (action, object) 去重统计
    deduped = defaultdict(lambda: {"count": 0, "examples": []})
    for issue in issues:
        key = (issue.get("action_id", ""), issue.get("object", ""))
        deduped[key]["count"] += 1
        deduped[key]["reason"] = issue.get("reason", "")
        if len(deduped[key]["examples"]) < 3:
            deduped[key]["examples"].append({
                "file": issue.get("file", ""),
                "task": issue.get("task", ""),
                "step": issue.get("step", ""),
                "atomic_step": issue.get("atomic_step", ""),
            })
    
    # 输出到文件
    output_path = os.path.join(os.path.dirname(ROOT), "semantic_issues_report.json")
    report = {
        "summary": {
            "total_files": total_files,
            "total_steps": total_steps,
            "total_issues": len(issues),
            "by_type": {k: len(v) for k, v in by_type.items()},
        },
        "deduped_issues": [
            {
                "action_id": k[0],
                "object": k[1],
                "count": v["count"],
                "reason": v["reason"],
                "examples": v["examples"],
            }
            for k, v in sorted(deduped.items(), key=lambda x: -x[1]["count"])
        ],
        "all_issues": issues,
    }
    
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"详细报告已保存到: {output_path}")
    
    # 打印摘要
    print("\n" + "=" * 80)
    print("按问题类型统计:")
    print("=" * 80)
    for typ, items in by_type.items():
        print(f"  {typ}: {len(items)} 条")
    
    print("\n" + "=" * 80)
    print("去重后的问题组合 (按出现次数排序，前50个):")
    print("=" * 80)
    sorted_deduped = sorted(deduped.items(), key=lambda x: -x[1]["count"])
    for i, ((action, obj), info) in enumerate(sorted_deduped[:50]):
        print(f"\n  [{i+1}] action='{action}' + object='{obj}'  (出现 {info['count']} 次)")
        print(f"      原因: {info['reason']}")
        for ex in info["examples"][:2]:
            print(f"      例子: task='{ex['task']}' | step='{ex['step']}' → atomic='{ex['atomic_step']}'")
    
    if len(sorted_deduped) > 50:
        print(f"\n  ... 还有 {len(sorted_deduped) - 50} 个组合，详见报告文件")
    
    # 额外：输出所有 (action, object) 频次到 CSV，便于进一步分析
    csv_path = os.path.join(os.path.dirname(ROOT), "action_object_pairs.csv")
    with open(csv_path, "w", encoding="utf-8") as f:
        f.write("action_id,object,count\n")
        for (action, obj), count in sorted(pairs.items(), key=lambda x: (-x[1], x[0][0])):
            f.write(f"{action},{obj},{count}\n")
    print(f"\n动作-物体组合频次已保存到: {csv_path}")


if __name__ == "__main__":
    main()
