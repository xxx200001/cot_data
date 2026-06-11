"""
grounding_dryrun.py — P0 + G1-G4 干跑, 只产出 plan.csv
D1=straighten, D2=含fluff, D3=消解, D4=reposition
"""
import json, glob, os, re, csv
from collections import defaultdict

ROOT = r"d:\微信文件\xwechat_files\wxid_mviguy0cna1m22_c0e5\msg\file\2026-06\cot_data\cot_data"
DATA = os.path.join(ROOT, "gemini_tasks_output_hm3d_atomic")
QA_OUT = os.path.join(ROOT, "qa_output")
os.makedirs(QA_OUT, exist_ok=True)

def norm(s): return s.lower().strip().replace("_", " ")
def is_phantom(word, at, step):
    return bool(re.search(r'\b' + word + r'\b', at, re.I)) and \
           not bool(re.search(r'\b' + word + r'\b', step, re.I))

FAITHFUL = {'hang':'hang','stack':'stack','store':'store','load':'load','stow':'store'}
PREP_MAP = {'in':'place_in','into':'place_in','on':'place_on','onto':'place_on'}
PREP_REL = {'in':'in','into':'in','on':'on','onto':'on'}

# P0 hardcoded
P0_ENTRIES = {
    # P0a
    ("00096-6HRFAUDqpTb\\tasks-island_0.json",77,1): ("P0a","reposition","tighten","Tighten the cabinet door.",";vocab_extension_v1:repair_remap->tighten"),
    ("00664-u5atqC7vRCY\\tasks-island_0.json",16,1): ("P0a","reposition","tighten","Tighten the support beam.",";vocab_extension_v1:repair_remap->tighten"),
    # P0b
    ("00475-g7hUFVNac26\\tasks-island_0.json",38,1): ("P0b","open","unload","Unload the laundry machine.",";vocab_extension_v1:open->unload"),
    # P0c
    ("00164-XfUxBGTFQQb\\tasks-island_0.json",65,2): ("P0c","turn_on","reposition","Reposition the fireplace tool set.",";cleanup_v1:turn_on->reposition"),
    ("00475-g7hUFVNac26\\tasks-island_0.json",0,3): ("P0c","turn_on","reposition","Reposition the fireplace tool set.",";cleanup_v1:turn_on->reposition"),
    ("00475-g7hUFVNac26\\tasks-island_0.json",503,3): ("P0c","turn_on","reposition","Reposition the fireplace tool set.",";cleanup_v1:turn_on->reposition"),
    ("00475-g7hUFVNac26\\tasks-island_0.json",513,5): ("P0c","turn_on","reposition","Reposition the fireplace tool set.",";cleanup_v1:turn_on->reposition"),
}

def parse_step_framework(step, labels):
    """从 step 解析 (verb, patient, prep, destination) 或 None"""
    lab_norms = [norm(l) for l in labels]
    step_low = step.lower()
    
    # 提取首动词
    vm = re.match(r'^(\w+)\s+', step)
    if not vm: return None
    verb = vm.group(1).lower()
    rest = step[vm.end():]
    
    # 按 label 在 prep 后出现来定位框架
    best = None
    for lab in labels:
        ln = norm(lab)
        # 尝试匹配 "prep (the)? label" 
        pat = r'\b(in|into|on|onto)\s+(the\s+)?' + re.escape(ln)
        m = re.search(pat, step_low)
        if m:
            prep = m.group(1)
            dest = lab
            # patient = verb 和 prep 之间的文本
            pre_text = step[vm.end():m.start()].strip()
            # 清理 patient
            pre_text = re.sub(r'^(the|a|an|some|all|my|your)\s+', '', pre_text, flags=re.I)
            pre_text = re.sub(r'\s+back$', '', pre_text, flags=re.I).strip()
            if pre_text:
                best = (verb, pre_text, prep, dest)
                break
    
    if best: return best
    
    # 尝试不依赖 label 的通用框架解析
    m = re.match(r'^(\w+)\s+(the\s+|a\s+|an\s+|some\s+|my\s+)?(.*?)\s+\b(back\s+)?(in|into|on|onto)\s+(the\s+)?(.*?)\.?\s*$', step, re.I)
    if m:
        verb2 = m.group(1).lower()
        patient = m.group(3).strip()
        prep = m.group(5).lower()
        dest = m.group(7).strip()
        # 去掉 dest 后面的 location clause
        dest = re.sub(r'\s+(in|on|at|near|by|from|for|with)\s+the\s+.*$', '', dest, flags=re.I)
        if patient and dest:
            return (verb2, patient, prep, dest)
    
    return None

def extract_patient_np(step):
    """从 step 提取受事名词短语(无介词框架时)"""
    m = re.match(r'^(\w+)\s+(the\s+|a\s+|an\s+|some\s+|my\s+|all\s+)?(.*?)\.?\s*$', step, re.I)
    if m:
        patient = m.group(3).strip()
        # 去掉副词
        patient = re.sub(r'\s+(neatly|carefully|properly|quickly|gently|thoroughly)\s*$', '', patient, flags=re.I)
        patient = re.sub(r'^(neatly|carefully|properly|quickly|gently|thoroughly)\s+', '', patient, flags=re.I)
        return patient
    return None

VAGUE_NPS = {'items','item','it','them','things','everything','essentials','belongings',
    'accessories','stuff','provisions','supplies','groceries','toiletries','snacks',
    'workout gear','gear','equipment','personal items','gym clothes','my clothes',
    'clothes','dirty clothes','clean clothes','wet clothes','dry clothes','laundry',
    'dishes','dirty dishes','clean dishes'}

def extract_items_patient(step):
    """从 step 提取具名受事 NP 用于替换 items (排除泛化名词)"""
    m = re.match(r'^(\w+)\s+(the\s+|a\s+|an\s+|some\s+|my\s+|all\s+)?([\w\s\']+?)\s+\b(in|into|on|onto|from|at)\s+', step, re.I)
    if m:
        patient = m.group(3).strip()
        if patient.lower() not in VAGUE_NPS:
            return patient
    return None

plan = []
stats = defaultdict(int)
g1_failed = []
g4_verdicts = []
files = sorted(glob.glob(os.path.join(DATA, "**", "*.json"), recursive=True))

for fpath in files:
    d = json.load(open(fpath, "r", encoding="utf-8"))
    rel = os.path.relpath(fpath, DATA)
    
    for tidx, task in enumerate(d.get("tasks", [])):
        for step in task.get("plan", []):
            orig = step.get("step", "")
            at = step.get("atomic_step", "")
            labels = list(step.get("labels", {}).values())
            sid = step.get("step_id")
            
            for aa in step.get("atomic_actions", []):
                aid = aa["action_id"]
                ms = aa.get("mapping_source") or ""
                rel_val = aa.get("relation")
                
                if "referent_grounding_v1" in ms: continue
                
                # === P0 ===
                p0_key = (rel.replace("/","\\"), tidx, sid)
                if p0_key in P0_ENTRIES:
                    rule, exp_old, new_aid, new_at, marker = P0_ENTRIES[p0_key]
                    if aid == exp_old or (rule == "P0c" and aid == "turn_on"):
                        plan.append({"file":rel,"task_idx":tidx,"step_id":sid,
                            "rule":rule,"old_action":aid,"new_action":new_aid,
                            "old_atomic_step":at,"new_atomic_step":new_at,
                            "relation_op":"no_change" if rule!="P0c" else "set_null",
                            "ms_op":marker, "step_orig":orig[:80]})
                        stats[rule] += 1
                    continue
                
                claimed = False
                ph_surface = is_phantom("surface", at, orig)
                ph_receptacle = is_phantom("receptacle", at, orig)
                ph_items = is_phantom("items", at, orig) or is_phantom("item", at, orig)
                ph_container = is_phantom("container", at, orig)
                
                # === G1: 框架还原 ===
                if (ph_surface or ph_receptacle) and not claimed:
                    fw = parse_step_framework(orig, labels)
                    if fw:
                        verb, patient, prep, dest = fw
                        # 动词保真
                        if verb in FAITHFUL:
                            new_aid_g1 = FAITHFUL[verb]
                            new_at_g1 = f"{verb.capitalize()} the {patient} {prep} the {dest}."
                        else:
                            new_aid_g1 = PREP_MAP.get(prep, "place_in")
                            new_at_g1 = f"Place the {patient} {prep} the {dest}."
                        new_rel_g1 = PREP_REL.get(prep, "in")
                        plan.append({"file":rel,"task_idx":tidx,"step_id":sid,
                            "rule":"G1","old_action":aid,"new_action":new_aid_g1,
                            "old_atomic_step":at,"new_atomic_step":new_at_g1,
                            "relation_op":f"set_{new_rel_g1}","ms_op":";referent_grounding_v1:G1",
                            "step_orig":orig[:80]})
                        stats["G1"] += 1
                        claimed = True
                    else:
                        # G1 解析失败 → 降级到 G2(无介词框架)
                        pass
                
                # === G2: 无锚 → tidy ===
                if (ph_surface or ph_receptacle) and not claimed:
                    patient = extract_patient_np(orig)
                    if patient:
                        new_at_g2 = f"Straighten the {patient}."
                    else:
                        new_at_g2 = f"Straighten the {labels[0] if labels else 'item'}."
                    plan.append({"file":rel,"task_idx":tidx,"step_id":sid,
                        "rule":"G2","old_action":aid,"new_action":"straighten",
                        "old_atomic_step":at,"new_atomic_step":new_at_g2,
                        "relation_op":"set_null","ms_op":";referent_grounding_v1:G2",
                        "step_orig":orig[:80]})
                    stats["G2"] += 1
                    claimed = True
                
                # === G3: items 具名还原 ===
                if ph_items and not claimed:
                    named_patient = extract_items_patient(orig)
                    if named_patient:
                        new_at_g3 = re.sub(r'\bitems?\b', f'the {named_patient}', at, count=1, flags=re.I)
                        plan.append({"file":rel,"task_idx":tidx,"step_id":sid,
                            "rule":"G3","old_action":aid,"new_action":aid,
                            "old_atomic_step":at,"new_atomic_step":new_at_g3,
                            "relation_op":"no_change","ms_op":";referent_grounding_v1:G3",
                            "step_orig":orig[:80]})
                        stats["G3"] += 1
                        claimed = True
                
                # === G4: container 消解 ===
                if ph_container and not claimed:
                    # 从 task 文本和前续步骤找容器
                    CONTAINERS = {"watering can","kettle","vase","bucket","pot","bottle",
                        "jar","cup","mug","pitcher","bowl","basin","tank","jug","carafe",
                        "flask","canteen","thermos","spray bottle","water bottle","teapot"}
                    context = task.get("task","") + " "
                    for prev_s in task.get("plan",[]):
                        if prev_s.get("step_id",0) >= sid: break
                        context += prev_s.get("step","") + " "
                    context_low = context.lower()
                    
                    resolved = None
                    for c in CONTAINERS:
                        if c in context_low:
                            resolved = c
                            break
                    
                    if resolved:
                        # 从 labels 找 sink/tap
                        loc = "the sink"
                        for l in labels:
                            if "sink" in norm(l) or "tap" in norm(l) or "faucet" in norm(l):
                                loc = f"the {l}"
                                break
                        new_at_g4 = f"Fill the {resolved} at {loc}."
                        plan.append({"file":rel,"task_idx":tidx,"step_id":sid,
                            "rule":"G4_resolved","old_action":aid,"new_action":aid,
                            "old_atomic_step":at,"new_atomic_step":new_at_g4,
                            "relation_op":"set_at","ms_op":";referent_grounding_v1:G4",
                            "step_orig":orig[:80]})
                        stats["G4_resolved"] += 1
                    else:
                        plan.append({"file":rel,"task_idx":tidx,"step_id":sid,
                            "rule":"G4_flag","old_action":aid,"new_action":aid,
                            "old_atomic_step":at,"new_atomic_step":at,
                            "relation_op":"no_change","ms_op":";ungrounded_anaphora",
                            "step_orig":orig[:80]})
                        stats["G4_flag"] += 1
                    claimed = True

# 保存 plan
csv_path = os.path.join(QA_OUT, "grounding_plan.csv")
if plan:
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(plan[0].keys()))
        w.writeheader()
        w.writerows(plan)

# 对照表
expected = {"P0a":2,"P0b":1,"P0c":4,"G1":1422,"G2":2733,"G3":662,"G4_resolved":"?","G4_flag":"?"}
print("=" * 70)
print(f"{'Rule':<20} {'Actual':<10} {'Expected':<10} {'Status'}")
print("-" * 70)
g4_total = stats.get("G4_resolved",0) + stats.get("G4_flag",0)
for rule in ["P0a","P0b","P0c","G1","G2","G3"]:
    a = stats.get(rule, 0)
    e = expected.get(rule, "?")
    if isinstance(e, int):
        delta = a - e
        pct = abs(delta) / max(e, 1) * 100
        status = "OK" if pct <= 10 else f"WARN ({pct:.0f}%)"
    else:
        status = "?"
    print(f"{rule:<20} {a:<10} {str(e):<10} {status}")
print(f"{'G4_total':<20} {g4_total:<10} {'166':<10} {'OK' if abs(g4_total-166)/166*100<=10 else 'WARN'}")
print(f"  G4_resolved: {stats.get('G4_resolved',0)}")
print(f"  G4_flag: {stats.get('G4_flag',0)}")
print(f"\nTotal plan entries: {len(plan)}")
print(f"Plan CSV: {csv_path}")
