import json

with open(r"d:\微信文件\xwechat_files\wxid_mviguy0cna1m22_c0e5\msg\file\2026-06\cot_data\cot_data\semantic_issues_report.json", "r", encoding="utf-8") as f:
    d = json.load(f)

print("=== SUMMARY ===")
print(json.dumps(d["summary"], indent=2, ensure_ascii=False))
print()

items = d["deduped_issues"]
print(f"=== DEDUPED ISSUES (total: {len(items)}) ===")

# Categorize
true_issues = []
false_positives = []

for x in items:
    action = x["action_id"]
    obj = x["object"]
    reason = x["reason"]
    count = x["count"]
    examples = x["examples"]
    
    # 判断是否真问题还是规则过严导致的误报
    # 先全部打印，让用户判断
    print(f"\n  action='{action}' + object='{obj}'  (count={count})")
    print(f"    reason: {reason}")
    for ex in examples[:2]:
        print(f"    ex: step='{ex['step']}' -> atomic='{ex['atomic_step']}'")
