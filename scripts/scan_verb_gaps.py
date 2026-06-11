"""扫描 step 原文动词，找出词表外的高频意图"""
import json, glob, os, re
from collections import defaultdict

ROOT = r"d:\微信文件\xwechat_files\wxid_mviguy0cna1m22_c0e5\msg\file\2026-06\cot_data\cot_data\gemini_tasks_output_hm3d_atomic"

step_verbs = defaultdict(int)
verb_examples = defaultdict(list)
verb_actions = defaultdict(lambda: defaultdict(int))  # verb -> action_id -> count

for f in glob.glob(os.path.join(ROOT, "**", "*.json"), recursive=True):
    d = json.load(open(f, "r", encoding="utf-8"))
    for t in d.get("tasks", []):
        for s in t.get("plan", []):
            step = s.get("step", "")
            m = re.match(r"^(\w+)\s", step)
            if m:
                v = m.group(1).lower()
                step_verbs[v] += 1
                if len(verb_examples[v]) < 3:
                    verb_examples[v].append(step[:90])
                for aa in s.get("atomic_actions", []):
                    verb_actions[v][aa["action_id"]] += 1

existing = {"wipe","straighten","pick_up","turn_on","inspect","place_on","scrub","dust",
    "reposition","open","close","push","smooth","carry","fluff","lift","place_in",
    "dump","set_control","turn_off","store","hang","fold","set_up","load","pour",
    "fill","rinse","polish","align","start_machine","stack","vacuum","set","plug_in",
    "dispose","shake_out","cover","pull","tighten","lock","attach","flush","mop",
    "tuck","press","unplug","unlock","pack"}

skip = {"the","a","an","and","to","in","on","for","with","from","if","make","do","ensure",
        "use","check","go","take","bring","put","get","remove","prepare","empty","organize",
        "arrange","clean","wash","dry","sweep","sort","replace","refill","adjust","move",
        "gather","collect","clear","trim","water","spray","change","switch","plump"}

print("Step verbs NOT in 49-action vocab (freq >= 10):")
print(f"{'Verb':<20} {'Count':<8} {'Mapped to':<30} Examples")
print("-" * 120)
for v, cnt in sorted(step_verbs.items(), key=lambda x: -x[1]):
    if v not in existing and v not in skip and cnt >= 10:
        top_actions = sorted(verb_actions[v].items(), key=lambda x: -x[1])[:3]
        mapped = ", ".join(f"{a}({c})" for a, c in top_actions)
        exs = verb_examples[v][0][:50] if verb_examples[v] else ""
        print(f"{v:<20} {cnt:<8} {mapped:<30} {exs}")
