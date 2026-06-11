"""3 条精确返工 (phone relation 已经是 on, 不需要改)"""
import json, os

DATA = r"d:\微信文件\xwechat_files\wxid_mviguy0cna1m22_c0e5\msg\file\2026-06\cot_data\cot_data\gemini_tasks_output_hm3d_atomic"

def load(fname):
    fpath = os.path.join(DATA, fname)
    with open(fpath, "r", encoding="utf-8") as f:
        return json.load(f)

def save(fname, data):
    fpath = os.path.join(DATA, fname)
    with open(fpath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")

def find_step(data, tidx, sid):
    for s in data["tasks"][tidx]["plan"]:
        if s["step_id"] == sid:
            return s
    raise ValueError(f"step_id {sid} not found")

# ============================================================
# 1. BUG: "Rinse the a in the dishwasher." → "Rinse the bowl in the dishwasher."
# ============================================================
fname = os.path.join("00757-LVgQNuK8vtv", "tasks-island_0.json")
d = load(fname)
s = find_step(d, 110, 3)
old = s["atomic_step"]
s["atomic_step"] = "Rinse the bowl in the dishwasher."
print(f"[1] BUG: '{old}' -> '{s['atomic_step']}'")
save(fname, d)

# ============================================================
# 2. ROLLBACK: "Wash the dishwasher." 不是受事漂移
# ============================================================
rollbacks = [
    (os.path.join("00022-gmuS7Wgsbrx", "tasks-island_0.json"), 276, 4),
    (os.path.join("00827-BAbdmeyTvMZ", "tasks-island_0.json"), 46, 4),
]

for fname, tidx, sid in rollbacks:
    d = load(fname)
    s = find_step(d, tidx, sid)
    old = s["atomic_step"]
    s["atomic_step"] = "Rinse the dishwasher."
    for aa in s["atomic_actions"]:
        if aa["action_id"] == "rinse":
            aa["relation"] = None
            ms = aa.get("mapping_source") or ""
            ms = ms.replace("semantic_qa_v1:fix_patient_drift_rinse",
                           "semantic_qa_v1:rollback_not_drift")
            aa["mapping_source"] = ms
    print(f"[2] ROLLBACK: {fname} t{tidx}/s{sid}: '{old}' -> 'Rinse the dishwasher.'")
    save(fname, d)

print("\nDone: 3 fixes applied")
print("(8 phone relation fixes confirmed already at 'on' - no change needed)")
