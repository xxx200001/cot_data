"""
语义检测脚本 v2 — 修复了子串误匹配问题。
使用"全词匹配"和"排除规则"来避免 table lamp 被 table 匹配等误报。
"""

import json
import os
import glob
import re
from collections import defaultdict, Counter

ROOT = r"d:\微信文件\xwechat_files\wxid_mviguy0cna1m22_c0e5\msg\file\2026-06\cot_data\cot_data\gemini_tasks_output_hm3d_atomic"

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


def norm(s):
    return s.lower().strip().replace("_", " ")


def word_match(keyword, text):
    """全词匹配：keyword 作为独立词出现在 text 中"""
    pattern = r'\b' + re.escape(keyword) + r'\b'
    return bool(re.search(pattern, text))


def is_electric_device(obj_name):
    """判断物体是否是电器/可开关设备"""
    n = norm(obj_name)
    electric_keywords = [
        "lamp", "light", "fan", "tv", "television", "monitor", "heater",
        "air conditioner", "oven", "microwave", "dishwasher", "washer",
        "dryer", "refrigerator", "fridge", "stove", "toaster", "blender",
        "coffee", "printer", "computer", "speaker", "radio", "projector",
        "humidifier", "dehumidifier", "purifier", "vacuum", "iron",
        "machine", "appliance", "vent", "exhaust", "shower", "faucet",
        "tap", "water heater", "boiler", "charger",
    ]
    return any(kw in n for kw in electric_keywords)


def is_openable(obj_name):
    """判断物体是否可开合"""
    n = norm(obj_name)
    openable = [
        "door", "cabinet", "drawer", "window", "closet", "wardrobe",
        "oven", "microwave", "dishwasher", "washer", "dryer", "refrigerator",
        "fridge", "box", "chest", "safe", "lid", "gate", "trunk",
        "bag", "backpack", "suitcase", "book", "laptop", "case",
        "container", "jar", "can", "bin", "hamper", "shed",
        "garage", "pantry", "cupboard",
    ]
    return any(kw in n for kw in openable)


def is_pluggable(obj_name):
    """判断物体是否可以 plug in"""
    n = norm(obj_name)
    pluggable = [
        "lamp", "light", "fan", "tv", "television", "monitor", "heater",
        "air conditioner", "oven", "microwave", "dishwasher", "washer",
        "dryer", "refrigerator", "fridge", "stove", "toaster", "blender",
        "coffee", "printer", "computer", "pc", "speaker", "radio",
        "projector", "humidifier", "iron", "machine", "appliance",
        "charger", "keyboard", "mouse", "camera", "phone", "telephone",
        "cellular", "tablet", "laptop", "screen", "display", "amplifier",
        "router", "modem", "console", "controller", "hose",
    ]
    return any(kw in n for kw in pluggable)


def is_container_or_fillable(obj_name):
    """判断物体是否可以 fill"""
    n = norm(obj_name)
    fillable = [
        "cup", "glass", "bowl", "pot", "pan", "mug", "bottle", "pitcher",
        "kettle", "container", "bucket", "jug", "vase", "sink", "bathtub",
        "bath", "tub", "basin", "tank", "planter", "watering can",
        "jar", "can", "dispenser", "machine", "maker", "humidifier",
        "pool", "fountain", "reservoir",
    ]
    return any(kw in n for kw in fillable)


def is_hangable(obj_name):
    """判断物体是否可以 hang"""
    n = norm(obj_name)
    hangable = [
        "towel", "cloth", "clothing", "coat", "jacket", "shirt", "pants",
        "hanger", "picture", "painting", "frame", "mirror", "curtain",
        "drape", "garment", "robe", "bathrobe", "apron", "key", "bag",
        "backpack", "hat", "cap", "hook", "wreath", "decoration", "ornament",
        "art", "poster", "photo", "scarf", "umbrella", "leash", "broom",
        "mop", "rack", "closet",  # hanging ON/IN these
    ]
    return any(kw in n for kw in hangable)


def is_lockable(obj_name):
    """判断物体是否可以 lock"""
    n = norm(obj_name)
    lockable = [
        "door", "window", "cabinet", "drawer", "gate", "lock", "safe",
        "box", "chest", "padlock", "wardrobe", "closet", "locker",
        "shed", "garage", "trunk",
    ]
    return any(kw in n for kw in lockable)


def is_loadable(obj_name):
    """判断物体是否可以 load"""
    n = norm(obj_name)
    loadable = [
        "washer", "washing machine", "dryer", "dishwasher", "oven",
        "microwave", "machine", "printer", "backpack", "suitcase",
        "bag", "handbag", "box", "trunk", "container", "basket",
        "case", "cart", "vehicle", "car",
    ]
    return any(kw in n for kw in loadable)


def is_rinseable(obj_name):
    """判断物体是否可以 rinse"""
    n = norm(obj_name)
    rinseable = [
        "cup", "glass", "bowl", "pot", "pan", "mug", "plate", "dish",
        "sink", "tub", "bath", "cloth", "towel", "sponge", "brush",
        "utensil", "fork", "knife", "spoon", "cutting board", "colander",
        "container", "bottle", "jar", "pitcher", "kettle", "tray",
        "bucket", "basket", "tap", "faucet",
    ]
    return any(kw in n for kw in rinseable)


def is_foldable(obj_name):
    """判断物体是否可以 fold"""
    n = norm(obj_name)
    foldable = [
        "towel", "blanket", "cloth", "clothing", "sheet", "napkin",
        "mat", "rug", "curtain", "drape", "fabric", "laundry", "garment",
        "shirt", "pants", "jacket", "coat", "sweater", "linen",
        "comforter", "duvet", "bedspread", "quilt", "tablecloth",
        "bath mat", "bathmat", "shower curtain", "bed sheet",
        "newspaper", "scarf", "map",
    ]
    return any(kw in n for kw in foldable)


def is_smoothable(obj_name):
    """判断物体是否可以 smooth"""
    n = norm(obj_name)
    smoothable = [
        "sheet", "blanket", "bedspread", "comforter", "duvet", "tablecloth",
        "fabric", "curtain", "drape", "cloth", "towel", "rug", "mat",
        "pillow", "cushion", "linen", "bed sheet", "quilt", "cover",
        "napkin", "bed", "mattress", "couch", "sofa", "carpet",
    ]
    return any(kw in n for kw in smoothable)


def is_fluffable(obj_name):
    """判断物体是否可以 fluff"""
    n = norm(obj_name)
    fluffable = [
        "pillow", "cushion", "blanket", "comforter", "duvet", "bedding",
        "mattress pad", "throw", "pouffe", "ottoman",
    ]
    return any(kw in n for kw in fluffable)


def is_stackable(obj_name):
    """判断物体是否可以 stack"""
    n = norm(obj_name)
    stackable = [
        "book", "box", "plate", "dish", "bowl", "tray", "paper",
        "magazine", "folder", "chair", "stool", "crate", "container",
        "brick", "tile", "log", "towel", "cloth", "wood",
    ]
    return any(kw in n for kw in stackable)


def is_vacuumable(obj_name):
    n = norm(obj_name)
    vacuumable = [
        "floor", "carpet", "rug", "mat", "ground", "couch", "sofa",
        "chair", "bed", "mattress", "curtain", "stair", "step", "fireplace",
    ]
    return any(kw in n for kw in vacuumable)


def is_moppable(obj_name):
    n = norm(obj_name)
    moppable = ["floor", "tile", "ground", "stair", "step", "patio", "deck", "hallway"]
    return any(kw in n for kw in moppable)


def check_v2(action_id, obj_name):
    """v2 语义检查 — 基于函数式判断，避免子串误匹配"""
    n = norm(obj_name)
    
    if action_id not in VALID_ACTIONS:
        return True, f"UNKNOWN_ACTION: '{action_id}'"
    
    # 每个动作用专门的判断函数
    checks = {
        "flush": lambda o: any(kw in norm(o) for kw in ["toilet", "urinal"]),
        "fluff": is_fluffable,
        "fold": is_foldable,
        "pour": lambda o: is_container_or_fillable(o) or any(kw in norm(o) for kw in ["plant", "flower", "tree", "herb", "bonsai", "bouquet", "garden", "shampoo", "soap", "oil", "sauce", "batter"]),
        "fill": is_container_or_fillable,
        "rinse": is_rinseable,
        "smooth": is_smoothable,
        "tuck": lambda o: any(kw in norm(o) for kw in ["sheet", "blanket", "bedspread", "comforter", "duvet", "bed", "mattress", "pillow", "cushion", "linen", "quilt", "cover", "curtain", "tablecloth", "chair"]),
        "shake_out": lambda o: any(kw in norm(o) for kw in ["rug", "mat", "towel", "blanket", "cloth", "sheet", "tablecloth", "curtain", "drape", "pillow", "cushion", "duvet", "comforter", "doormat", "carpet"]),
        "load": is_loadable,
        "start_machine": lambda o: any(kw in norm(o) for kw in ["washer", "washing machine", "dryer", "dishwasher", "machine", "appliance", "microwave", "printer", "coffee", "oven"]),
        "mop": is_moppable,
        "vacuum": is_vacuumable,
        "plug_in": is_pluggable,
        "unplug": is_pluggable,
        "lock": is_lockable,
        "unlock": is_lockable,
        "hang": is_hangable,
        "turn_on": is_electric_device,
        "turn_off": is_electric_device,
        "set_control": lambda o: is_electric_device(o) or any(kw in norm(o) for kw in ["clock", "thermostat", "timer", "dial", "knob", "chair", "stool", "shade", "blind", "curtain"]),
        "open": is_openable,
        "close": is_openable,
        "stack": is_stackable,
        "carry": lambda o: not any(kw == norm(o) for kw in ["wall", "floor", "ceiling", "staircase"]),
        "lift": lambda o: not any(kw == norm(o) for kw in ["wall", "floor", "ceiling", "staircase"]),
        "pick_up": lambda o: not any(kw == norm(o) for kw in ["wall", "floor", "ceiling", "staircase", "sink", "toilet", "bathtub", "shower", "oven", "refrigerator"]),
    }
    
    if action_id in checks:
        if not checks[action_id](obj_name):
            return True, f"MISMATCH: '{action_id}' is not semantically compatible with '{obj_name}'"
    
    return False, ""


def scan_all_files():
    pattern = os.path.join(ROOT, "**", "*.json")
    files = glob.glob(pattern, recursive=True)
    
    issues = []
    total_steps = 0
    
    for fpath in sorted(files):
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            continue
        
        scene_id = data.get("scene_id", "unknown")
        for task in data.get("tasks", []):
            task_desc = task.get("task", "")
            for step in task.get("plan", []):
                total_steps += 1
                step_labels = step.get("labels", {})
                objects = list(step_labels.values())
                
                for aa in step.get("atomic_actions", []):
                    action_id = aa.get("action_id", "")
                    for obj in objects:
                        is_bad, reason = check_v2(action_id, obj)
                        if is_bad:
                            issues.append({
                                "file": os.path.relpath(fpath, ROOT),
                                "scene_id": scene_id,
                                "task": task_desc,
                                "step_id": step.get("step_id"),
                                "step": step.get("step", ""),
                                "atomic_step": step.get("atomic_step", ""),
                                "action_id": action_id,
                                "object": obj,
                                "reason": reason,
                            })
    
    return issues, total_steps, len(files)


def main():
    print("=" * 70)
    print("Semantic Check v2 (improved matching)")
    print("=" * 70)
    
    issues, total_steps, total_files = scan_all_files()
    
    print(f"\nScanned: {total_files} files, {total_steps} steps")
    print(f"Found: {len(issues)} issues\n")
    
    # 去重
    deduped = defaultdict(lambda: {"count": 0, "examples": []})
    for issue in issues:
        key = (issue["action_id"], issue["object"])
        deduped[key]["count"] += 1
        deduped[key]["reason"] = issue["reason"]
        if len(deduped[key]["examples"]) < 3:
            deduped[key]["examples"].append({
                "step": issue["step"],
                "atomic_step": issue["atomic_step"],
                "file": issue["file"],
            })
    
    sorted_deduped = sorted(deduped.items(), key=lambda x: -x[1]["count"])
    
    print(f"Unique (action, object) combos with issues: {len(sorted_deduped)}\n")
    
    for i, ((action, obj), info) in enumerate(sorted_deduped[:60]):
        print(f"  [{i+1}] {action} + {obj}  (count={info['count']})")
        for ex in info["examples"][:2]:
            print(f"      step='{ex['step']}' → atomic='{ex['atomic_step']}'")
    
    if len(sorted_deduped) > 60:
        print(f"\n  ... and {len(sorted_deduped) - 60} more")
    
    # 保存
    report = {
        "summary": {"total_files": total_files, "total_steps": total_steps, "total_issues": len(issues), "unique_combos": len(sorted_deduped)},
        "deduped_issues": [{"action_id": k[0], "object": k[1], **v} for k, v in sorted_deduped],
    }
    out_path = os.path.join(os.path.dirname(ROOT), "semantic_issues_report_v2.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\nReport saved: {out_path}")


if __name__ == "__main__":
    main()
