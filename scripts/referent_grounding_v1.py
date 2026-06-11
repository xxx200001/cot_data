#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
referent_grounding_v1 —— 指代失锚修复 + P0 收尾(单文件三子命令)

用法(在仓库根目录运行, 即 gemini_tasks_output_hm3d_atomic/ 的上一级):
  python referent_grounding_v1.py dryrun   # 只产出 qa_output/grounding_plan.csv + 命中对照表, 不写数据
  python referent_grounding_v1.py apply    # 备份整个数据目录 -> 按 plan 应用 -> qa_output/changes_grounding.csv
  python referent_grounding_v1.py verify   # S5 断言(失锚归零/不变量/标记计数/抽样对照)

CHECKPOINT 0 决策在 CONFIG 里改, 默认: D1=straighten, D2=含 fluff 批, D3=消解+兜底 FLAG, D4=reposition。
幂等: mapping_source 含 referent_grounding_v1 / cleanup_v1 标记的条目自动跳过。
"""
import json, glob, os, re, csv, sys, shutil, random, collections
from datetime import date

# ---------------- CONFIG ----------------
DATA_DIR   = "gemini_tasks_output_hm3d_atomic"
QA_DIR     = "qa_output"
PLAN_CSV   = os.path.join(QA_DIR, "grounding_plan.csv")
CHANGES_CSV= os.path.join(QA_DIR, "changes_grounding.csv")
D1_TIDY            = "straighten"    # G2 tidy 动词: straighten | reposition
D2_INCLUDE_FLUFF   = True            # G3 是否包含 action==fluff 的条目
D3_RESOLVE         = True            # G4: True=上下文消解+兜底FLAG, False=一律FLAG
D4_TOOLSET_ACTION  = "reposition"    # P0c: reposition | straighten
MARK   = "referent_grounding_v1"

PHANTOMS   = ("surface", "receptacle")
PRONOUNS   = {"it","them","this","that","these","those","him","her","one","everything","anything","something","stuff"}
G1_VERBS   = {"arrange","organize","organise","put","place","position","set","return","store","stack","hang","load","tidy","display","line","lay","sort","rearrange","reposition","keep","stow"}
VERB_KEEP  = {"hang":("hang","Hang"), "stack":("stack","Stack"), "store":("store","Store"), "load":("load","Load")}
G2_VERBS   = {"arrange","organize","organise","tidy","position","set","neaten","straighten","prepare","fix","make","adjust","align","sort","style","reposition","rearrange","display","stow","place","put"}
G2_VERB_ACTION = {"reposition":("reposition","Reposition"), "position":("reposition","Reposition"), "align":("align","Align"), "straighten":("straighten","Straighten")}
G3_FRAME   = r'^\s*(put|arrange|organize|place|stack|fluff|store|tidy)\s+(the\s+)?([a-z][a-z ]*?)\s+(back\s+)?(in|into|on|onto|at)\b'
X_TRIM     = r'\s+\b(for|with|before|after|to|from|at|near|by|during|so|until|while|because|using)\b.*$'
G3_EXCL    = {'items','item','everything','things','them','it','away','back','up','down','out'}
def parse_g3_np(sl):
    m = re.match(G3_FRAME, sl)
    if not m: return None
    NP = norm_np(m.group(3))
    if not NP or NP in G3_EXCL: return None
    return NP
VESSELS    = ["watering can","water can","spray bottle","coffee pot","tea pot","teapot","kettle","pitcher","carafe","vase","bucket","jug","jar","bowl","mug","cup","glass","bottle","pot","pan","basin","tank"]
P0 = [  # (file_rel, task_idx, step_id, rule, new_action, new_text, marker, remove_tag)
 ("00096-6HRFAUDqpTb/tasks-island_0.json",77,1,"P0a","tighten","Tighten the cabinet door.",";vocab_extension_v1:repair_remap->tighten",None),
 ("00664-u5atqC7vRCY/tasks-island_0.json",16,1,"P0a","tighten","Tighten the support beam.",";vocab_extension_v1:repair_remap->tighten",None),
 ("00475-g7hUFVNac26/tasks-island_0.json",38,1,"P0b","unload","Unload the laundry machine.",";vocab_extension_v1:open->unload",None),
 ("00164-XfUxBGTFQQb/tasks-island_0.json",65,2,"P0c",D4_TOOLSET_ACTION,f"{D4_TOOLSET_ACTION.capitalize()} the fireplace tool set.",f";cleanup_v1:turn_on->{D4_TOOLSET_ACTION}","vocab_gap:no_ignite_action"),
 ("00475-g7hUFVNac26/tasks-island_0.json",0,3,"P0c",D4_TOOLSET_ACTION,f"{D4_TOOLSET_ACTION.capitalize()} the fireplace tool set.",f";cleanup_v1:turn_on->{D4_TOOLSET_ACTION}","vocab_gap:no_ignite_action"),
 ("00475-g7hUFVNac26/tasks-island_0.json",503,3,"P0c",D4_TOOLSET_ACTION,f"{D4_TOOLSET_ACTION.capitalize()} the fireplace tool set.",f";cleanup_v1:turn_on->{D4_TOOLSET_ACTION}","vocab_gap:no_ignite_action"),
 ("00475-g7hUFVNac26/tasks-island_0.json",513,5,"P0c",D4_TOOLSET_ACTION,f"{D4_TOOLSET_ACTION.capitalize()} the fireplace tool set.",f";cleanup_v1:turn_on->{D4_TOOLSET_ACTION}","vocab_gap:no_ignite_action"),
]
EXPECT = {"P0":7,"G1":1409,"G2":2708,"G3":164,"G4":166}
MARKER_BUDGET = {"vocab_gap:roll":99,"vocab_gap:no_tune_action":78,"idiom_ok":553,"assume_gas_fireplace":549,"vocab_gap:repair":36}

# ---------------- helpers ----------------
def files():
    return sorted(glob.glob(os.path.join(DATA_DIR, "*", "tasks-*.json")))

def rel(fp):
    return os.path.relpath(fp, DATA_DIR).replace('\\', '/')

def ungrounded(word, atomic_l, ground):
    return re.search(r'\b'+word+r's?\b', atomic_l) and not re.search(r'\b'+word+r's?\b', ground)

def norm_np(x):
    x = re.sub(X_TRIM, '', x.strip())
    x = re.sub(r'^(away|back|out|up|down)\s+', '', x)
    x = re.sub(r'^(the|a|an|some|all the|all|your|my)\s+', '', x)
    x = re.sub(r'^(away|back|out|up|down)\s+', '', x)
    x = re.sub(r'^(the|a|an)\s+', '', x)
    x = re.sub(r'\s+(away|back|out|up|down|aside|neatly|properly|nicely|carefully|nearby|next|first|together|too|again)$', '', x)
    return x.strip(' .')

def step_iter():
    for fp in files():
        d = json.load(open(fp))
        for ti, t in enumerate(d.get("tasks", [])):
            for st in t.get("plan", []):
                yield rel(fp), ti, t, st

def parse_g1(step_text, labels_l):
    s = step_text.strip().rstrip('.!?')
    m = re.match(r'^\s*([A-Za-z-]+)\s+(.*)$', s)
    if not m: return None
    verb = m.group(1).lower()
    if verb not in G1_VERBS: return None
    rest = m.group(2)
    pm = re.search(r'\b(in|into|on|onto|at|near|beside|by)\s+(?:the\s+|a\s+|an\s+)?(.+)$', rest)
    if not pm: return None
    X = norm_np(re.sub(r'\s+\b(in|into|on|onto|at|near|beside|by)\b.*$', '', rest))
    if not X or X.lower() in PRONOUNS or re.match(r'^(in|into|on|onto|at|of|near|beside|by)\b', X): return None
    pw = pm.group(1)
    prep = 'in' if pw in ('in','into') else ('on' if pw in ('on','onto') else 'at')
    Ytail = pm.group(2)
    Ytext = norm_np(re.split(r'\b(in|into|on|onto|at|near|inside|under|next|with|for|beside|by)\b', Ytail)[0])
    Y = None
    for lab in sorted(labels_l, key=len, reverse=True):
        if lab == Ytext: Y = lab; break
    if Y is None: Y = Ytext
    if not Y: return None
    if Y.lower() == X.lower(): return None
    act, verb_out = VERB_KEEP.get(verb, ("place_in" if prep=="in" else "place_on", "Place"))
    if verb in VERB_KEEP: act = VERB_KEEP[verb][0]
    new_text = f"{verb_out} the {X} {pw} the {Y}."
    return X, prep, Y, act, new_text

def parse_g2(step_text):
    s = step_text.strip().rstrip('.!?')
    m = re.match(r'^\s*([A-Za-z-]+)\s+(.*)$', s)
    if not m: return None
    verb = m.group(1).lower()
    if verb not in G2_VERBS: return None
    if verb=='set' and re.search(r'\bto\b', m.group(2)): return None
    X = norm_np(m.group(2))
    if not X or X.lower() in PRONOUNS: return None
    act, vout = G2_VERB_ACTION.get(verb, (D1_TIDY, D1_TIDY.capitalize()))
    return X, act, vout

def resolve_vessel(task, st):
    pool = (task.get('task') or '')
    for prev in task.get('plan', []):
        if prev is st: break
        pool += ' ' + (prev.get('step') or '')
    pl = pool.lower()
    for v in VESSELS:
        if re.search(r'\b'+re.escape(v)+r'\b', pl): return v
    return None

# ---------------- dryrun ----------------
def build_plan():
    rows, claimed = [], set()
    p0idx = {(f,ti,sid):(rule,na,nt,mk,rm) for f,ti,sid,rule,na,nt,mk,rm in P0}
    stats = collections.Counter(); unparsed = []
    for frel, ti, task, st in step_iter():
        sid = st.get('step_id'); key = (frel,ti,sid)
        s = st.get('step') or ''; sl = s.lower()
        a = st.get('atomic_step') or ''; al = a.lower()
        labs = [v.lower() for v in (st.get('labels') or {}).values()]
        ground = sl + ' ' + ' '.join(labs)
        aas = st.get('atomic_actions') or []
        if not aas: continue
        ms_all = ';'.join((x.get('mapping_source') or '') for x in aas)
        if MARK in ms_all or 'cleanup_v1' in ms_all: stats['skipped_idempotent']+=1; continue
        a0 = aas[0]; act = a0.get('action_id'); rel0 = a0.get('relation')
        # ---- P0 ----
        if key in p0idx:
            rule,na,nt,mk,rm = p0idx[key]
            rows.append(dict(rule=rule,file=frel,task_idx=ti,step_id=sid,step=s,status='OK',
                old_action=act,new_action=na,old_text=a,new_text=nt,
                old_relation=rel0,new_relation=None if rule!='P0b' else rel0,
                marker=mk,remove_tag=rm or '',note=''))
            claimed.add(key); stats[rule]+=1; continue
        phant = any(ungrounded(w, al, ground) for w in PHANTOMS)
        hasprep = bool(re.search(r'\b(in|into|on|onto|at|near|beside|by)\s+(the|a|an)\s+\w', sl))
        inv = drift = False
        for lab in labs:
            am = re.match(r'^(place|put|move|store|load)\s+(the\s+)?'+re.escape(lab)+r'\b(?P<rest>.*)$', al)
            if re.search(r'\b(in|into|on|onto)\s+the\s+'+re.escape(lab)+r'\b', sl) and am and (not am.group('rest').strip(' .') or 'surface' in am.group('rest') or 'receptacle' in am.group('rest')): inv=True
            if act in ('place_on','place_in') and re.search(r'\b(in|into)\s+the\s+'+re.escape(lab)+r'\b', sl) and re.search(r'\bon(to)?\s+the\s+'+re.escape(lab)+r'\b', al): drift=True
        # ---- G1 ----
        if (phant and hasprep) or inv or drift:
            if len(aas)>1:
                unparsed.append((frel,ti,sid,s,a,'multi_action')); stats['G1_unparsed']+=1; continue
            p = parse_g1(s, labs)
            if p:
                X,prep,Y,na,nt = p
                rows.append(dict(rule='G1',file=frel,task_idx=ti,step_id=sid,step=s,status='OK',
                    old_action=act,new_action=na,old_text=a,new_text=nt,
                    old_relation=rel0,new_relation=prep if na.startswith('place') or na in('hang','stack','store','load') else rel0,
                    marker=f';{MARK}:G1',remove_tag='',note=f'X={X}|Y={Y}'))
                claimed.add(key); stats['G1']+=1
            else:
                unparsed.append((frel,ti,sid,s,a,'parse_fail')); stats['G1_unparsed']+=1
            continue
        # ---- G2 ----
        if phant and not hasprep:
            if len(aas)>1:
                unparsed.append((frel,ti,sid,s,a,'multi_action')); stats['G2_unparsed']+=1; continue
            g2 = parse_g2(s)
            if g2:
                X, g2act, g2verb = g2
                nt = f"{g2verb} the {X}."
                rows.append(dict(rule='G2',file=frel,task_idx=ti,step_id=sid,step=s,status='OK',
                    old_action=act,new_action=g2act,old_text=a,new_text=nt,
                    old_relation=rel0,new_relation=None,marker=f';{MARK}:G2',remove_tag='',note=f'X={X}'))
                claimed.add(key); stats['G2']+=1
            else:
                unparsed.append((frel,ti,sid,s,a,'parse_fail')); stats['G2_unparsed']+=1
            continue
        # ---- G3 ----
        if re.search(r'\bitems?\b', al) and not re.search(r'\bitems?\b', sl):
            NP = parse_g3_np(sl)
            if NP:
                if not D2_INCLUDE_FLUFF and act=='fluff': stats['G3_excluded_fluff']+=1; continue
                nt = re.sub(r'\b[Ii]tems?\b', f"the {NP}", a, count=1)
                rows.append(dict(rule='G3',file=frel,task_idx=ti,step_id=sid,step=s,status='OK',
                    old_action=act,new_action=act,old_text=a,new_text=nt,
                    old_relation=rel0,new_relation=rel0,marker=f';{MARK}:G3',remove_tag='',note=f'NP={NP}'))
                claimed.add(key); stats['G3']+=1
            continue
        # ---- G4 ----
        if ungrounded('container', al, ground):
            if not D3_RESOLVE:
                rows.append(dict(rule='G4',file=frel,task_idx=ti,step_id=sid,step=s,status='FLAG',
                    old_action=act,new_action=act,old_text=a,new_text=a,
                    old_relation=rel0,new_relation=rel0,marker=';ungrounded_anaphora',remove_tag='',note='policy=flag_all'))
                stats['G4_flag']+=1; continue
            v = resolve_vessel(task, st)
            if v:
                fix = 'sink' if 'sink' in (al+' '+' '.join(labs)) else ('tap' if 'tap' in (al+' '+' '.join(labs)) else None)
                nt = f"Fill the {v} at the {fix}." if fix else re.sub(r'\b(a|the)\s+container\b', f"the {v}", a)
                rows.append(dict(rule='G4',file=frel,task_idx=ti,step_id=sid,step=s,status='RESOLVED',
                    old_action=act,new_action=act,old_text=a,new_text=nt,
                    old_relation=rel0,new_relation=rel0,marker=f';{MARK}:G4',remove_tag='',note=f'vessel={v}'))
                stats['G4_resolved']+=1
            else:
                rows.append(dict(rule='G4',file=frel,task_idx=ti,step_id=sid,step=s,status='FLAG',
                    old_action=act,new_action=act,old_text=a,new_text=a,
                    old_relation=rel0,new_relation=rel0,marker=';ungrounded_anaphora',remove_tag='',note='no_vessel_found'))
                stats['G4_flag']+=1
    return rows, stats, unparsed

def cmd_dryrun():
    os.makedirs(QA_DIR, exist_ok=True)
    rows, stats, unparsed = build_plan()
    cols = ['rule','file','task_idx','step_id','step','status','old_action','new_action','old_text','new_text','old_relation','new_relation','marker','remove_tag','note']
    with open(PLAN_CSV,'w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=cols); w.writeheader(); w.writerows(rows)
    with open(os.path.join(QA_DIR,'g_unparsed.csv'),'w',newline='',encoding='utf-8-sig') as f:
        w=csv.writer(f); w.writerow(['file','task_idx','step_id','step','atomic_step','reason']); w.writerows(unparsed)
    print("== 命中对照表 (实际 / 锚点) ==")
    p0 = sum(stats[r] for r in ('P0a','P0b','P0c'))
    table = {'P0':p0,'G1':stats['G1'],'G2':stats['G2'],'G3':stats['G3'],'G4':stats['G4_resolved']+stats['G4_flag']}
    halt=False
    for k,v in table.items():
        exp=EXPECT[k]; dev = (v-exp)/exp*100 if exp else 0
        flag='' if abs(dev)<=10 else '  <-- 偏差超±10%, 先解释再继续'
        if abs(dev)>10: halt=True
        print(f"  {k}: {v} / {exp}  ({dev:+.1f}%){flag}")
    print(f"  G1_unparsed(转逐条判定批): {stats['G1_unparsed']} | G2_unparsed: {stats['G2_unparsed']}")
    print(f"  G4: resolved={stats['G4_resolved']}, flag={stats['G4_flag']} | 幂等跳过: {stats['skipped_idempotent']}")
    print(f"plan -> {PLAN_CSV} ({len(rows)} rows); unparsed -> qa_output/g_unparsed.csv ({len(unparsed)})")
    if halt and stats["skipped_idempotent"]==0: print("!! 存在超阈偏差, 请人工核对后再 apply"); sys.exit(2)
    if stats["skipped_idempotent"]>0: print("(检测到已应用标记, 对照表偏差不作熔断)")

# ---------------- apply ----------------
def cmd_apply():
    if not os.path.exists(PLAN_CSV):
        sys.exit("先跑 dryrun 生成 plan")
    backup = f"cot_data_backup_grounding_{date.today().strftime('%Y%m%d')}"
    if not os.path.exists(backup):
        print("backing up ->", backup); shutil.copytree(DATA_DIR, backup)
    plan = list(csv.DictReader(open(PLAN_CSV, encoding='utf-8-sig')))
    byfile = collections.defaultdict(list)
    for r in plan:
        if r['status'] in ('OK','RESOLVED','FLAG'): byfile[r['file']].append(r)
    applied, mismatched = [], []
    for frel, rs in byfile.items():
        fp = os.path.join(DATA_DIR, frel); d = json.load(open(fp))
        for r in rs:
            t = d['tasks'][int(r['task_idx'])]
            st = next((x for x in t['plan'] if x.get('step_id')==int(r['step_id'])), None)
            if st is None: mismatched.append((r,'step_not_found')); continue
            aas = st.get('atomic_actions') or []
            if not aas: mismatched.append((r,'no_actions')); continue
            ms0 = aas[0].get('mapping_source') or ''
            tgt = (r['marker'] or '').lstrip(';')
            if MARK in ms0 or 'cleanup_v1' in ms0 or 'ungrounded_anaphora' in ms0 or (tgt and tgt in ms0): continue  # idempotent
            if (st.get('atomic_step') or '') != r['old_text'] or aas[0].get('action_id') != r['old_action']:
                mismatched.append((r,'state_mismatch')); continue
            if r['status'] != 'FLAG':
                st['atomic_step'] = r['new_text']
                aas[0]['action_id'] = r['new_action']
                nr = r['new_relation']
                aas[0]['relation'] = None if nr in ('','None',None) else nr
            ms = ms0
            if r['remove_tag']:
                ms = ms.replace(';'+r['remove_tag'],'').replace(r['remove_tag'],'').replace(';;',';').strip(';')
            aas[0]['mapping_source'] = ms + r['marker']
            applied.append(r)
        json.dump(d, open(fp,'w'), indent=2, ensure_ascii=False)
    os.makedirs(QA_DIR, exist_ok=True)
    with open(CHANGES_CSV,'w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=list(plan[0].keys())); w.writeheader(); w.writerows(applied)
    print(f"applied {len(applied)} | mismatched/skipped {len(mismatched)} | changes -> {CHANGES_CSV} | backup -> {backup}")
    for r,why in mismatched[:10]: print("  MISMATCH:", why, r['file'], r['task_idx'], r['step_id'])

# ---------------- verify ----------------
def cmd_verify():
    backups = sorted(glob.glob('cot_data_backup_grounding_*'))
    bk = backups[-1] if backups else None
    fail=[]
    ph=collections.Counter(); inv=0; items_named=0; cont_ung=0; flags=collections.Counter()
    ph_keys=set(); inv_keys=set()
    up_keys=set()
    upf=os.path.join(QA_DIR,'g_unparsed.csv')
    if os.path.exists(upf):
        for r in csv.reader(open(upf,encoding='utf-8-sig')):
            if r and r[0]!='file': up_keys.add((r[0],int(r[1]),int(r[2])))
    acts=set(); n=0; t_diff=s_diff=l_diff=0; jbad=0
    for fp in files():
        try: d=json.load(open(fp))
        except Exception: jbad+=1; continue
        db = json.load(open(os.path.join(bk, rel(fp)))) if bk else None
        for ti,t in enumerate(d['tasks']):
            tb = db['tasks'][ti] if db else None
            if tb and t.get('task')!=tb.get('task'): t_diff+=1
            for si,st in enumerate(t.get('plan',[])):
                if tb:
                    sb=tb['plan'][si]
                    if st.get('step')!=sb.get('step'): s_diff+=1
                    if (st.get('labels') or {})!=(sb.get('labels') or {}): l_diff+=1
                s=(st.get('step') or '').lower(); a=(st.get('atomic_step') or '').lower()
                labs=[v.lower() for v in (st.get('labels') or {}).values()]
                ground=s+' '+' '.join(labs)
                key=(rel(fp), ti, st.get('step_id'))
                for w in PHANTOMS:
                    if ungrounded(w,a,ground): ph[w]+=1; ph_keys.add(key)
                if ungrounded('container',a,ground): cont_ung+=1
                for lab in labs:
                    am = re.match(r'^(place|put|move|store|load)\s+(the\s+)?'+re.escape(lab)+r'\b(?P<rest>.*)$', a)
                    if re.search(r'\b(in|into|on|onto)\s+the\s+'+re.escape(lab)+r'\b', s) and am and (not am.group('rest').strip(' .') or 'surface' in am.group('rest') or 'receptacle' in am.group('rest')): inv+=1; inv_keys.add(key); break
                if re.search(r'\bitems?\b',a) and not re.search(r'\bitems?\b',s):
                    NPv=parse_g3_np(s)
                    aas=st.get('atomic_actions') or []
                    if NPv:
                        if D2_INCLUDE_FLUFF or (aas and aas[0].get('action_id')!='fluff'): items_named+=1
                for aa in st.get('atomic_actions',[]):
                    n+=1; acts.add(aa.get('action_id'))
                    ms=aa.get('mapping_source') or ''
                    for tag in list(MARKER_BUDGET)+['vocab_gap:no_ignite_action','ungrounded_anaphora',MARK]:
                        if tag in ms: flags[tag]+=1
    def chk(name,cond,info=''):
        print(("PASS  " if cond else "FAIL  ")+name, info); 
        if not cond: fail.append(name)
    chk("幻影残留 ⊆ 判定批清单", ph_keys<=up_keys, f"(残留{len(ph_keys)}, 批内{len(ph_keys&up_keys)}, 批外{len(ph_keys-up_keys)})")
    chk("失锚 container == FLAG 数", cont_ung==flags['ungrounded_anaphora'], f"({cont_ung} vs {flags['ungrounded_anaphora']})")
    chk("倒置残留 ⊆ 判定批清单", inv_keys<=up_keys, f"(残留{len(inv_keys)}, 批外{len(inv_keys-up_keys)})")
    chk("具名可还原 items 残留 == 0", items_named==0, f"({items_named})")
    chk("条目守恒 179546", n==179546, f"({n})")
    chk("JSON 217/217", jbad==0, f"(bad={jbad})")
    chk("词表 <= 52", len(acts)<=52, f"({len(acts)})")
    chk("step/task/labels 与备份零差异", (t_diff,s_diff,l_diff)==(0,0,0), f"({t_diff},{s_diff},{l_diff})")
    for tag,exp in MARKER_BUDGET.items():
        chk(f"标记 {tag} == {exp}", flags[tag]==exp, f"({flags[tag]})")
    chk("no_ignite_action == 0", flags['vocab_gap:no_ignite_action']==0, f"({flags['vocab_gap:no_ignite_action']})")
    print(f"\n{MARK} 标记总数: {flags[MARK]}")
    if os.path.exists(CHANGES_CSV):
        ch=list(csv.DictReader(open(CHANGES_CSV,encoding='utf-8-sig')))
        print("\n== 随机抽样 10 条前后对照 ==")
        for r in random.sample(ch, min(10,len(ch))):
            print(f"  [{r['rule']}] {r['file']} t{r['task_idx']} s{r['step_id']}\n    '{r['old_text']}' [{r['old_action']}] -> '{r['new_text']}' [{r['new_action']}]")
    print("\n== 结论:", "全部断言通过" if not fail else f"{len(fail)} 项失败: {fail}")
    sys.exit(0 if not fail else 1)

if __name__=='__main__':
    cmd = sys.argv[1] if len(sys.argv)>1 else ''
    {'dryrun':cmd_dryrun,'apply':cmd_apply,'verify':cmd_verify}.get(cmd, lambda: sys.exit(__doc__))()
