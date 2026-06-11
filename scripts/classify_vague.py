"""
classify_vague.py — 分类泛化指代, 区分真问题和合理表达
"""
import json, glob, os, re
from collections import defaultdict

ROOT = r"d:\微信文件\xwechat_files\wxid_mviguy0cna1m22_c0e5\msg\file\2026-06\cot_data\cot_data"
DATA = os.path.join(ROOT, "gemini_tasks_output_hm3d_atomic")

def norm(s): return s.lower().strip().replace("_", " ")

# 分类计数
cats = defaultdict(int)
true_bugs = defaultdict(list)

for fpath in sorted(glob.glob(os.path.join(DATA, "**", "*.json"), recursive=True)):
    d = json.load(open(fpath, "r", encoding="utf-8"))
    rel = os.path.relpath(fpath, DATA)
    
    for tidx, task in enumerate(d.get("tasks", [])):
        for step in task.get("plan", []):
            orig = step.get("step", "")
            at = step.get("atomic_step", "")
            labels = list(step.get("labels", {}).values())
            lab_norms = [norm(l) for l in labels]
            at_low = at.lower()
            orig_low = orig.lower()
            
            # === surface ===
            if "surface" in at_low and "surface" not in orig_low:
                # step 原文没有 surface, atomic_step 凭空加的
                # 但 place_on + "on surface" 是模板行为: "Place X on surface" 
                # 这类其实是缺少目标位置——step 说 "Arrange the books" 但没明说放在哪
                if "on surface" in at_low:
                    cats["surface_template"] += 1
                else:
                    cats["surface_other"] += 1
            
            # === items ===
            if re.search(r"\bitems?\b", at_low) and not re.search(r"\bitems?\b", orig_low):
                # step 原文有具体名词但 atomic_step 用了 items
                # 这是真 bug: "Put the books" → "Place items"
                cats["items_bug"] += 1
                if len(true_bugs["items_bug"]) < 5:
                    true_bugs["items_bug"].append((orig[:60], at[:60], ", ".join(labels)[:40]))
            elif re.search(r"\bitems?\b", at_low) and re.search(r"\bitems?\b", orig_low):
                # step 原文本身就说 items
                cats["items_faithful"] += 1
            
            # === receptacle ===
            if "receptacle" in at_low:
                if "receptacle" not in orig_low:
                    cats["receptacle_bug"] += 1
                    if len(true_bugs["receptacle_bug"]) < 5:
                        true_bugs["receptacle_bug"].append((orig[:60], at[:60], ", ".join(labels)[:40]))
                else:
                    cats["receptacle_faithful"] += 1
            
            # === step 有具体受事, atomic_step 丢失 ===
            # 核心模式: step 有 the X, labels 里有 Y, atomic_step 没提 X 也没提 Y
            if labels:
                label_in_at = any(norm(l) in at_low or l.lower() in at_low for l in labels)
                # 从 step 提取宾语
                step_nouns = re.findall(r"the\s+(\w[\w\s]*?)(?:\.|,|$)", orig, re.I)
                step_noun_in_at = any(n.strip().lower() in at_low for n in step_nouns if len(n.strip()) > 2)
                
                if not label_in_at and not step_noun_in_at:
                    # atomic_step 里既没有 label 名也没有 step 里的受事名词
                    cats["lost_patient"] += 1

print("=== 泛化指代分类 ===")
for k, v in sorted(cats.items(), key=lambda x: -x[1]):
    print(f"  {k}: {v}")

print("\n=== 真问题样本 ===")
for cat, samples in true_bugs.items():
    print(f"\n--- {cat} ---")
    for orig, at, labels in samples:
        print(f"  step:   {orig}")
        print(f"  atomic: {at}")
        print(f"  labels: {labels}")
        print()

# 更精细: items_bug 按 action 分组
print("\n=== items_bug 按 action 分组 ===")
items_by_action = defaultdict(int)
for fpath in sorted(glob.glob(os.path.join(DATA, "**", "*.json"), recursive=True)):
    d = json.load(open(fpath, "r", encoding="utf-8"))
    for t in d.get("tasks", []):
        for s in t.get("plan", []):
            at = s.get("atomic_step", "")
            orig = s.get("step", "")
            if re.search(r"\bitems?\b", at.lower()) and not re.search(r"\bitems?\b", orig.lower()):
                for aa in s.get("atomic_actions", []):
                    items_by_action[aa["action_id"]] += 1

for k, v in sorted(items_by_action.items(), key=lambda x: -x[1]):
    print(f"  {k}: {v}")
