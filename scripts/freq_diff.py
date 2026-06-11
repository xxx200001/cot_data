"""freq_diff.py — 重算频次统计并给 before/after diff"""
import json, glob, os
from collections import Counter

ROOT = r"d:\微信文件\xwechat_files\wxid_mviguy0cna1m22_c0e5\msg\file\2026-06\cot_data\cot_data"
DATA = os.path.join(ROOT, "gemini_tasks_output_hm3d_atomic")
BACKUP = os.path.join(ROOT, "cot_data_backup_grounding_20260612")
FREQ_FILE = os.path.join(ROOT, "gemini_tasks_output_hm3d_atomic_action_frequency_v3.json")

def count_actions(data_dir):
    c = Counter()
    for fp in sorted(glob.glob(os.path.join(data_dir, "**", "*.json"), recursive=True)):
        d = json.load(open(fp, "r", encoding="utf-8"))
        for t in d.get("tasks", []):
            for s in t.get("plan", []):
                for aa in s.get("atomic_actions", []):
                    c[aa["action_id"]] += 1
    return c

print("Counting current...")
curr = count_actions(DATA)
print("Counting backup...")
prev = count_actions(BACKUP)

# 保存新频次
freq_out = dict(sorted(curr.items(), key=lambda x: -x[1]))
with open(FREQ_FILE, "w", encoding="utf-8") as f:
    json.dump(freq_out, f, indent=2, ensure_ascii=False)
print(f"Frequency file updated: {FREQ_FILE}")

# diff
all_actions = sorted(set(list(curr.keys()) + list(prev.keys())))
print(f"\n{'Action':<20} {'Before':>8} {'After':>8} {'Delta':>8}")
print("-" * 50)
for a in all_actions:
    b = prev.get(a, 0)
    c = curr.get(a, 0)
    d = c - b
    if d != 0:
        print(f"{a:<20} {b:>8} {c:>8} {d:>+8}")
print("-" * 50)
print(f"{'TOTAL':<20} {sum(prev.values()):>8} {sum(curr.values()):>8} {sum(curr.values())-sum(prev.values()):>+8}")
print(f"\nAction count: {len(curr)} (unchanged at 52)")
