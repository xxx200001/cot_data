"""
deep_vague.py — 深入分析三类泛化指代, 找出可批量修复的模式
"""
import json, glob, os, re
from collections import defaultdict

ROOT = r"d:\微信文件\xwechat_files\wxid_mviguy0cna1m22_c0e5\msg\file\2026-06\cot_data\cot_data"
DATA = os.path.join(ROOT, "gemini_tasks_output_hm3d_atomic")

def norm(s): return s.lower().strip().replace("_", " ")

# 1. items_bug 模式分析 (1021 条)
print("=== items_bug 模式分析 ===")
items_patterns = defaultdict(int)
items_samples = defaultdict(list)

for fpath in sorted(glob.glob(os.path.join(DATA, "**", "*.json"), recursive=True)):
    d = json.load(open(fpath, "r", encoding="utf-8"))
    for t in d.get("tasks", []):
        for s in t.get("plan", []):
            at = s.get("atomic_step", "")
            orig = s.get("step", "")
            labels = list(s.get("labels", {}).values())
            
            if re.search(r"\bitems?\b", at.lower()) and not re.search(r"\bitems?\b", orig.lower()):
                # step 里明确的受事
                step_obj_m = re.search(r"(?:the|some|all)\s+([\w\s]+?)(?:\s+(?:in|on|into|from|to|back|away|off|out|up)\b|\.)", orig, re.I)
                step_obj = step_obj_m.group(1).strip() if step_obj_m else "?"
                aid = s["atomic_actions"][0]["action_id"] if s.get("atomic_actions") else "?"
                
                pattern = f"{aid}: items <- {step_obj}"
                items_patterns[pattern] += 1
                if len(items_samples[pattern]) < 2:
                    items_samples[pattern].append((orig[:60], at[:60], labels[0] if labels else "?"))

print("Top 20 patterns:")
for p, c in sorted(items_patterns.items(), key=lambda x: -x[1])[:20]:
    print(f"  [{c:3d}] {p}")
    for orig, at, lab in items_samples[p]:
        print(f"        step: {orig}  |  atomic: {at}  |  label: {lab}")

# 2. receptacle_bug 模式 (718 条)
print("\n=== receptacle_bug 模式分析 ===")
rec_patterns = defaultdict(int)
rec_samples = defaultdict(list)

for fpath in sorted(glob.glob(os.path.join(DATA, "**", "*.json"), recursive=True)):
    d = json.load(open(fpath, "r", encoding="utf-8"))
    for t in d.get("tasks", []):
        for s in t.get("plan", []):
            at = s.get("atomic_step", "")
            orig = s.get("step", "")
            labels = list(s.get("labels", {}).values())
            
            if "receptacle" in at.lower() and "receptacle" not in orig.lower():
                aid = s["atomic_actions"][0]["action_id"] if s.get("atomic_actions") else "?"
                rec_patterns[aid] += 1
                if len(rec_samples[aid]) < 3:
                    rec_samples[aid].append((orig[:60], at[:60], labels[0] if labels else "?"))

print("By action:")
for a, c in sorted(rec_patterns.items(), key=lambda x: -x[1]):
    print(f"  [{c:3d}] {a}")
    for orig, at, lab in rec_samples[a]:
        print(f"        step: {orig}  |  atomic: {at}  |  label: {lab}")

# 3. surface_template (3437): 是否都是 "Place X on surface" 句式
print("\n=== surface_template 句式分析 ===")
surf_patterns = defaultdict(int)
for fpath in sorted(glob.glob(os.path.join(DATA, "**", "*.json"), recursive=True)):
    d = json.load(open(fpath, "r", encoding="utf-8"))
    for t in d.get("tasks", []):
        for s in t.get("plan", []):
            at = s.get("atomic_step", "")
            orig = s.get("step", "")
            if "surface" in at.lower() and "surface" not in orig.lower():
                aid = s["atomic_actions"][0]["action_id"] if s.get("atomic_actions") else "?"
                m = re.match(r"(\w+)\s+(.+?)\s+on\s+surface\.", at, re.I)
                if m:
                    surf_patterns[f"{m.group(1)} X on surface"] += 1
                else:
                    surf_patterns[f"other: {at[:40]}"] += 1

for p, c in sorted(surf_patterns.items(), key=lambda x: -x[1])[:10]:
    print(f"  [{c:4d}] {p}")
