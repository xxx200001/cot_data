"""apply_unparsed.py — 应用 unparsed verdicts (G1_fix + G2_tidy)"""
import json, csv, os, glob, re
from collections import Counter

ROOT = r"d:\微信文件\xwechat_files\wxid_mviguy0cna1m22_c0e5\msg\file\2026-06\cot_data\cot_data"
DATA = os.path.join(ROOT, "gemini_tasks_output_hm3d_atomic")
QA = os.path.join(ROOT, "qa_output")
MARK = "referent_grounding_v1"

# 读 verdicts
with open(os.path.join(QA, "g_unparsed_verdicts.csv"), "r", encoding="utf-8-sig") as f:
    verdicts = list(csv.DictReader(f))

# 只应用 G1_fix 和 G2_tidy
fixable = [v for v in verdicts if v["verdict"] in ("G1_fix", "G2_tidy")]
flag_only = [v for v in verdicts if v["verdict"] == "FLAG"]

print(f"Fixable: {len(fixable)} | FLAG (skip): {len(flag_only)}")

# 按文件分组
by_file = {}
for v in fixable:
    frel = v["file"]
    if frel not in by_file: by_file[frel] = []
    by_file[frel].append(v)

applied = 0
skipped = 0
changes = []

for frel, vs in by_file.items():
    fp = os.path.join(DATA, frel)
    d = json.load(open(fp, "r", encoding="utf-8"))
    modified = False
    
    for v in vs:
        ti = int(v["task_idx"])
        sid = int(v["step_id"])
        task = d["tasks"][ti]
        st = next((s for s in task["plan"] if s.get("step_id") == sid), None)
        if not st:
            print(f"  SKIP (not found): {frel} t{ti} s{sid}")
            skipped += 1
            continue
        
        aas = st.get("atomic_actions", [])
        if not aas:
            skipped += 1
            continue
        
        a0 = aas[0]
        ms = a0.get("mapping_source") or ""
        
        # 幂等检查
        if f"{MARK}:unparsed" in ms:
            skipped += 1
            continue
        
        old_at = st.get("atomic_step", "")
        old_aid = a0["action_id"]
        old_rel = a0.get("relation")
        
        # 验证当前状态匹配
        if old_at != v["atomic_step"]:
            print(f"  SKIP (mismatch): {frel} t{ti} s{sid}")
            print(f"    expected: {v['atomic_step'][:50]}")
            print(f"    actual:   {old_at[:50]}")
            skipped += 1
            continue
        
        new_aid = v["new_action"]
        new_at = v["new_text"]
        
        # 设置 relation
        if new_aid in ("place_in", "store"):
            new_rel = "in"
        elif new_aid in ("place_on",):
            new_rel = "on"
        elif new_aid == "fill":
            new_rel = "at"
        elif new_aid in ("straighten", "reposition", "align"):
            new_rel = None
        elif new_aid == "fold":
            # fold 保留原 relation 如果有 on/in
            if "on" in v.get("note", ""): new_rel = "on"
            elif "in" in v.get("note", ""): new_rel = "in"
            else: new_rel = old_rel
        else:
            new_rel = old_rel
        
        st["atomic_step"] = new_at
        a0["action_id"] = new_aid
        a0["relation"] = new_rel
        a0["mapping_source"] = ms + f";{MARK}:unparsed"
        
        changes.append({
            "file": frel, "task_idx": ti, "step_id": sid,
            "step": v["step"], "verdict": v["verdict"],
            "old_action": old_aid, "new_action": new_aid,
            "old_text": old_at, "new_text": new_at,
            "old_relation": str(old_rel), "new_relation": str(new_rel),
            "note": v["note"]
        })
        applied += 1
        modified = True
    
    if modified:
        with open(fp, "w", encoding="utf-8") as f:
            json.dump(d, f, indent=2, ensure_ascii=False)

# 保存 changes
out = os.path.join(QA, "changes_unparsed.csv")
with open(out, "w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(changes[0].keys()) if changes else [])
    w.writeheader()
    w.writerows(changes)

print(f"\nApplied: {applied} | Skipped: {skipped}")
print(f"Changes: {out}")

# 统计
vc = Counter(c["verdict"] for c in changes)
ac = Counter(c["new_action"] for c in changes)
print(f"\nBy verdict: {dict(vc)}")
print(f"By new_action: {dict(ac)}")
