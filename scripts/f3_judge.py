"""F3: 69 条 repair 逐条判定 → 写入 f3_repair_verdicts_judged.csv"""
import csv, os

QA = r"d:\微信文件\xwechat_files\wxid_mviguy0cna1m22_c0e5\msg\file\2026-06\cot_data\cot_data\qa_output"

# 读原始
with open(os.path.join(QA, "f3_repair_verdicts.csv"), "r", encoding="utf-8") as f:
    rows = list(csv.DictReader(f))

# 判定规则:
# - 修理电器(fan/lamp/dishwasher/printer/appliance): 无法用 49 词表内动作近似 → FLAG
# - 修理有铰链/连接件的(cabinet door/hinge/drawer track/handle): tighten
# - 修理管道/排水(sink pipes/drain/connection): tighten (拧紧管件)
# - 修理固定结构(fence/shelf/rack/beam/bench): tighten (拧紧螺丝)
# - 修理可调整位置的(mirror/coat rack): align
# - 修理通风设备(vent/ventilation): tighten
# - 其他通用(cabinet/sink/toilet/dresser/piano/fireplace): FLAG (无法判定具体修理操作)

TIGHTEN_OBJECTS = {
    "cabinet door", "cabinet drawer", "hinge", "drawer track", "handle",
    "fence", "shelf", "rack", "support beam", "bench",
    "sink", "vent", "ventilation", "locker", "fireplace utensil",
    "wash cabinet", "sink cabinet", "bath cabinet", "kitchen lower cabinet",
    "copier machine",
}

ALIGN_OBJECTS = {"mirror", "light fixture", "coat rack"}

FLAG_OBJECTS = {
    "fan", "lamp", "wall lamp", "dishwasher", "kitchen appliance", "appliance",
    "printer", "cabinet", "toilet", "dresser", "toaster", "machine",
    "telephone", "keyboard", "heater", "piano", "fireplace", "tap",
}

for row in rows:
    obj = row["objects"].lower().strip()
    step = row["step_orig"].lower()
    old_act = row["old_action"]
    
    # 特殊: step 里有 hinge/pipes/drain/connection/track/handle → tighten
    if any(kw in step for kw in ("hinge", "pipe", "drain", "connection", "track", "handle")):
        row["verdict"] = "REMAP"
        row["new_action"] = "tighten"
        row["reason"] = "step mentions fastener/fitting component"
    elif obj in ALIGN_OBJECTS:
        row["verdict"] = "REMAP"
        row["new_action"] = "align"
        row["reason"] = f"{obj} repair = realignment"
    elif obj in TIGHTEN_OBJECTS or any(t in obj for t in ("cabinet door", "drawer", "rack", "bench", "fence", "beam", "vent", "sink")):
        row["verdict"] = "REMAP"
        row["new_action"] = "tighten"
        row["reason"] = f"{obj} repair = tightening screws/bolts"
    elif old_act == "turn_on":
        row["verdict"] = "FLAG"
        row["new_action"] = old_act  # keep
        row["reason"] = f"electrical {obj}, repair intent unclear in action space"
    else:
        row["verdict"] = "FLAG"
        row["new_action"] = old_act  # keep
        row["reason"] = f"{obj} repair too ambiguous for single atomic action"

# 统计
from collections import Counter
verdicts = Counter(r["verdict"] for r in rows)
remap_actions = Counter(r["new_action"] for r in rows if r["verdict"] == "REMAP")

print(f"Total: {len(rows)}")
print(f"Verdicts: {dict(verdicts)}")
print(f"Remap targets: {dict(remap_actions)}")

# 保存
out = os.path.join(QA, "f3_repair_verdicts_judged.csv")
with open(out, "w", encoding="utf-8", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
    w.writeheader()
    w.writerows(rows)
print(f"\nSaved: {out}")

# 打印 FLAG 的
print("\n=== FLAG entries (no remap) ===")
for r in rows:
    if r["verdict"] == "FLAG":
        print(f"  {r['step_orig'][:60]} | {r['old_action']} | {r['reason']}")

print("\n=== REMAP entries ===")
for r in rows:
    if r["verdict"] == "REMAP":
        print(f"  {r['step_orig'][:60]} | {r['old_action']} -> {r['new_action']} | {r['reason']}")
