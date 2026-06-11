"""
scan_vague_refs.py — 扫描 atomic_step 中的泛化指代问题
目标: 找出 atomic_step 用了 "items"/"receptacle"/"object"/"thing"/"it"/"device" 等
      泛化词,而 step 原文和 labels 里有具体名词的条目。
"""
import json, glob, os, re
from collections import defaultdict

ROOT = r"d:\微信文件\xwechat_files\wxid_mviguy0cna1m22_c0e5\msg\file\2026-06\cot_data\cot_data"
DATA = os.path.join(ROOT, "gemini_tasks_output_hm3d_atomic")

# 泛化词白名单 (这些词出现在 atomic_step 里就可疑)
VAGUE_WORDS = [
    r"\bitems?\b", r"\breceptacle\b", r"\bobjects?\b", r"\bthings?\b",
    r"\bdevice\b", r"\bsurface\b", r"\barea\b", r"\bspot\b",
    r"\bcontainer\b", r"\bfurniture\b", r"\bappliance\b",
    r"\bbelongings\b", r"\bstuff\b",
]
VAGUE_RE = re.compile("|".join(VAGUE_WORDS), re.I)

results = []
stats = defaultdict(int)

for fpath in sorted(glob.glob(os.path.join(DATA, "**", "*.json"), recursive=True)):
    d = json.load(open(fpath, "r", encoding="utf-8"))
    rel = os.path.relpath(fpath, DATA)
    
    for tidx, task in enumerate(d.get("tasks", [])):
        for step in task.get("plan", []):
            orig = step.get("step", "")
            at = step.get("atomic_step", "")
            labels = list(step.get("labels", {}).values())
            
            # 在 atomic_step 里找泛化词
            matches = VAGUE_RE.findall(at)
            if matches:
                # 检查 step 原文或 labels 里是否有更具体的名词
                vague_in_at = [m.lower() for m in matches]
                results.append({
                    "file": rel, "task_idx": tidx, "step_id": step.get("step_id"),
                    "step": orig, "atomic_step": at,
                    "labels": ", ".join(labels),
                    "vague_words": ", ".join(vague_in_at),
                    "action_id": step["atomic_actions"][0]["action_id"] if step.get("atomic_actions") else "?"
                })
                for w in vague_in_at:
                    stats[w] += 1

print(f"=== 泛化指代扫描 ===")
print(f"Total hits: {len(results)}")
print(f"\n泛化词频次:")
for k, v in sorted(stats.items(), key=lambda x: -x[1]):
    print(f"  {k}: {v}")

# 打印样本
print(f"\n=== 前 30 条样本 ===")
for r in results[:30]:
    print(f"  step:   {r['step'][:70]}")
    print(f"  atomic: {r['atomic_step'][:70]}")
    print(f"  labels: {r['labels'][:50]}")
    print(f"  vague:  {r['vague_words']}  action: {r['action_id']}")
    print()

# 保存完整结果
import csv
out = os.path.join(ROOT, "qa_output", "vague_refs_scan.csv")
if results:
    with open(out, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(results[0].keys()))
        w.writeheader()
        w.writerows(results)
    print(f"Full scan saved to: {out}")
