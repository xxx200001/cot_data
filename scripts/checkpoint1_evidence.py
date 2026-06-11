"""checkpoint1_evidence.py — 边界证明 + G4 verdict + G2 样例"""
import json, glob, os, re, csv
from collections import defaultdict

ROOT = r"d:\微信文件\xwechat_files\wxid_mviguy0cna1m22_c0e5\msg\file\2026-06\cot_data\cot_data"
DATA = os.path.join(ROOT, "gemini_tasks_output_hm3d_atomic")
QA = os.path.join(ROOT, "qa_output")

# 读 plan
with open(os.path.join(QA, "grounding_plan.csv"), "r", encoding="utf-8") as f:
    plan_rows = list(csv.DictReader(f))
plan_keys = set(f"{r['file']}::{r['task_idx']}::{r['step_id']}" for r in plan_rows)

# 1. step 原文含 surface/receptacle/container 的条目 → 证明未被触碰
print("=" * 70)
print("PROOF 1: step 原文含 surface/receptacle/container → 未被改动")
print("-" * 70)
cnt = 0
for fpath in sorted(glob.glob(os.path.join(DATA, "**", "*.json"), recursive=True)):
    d = json.load(open(fpath, "r", encoding="utf-8"))
    rel = os.path.relpath(fpath, DATA)
    for tidx, task in enumerate(d.get("tasks", [])):
        for step in task.get("plan", []):
            orig = step.get("step", "")
            key = f"{rel}::{tidx}::{step.get('step_id')}"
            for w in ("surface", "receptacle", "container"):
                if re.search(r'\b' + w + r'\b', orig, re.I):
                    in_plan = "IN PLAN!" if key in plan_keys else "NOT in plan (correct)"
                    if cnt < 10:
                        print(f"  [{w}] step: {orig[:60]}")
                        print(f"         atomic: {step.get('atomic_step','')[:60]}")
                        print(f"         {in_plan}")
                        print()
                    cnt += 1
print(f"  Total entries with surface/receptacle/container in step: {cnt}")

# 2. step 原文含 items → 证明未被触碰
print("\n" + "=" * 70)
print("PROOF 2: step 原文含 'items' → 未被改动")
print("-" * 70)
cnt2 = 0
for fpath in sorted(glob.glob(os.path.join(DATA, "**", "*.json"), recursive=True)):
    d = json.load(open(fpath, "r", encoding="utf-8"))
    rel = os.path.relpath(fpath, DATA)
    for tidx, task in enumerate(d.get("tasks", [])):
        for step in task.get("plan", []):
            orig = step.get("step", "")
            at = step.get("atomic_step", "")
            key = f"{rel}::{tidx}::{step.get('step_id')}"
            if re.search(r'\bitems?\b', orig, re.I) and re.search(r'\bitems?\b', at, re.I):
                in_plan = "IN PLAN!" if key in plan_keys else "NOT in plan (correct)"
                if cnt2 < 10:
                    print(f"  step:   {orig[:60]}")
                    print(f"  atomic: {at[:60]}")
                    print(f"  {in_plan}")
                    print()
                cnt2 += 1
print(f"  Total: {cnt2}")

# 3. G2 改写样例 10 条
print("\n" + "=" * 70)
print("G2 SAMPLES: 10 条改写前后对照")
print("-" * 70)
g2_rows = [r for r in plan_rows if r["rule"] == "G2"]
import random
random.seed(42)
for r in random.sample(g2_rows, min(10, len(g2_rows))):
    print(f"  step:     {r['step_orig']}")
    print(f"  OLD at:   {r['old_atomic_step'][:60]}")
    print(f"  NEW at:   {r['new_atomic_step'][:60]}")
    print(f"  action:   {r['old_action']} -> {r['new_action']}")
    print()

# 4. G1 样例 10 条
print("=" * 70)
print("G1 SAMPLES: 10 条框架还原")
print("-" * 70)
g1_rows = [r for r in plan_rows if r["rule"] == "G1"]
for r in random.sample(g1_rows, min(10, len(g1_rows))):
    print(f"  step:     {r['step_orig']}")
    print(f"  OLD at:   {r['old_atomic_step'][:60]}")
    print(f"  NEW at:   {r['new_atomic_step'][:60]}")
    print(f"  action:   {r['old_action']} -> {r['new_action']}")
    print()

# 5. G3 样例 10 条
print("=" * 70)
print("G3 SAMPLES: 10 条 items 还原")
print("-" * 70)
g3_rows = [r for r in plan_rows if r["rule"] == "G3"]
for r in random.sample(g3_rows, min(10, len(g3_rows))):
    print(f"  step:     {r['step_orig']}")
    print(f"  OLD at:   {r['old_atomic_step'][:60]}")
    print(f"  NEW at:   {r['new_atomic_step'][:60]}")
    print()

# 6. G4 全部 verdict
print("=" * 70)
print("G4 VERDICTS: 全部条目")
print("-" * 70)
g4_rows = [r for r in plan_rows if r["rule"].startswith("G4")]
print(f"  Resolved: {sum(1 for r in g4_rows if r['rule']=='G4_resolved')}")
print(f"  Flag:     {sum(1 for r in g4_rows if r['rule']=='G4_flag')}")
print()
for r in g4_rows:
    tag = "RESOLVED" if r["rule"] == "G4_resolved" else "FLAG"
    print(f"  [{tag}] step: {r['step_orig'][:55]}")
    if tag == "RESOLVED":
        print(f"          new:  {r['new_atomic_step'][:55]}")
    print()
