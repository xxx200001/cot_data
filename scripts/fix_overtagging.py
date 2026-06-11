"""
修正 vocab_gap 标记:
1. kettle/stove/cooker/grill 等家电: 移除 vocab_gap:no_boil_action (turn_on 本来就对)
2. bathtub: 移除 vocab_gap:no_faucet_action (turn_on bathtub 合理)
3. fireplace 本体: 改为 assume_gas_fireplace (边界, 软标记)
4. fireplace sconce / fireplace tool set: 保留 vocab_gap:no_ignite_action
5. candle 系: 保留 vocab_gap:no_ignite_action
6. guitar: 保留 vocab_gap:no_tune_action
"""
import json, glob, os, re
from collections import defaultdict

ROOT = r"d:\微信文件\xwechat_files\wxid_mviguy0cna1m22_c0e5\msg\file\2026-06\cot_data\cot_data"
DATA = os.path.join(ROOT, "gemini_tasks_output_hm3d_atomic")

def norm(s): return s.lower().strip().replace("_", " ")

stats = defaultdict(int)
files = sorted(glob.glob(os.path.join(DATA, "**", "*.json"), recursive=True))

for fpath in files:
    with open(fpath, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    modified = False
    for t in data.get("tasks", []):
        for s in t.get("plan", []):
            objs = [v for v in s.get("labels", {}).values()]
            for aa in s.get("atomic_actions", []):
                ms = aa.get("mapping_source") or ""
                if "vocab_gap:" not in ms:
                    continue
                
                # 判断物体类别
                obj_names = [norm(o) for o in objs]
                
                # 家电族: 移除 no_boil_action
                if "vocab_gap:no_boil_action" in ms:
                    ms = ms.replace(";vocab_gap:no_boil_action", "")
                    ms = ms.replace("vocab_gap:no_boil_action;", "")
                    ms = ms.replace("vocab_gap:no_boil_action", "")
                    if ms == "": ms = None
                    aa["mapping_source"] = ms
                    stats["removed_no_boil"] += 1
                    modified = True
                
                # bathtub: 移除 no_faucet_action
                if "vocab_gap:no_faucet_action" in (aa.get("mapping_source") or ""):
                    ms2 = aa["mapping_source"]
                    ms2 = ms2.replace(";vocab_gap:no_faucet_action", "")
                    ms2 = ms2.replace("vocab_gap:no_faucet_action;", "")
                    ms2 = ms2.replace("vocab_gap:no_faucet_action", "")
                    if ms2 == "": ms2 = None
                    aa["mapping_source"] = ms2
                    stats["removed_no_faucet"] += 1
                    modified = True
                
                # fireplace 本体: no_ignite → assume_gas_fireplace
                if "vocab_gap:no_ignite_action" in (aa.get("mapping_source") or ""):
                    is_candle = any("candle" in n for n in obj_names)
                    is_sconce = any("sconce" in n for n in obj_names)
                    is_fireplace = any("fireplace" in n and "sconce" not in n for n in obj_names)
                    is_tool = any("tool set" in n or "tool_set" in n for n in obj_names)
                    
                    if is_fireplace and not is_candle and not is_sconce:
                        ms3 = aa["mapping_source"]
                        ms3 = ms3.replace("vocab_gap:no_ignite_action", "assume_gas_fireplace")
                        aa["mapping_source"] = ms3
                        stats["fireplace_softened"] += 1
                        modified = True
                    elif is_tool:
                        # fireplace tool set 也不需要点燃, turn_on 不合理但 inspect 更好
                        # 保留 vocab_gap 标记
                        stats["tool_set_kept"] += 1
                    # candle/sconce: 保留 no_ignite_action
    
    if modified:
        with open(fpath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")

print("=== vocab_gap 标记修正 ===")
for k, v in sorted(stats.items()):
    print(f"  {k}: {v}")

# 验证
print("\n=== 验证 ===")
remaining = defaultdict(int)
for fpath in files:
    d = json.load(open(fpath, "r", encoding="utf-8"))
    for t in d.get("tasks", []):
        for s in t.get("plan", []):
            objs = [v for v in s.get("labels", {}).values()]
            for aa in s.get("atomic_actions", []):
                ms = aa.get("mapping_source") or ""
                for tag in re.findall(r"vocab_gap:\w+|assume_gas_fireplace", ms):
                    for obj in objs:
                        remaining[f"{tag} + {obj}"] += 1

for k, v in sorted(remaining.items(), key=lambda x: -x[1]):
    print(f"  {k}: {v}")
