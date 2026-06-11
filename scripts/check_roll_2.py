import json, glob, os, re
ROOT = r"d:\微信文件\xwechat_files\wxid_mviguy0cna1m22_c0e5\msg\file\2026-06\cot_data\cot_data\gemini_tasks_output_hm3d_atomic"
cnt = 0
for fpath in glob.glob(os.path.join(ROOT, "**", "*.json"), recursive=True):
    d = json.load(open(fpath, "r", encoding="utf-8"))
    for t in d.get("tasks", []):
        for s in t.get("plan", []):
            orig = s.get("step", "")
            for aa in s.get("atomic_actions", []):
                aid = aa["action_id"]
                # 尝试用开头匹配
                m = re.match(r"^([\w-]+)\s", orig)
                if m:
                    verb0 = m.group(1).lower()
                    if verb0 in ("roll", "unroll", "lint-roll") and aid in ("carry", "smooth", "inspect", "straighten"):
                        print(f"[{aid}] {orig}")
                        cnt += 1
                elif orig.lower().startswith("neatly roll up"):
                    if aid in ("carry", "smooth", "inspect", "straighten"):
                        print(f"[{aid}] {orig}")
                        cnt += 1
print("Total:", cnt)
