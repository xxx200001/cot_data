import json, glob, os
ROOT = r"d:\微信文件\xwechat_files\wxid_mviguy0cna1m22_c0e5\msg\file\2026-06\cot_data\cot_data\gemini_tasks_output_hm3d_atomic"
cnt = 0
for fpath in glob.glob(os.path.join(ROOT, "**", "*.json"), recursive=True):
    d = json.load(open(fpath, "r", encoding="utf-8"))
    for t in d.get("tasks", []):
        for s in t.get("plan", []):
            for aa in s.get("atomic_actions", []):
                ms = aa.get("mapping_source") or ""
                if "vocab_gap:roll" in ms:
                    print(s.get("step", ""), "||", aa["action_id"])
                    cnt += 1
print("Total:", cnt)
