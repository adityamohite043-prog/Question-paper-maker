import io, json, re, zipfile, requests, time, logging
import streamlit as st
from pypdf import PdfReader
from docx import Document

st.set_page_config(page_title="Question Paper Maker",page_icon="📝",layout="wide")
st.title("📝 Question Paper Maker")
st.caption("v2.3 — Gemini Interactions API, resilient 503 retries, saved unit progress, cached sources, and template export.")

logging.getLogger("pypdf").setLevel(logging.ERROR)

@st.cache_data(show_spinner=False)
def read_file_bytes(data, name):
    """Extract source text once per unique uploaded file and cache it across reruns."""
    low=name.lower()
    bio=io.BytesIO(data)
    if low.endswith(".pdf"):
        reader=PdfReader(bio)
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    if low.endswith(".docx"):
        d=Document(bio)
        out=[p.text for p in d.paragraphs if p.text.strip()]
        for t in d.tables:
            for r in t.rows:
                row=" | ".join(c.text.strip() for c in r.cells if c.text.strip())
                if row: out.append(row)
        return "\n".join(out)
    return data.decode("utf-8",errors="ignore")

def read_file(f):
    f.seek(0)
    return read_file_bytes(f.read(), f.name)

def relevant_reference(reference, unit, max_chunks=5):
    """Select small reference chunks most related to the current unit instead of resending the whole book."""
    text=re.sub(r"\s+"," ",reference).strip()
    if len(text)<=18000:
        return text
    chunk_size=3200; overlap=300; chunks=[]
    pos=0
    while pos < len(text):
        chunks.append(text[pos:pos+chunk_size])
        pos += chunk_size-overlap
    words=[w.lower() for w in re.findall(r"[A-Za-z][A-Za-z0-9-]{3,}",unit)]
    stop={"unit","hours","general","purpose","design","operation","types","systems","system","aircraft","airplane","aeroplane","measurement","parameters"}
    terms=[]
    for w in words:
        if w not in stop and w not in terms:
            terms.append(w)
    terms=terms[:35]
    scored=[]
    for i,ch in enumerate(chunks):
        low=ch.lower()
        score=sum(low.count(t) for t in terms)
        scored.append((score,i,ch))
    best=sorted(scored,key=lambda x:(-x[0],x[1]))[:max_chunks]
    best=sorted(best,key=lambda x:x[1])
    return "\n\n--- REFERENCE EXTRACT ---\n\n".join(x[2] for x in best)

def split_units(text):
    m=list(re.finditer(r"(?im)\bunit\s*[-–:]?\s*(?:[ivx]+|\d+)\b",text))
    if len(m)<5: raise ValueError("Five Unit headings were not detected. Please use Unit 1 ... Unit 5 headings.")
    out=[]
    for i,x in enumerate(m[:5]):
        end=m[i+1].start() if i+1<len(m) else len(text)
        out.append(text[x.start():end].strip())
    return out

def _interaction_text(data):
    texts=[]
    for step in data.get("steps",[]):
        if step.get("type") != "model_output":
            continue
        for item in step.get("content",[]):
            if item.get("type") == "text" and item.get("text"):
                texts.append(item["text"])
    if not texts:
        raise RuntimeError(f"AI returned no text output: {str(data)[:500]}")
    return "\n".join(texts)

def call_ai(prompt, attempts=4):
    key=st.secrets.get("GEMINI_API_KEY","")
    model=st.secrets.get("GEMINI_MODEL","gemini-3.8-flash")
    fallback=st.secrets.get("GEMINI_FALLBACK_MODEL","").strip()
    if not key:
        raise RuntimeError("Website owner has not configured the AI key.")
    url="https://generativelanguage.googleapis.com/v1beta/interactions"
    headers={"x-goog-api-key":key,"Content-Type":"application/json"}
    models=[model]+([fallback] if fallback and fallback != model else [])
    last=None
    waits=[5,15,30]
    for mi,current_model in enumerate(models):
        for attempt in range(1,attempts+1):
            payload={
                "model":current_model,
                "input":prompt,
                "store":False,
                "generation_config":{"temperature":0.2,"thinking_level":"low","max_output_tokens":8192}
            }
            try:
                r=requests.post(url,headers=headers,json=payload,timeout=(20,180))
                if r.ok:
                    return _interaction_text(r.json())
                last=f"AI service error {r.status_code}: {r.text[:500]}"
                if r.status_code not in (429,500,502,503,504):
                    raise RuntimeError(last)
            except requests.RequestException as e:
                last=f"AI connection error: {e}"
            if attempt < attempts:
                delay=waits[min(attempt-1,len(waits)-1)]
                time.sleep(delay)
        # Only move to an explicitly configured fallback after primary retries are exhausted.
    raise RuntimeError(last or "AI service did not respond after retries.")

def get_json(s):
    s=re.sub(r"^```(?:json)?\s*","",s.strip()); s=re.sub(r"\s*```$","",s)
    return json.loads(s)

def generate(unit_no,unit,reference,co,difficulty,used):
    # Send only the reference excerpts most relevant to this unit.
    ref=relevant_reference(reference,unit)
    prompt=f"""Act as a university examination question-paper setter.
Use ONLY the supplied Unit syllabus and reference material. Do not add outside topics.
Avoid questions already used. Difficulty: {difficulty}.
UNIT {unit_no} SYLLABUS:
{unit}
REFERENCE MATERIAL:
{ref}
COURSE OUTCOMES:
{co}
ALREADY USED:
{used[-7000:]}

Generate exactly 10 MCQs and exactly 2 alternative descriptive main questions.
Each descriptive main question is 5 marks split into part a = 3 and part b = 2.
MCQs need exactly four plausible options and one correct answer.
Solutions must be actual model answers, never phrases like "award marks for".
Return only valid JSON:
{{"mcqs":[{{"question":"","options":{{"A":"","B":"","C":"","D":""}},"answer":"A","bt":"L2","co":"CO1"}}],
"descriptive":[{{"a":{{"question":"","marks":3,"solution":""}},"b":{{"question":"","marks":2,"solution":""}},"bt":"L2","co":"CO1"}},
{{"a":{{"question":"","marks":3,"solution":""}},"b":{{"question":"","marks":2,"solution":""}},"bt":"L3","co":"CO1"}}]}}"""
    d=get_json(call_ai(prompt))
    if len(d.get("mcqs",[]))!=10 or len(d.get("descriptive",[]))!=2:
        raise ValueError("AI returned an incomplete unit. Please retry this set.")
    for q in d["mcqs"]:
        if str(q.get("answer","")).upper() not in "ABCD":
            raise ValueError("AI returned an invalid MCQ answer key. Please retry this set.")
        q["answer"]=str(q["answer"]).upper()
        if not all(k in q.get("options",{}) for k in "ABCD"):
            raise ValueError("AI returned incomplete MCQ options. Please retry this set.")
    return d

def balance(qs):
    target=(["A","B","C","D"]*13)[:len(qs)]
    for q,d in zip(qs,target):
        c=q["answer"].upper()
        if c!=d:
            q["options"][c],q["options"][d]=q["options"][d],q["options"][c]; q["answer"]=d
    return qs

def make_key_doc(paper,title,code,setno):
    d=Document(); d.add_heading("MCQ Answer Key",0)
    d.add_paragraph(f"Course: {code} – {title}     Set: {setno}")
    t=d.add_table(rows=1,cols=5); t.style="Table Grid"
    for c,x in zip(t.rows[0].cells,["Q.No.","Answer","Unit","BT","CO"]): c.text=x
    for i,q in enumerate(paper["mcqs"],1):
        r=t.add_row().cells
        for c,x in zip(r,[i,q["answer"],q["unit"],q.get("bt",""),q.get("co","")]): c.text=str(x)
    o=io.BytesIO(); d.save(o); return o.getvalue()

def make_qp_doc(paper,title,code,setno):
    d=Document(); d.add_heading("Question Paper",0)
    d.add_paragraph(f"Course: {code} – {title}     Set: {setno}")
    d.add_heading("Part A – MCQs",1)
    for i,q in enumerate(paper["mcqs"],1):
        d.add_paragraph(f"Q{i}. {q['question']}")
        d.add_paragraph(f"A) {q['options']['A']}     B) {q['options']['B']}\nC) {q['options']['C']}     D) {q['options']['D']}")
    d.add_heading("Part B – Descriptive Questions",1)
    n=1
    for u,pair in enumerate(paper["descriptive"],1):
        d.add_paragraph(f"UNIT {u}",style="Heading 2")
        for j,q in enumerate(pair):
            d.add_paragraph(f"Q{n}. a) {q['a']['question']} ({q['a']['marks']} marks)")
            d.add_paragraph(f"     b) {q['b']['question']} ({q['b']['marks']} marks)")
            if j==0: d.add_paragraph("OR")
            n+=1
    o=io.BytesIO(); d.save(o); return o.getvalue()

def make_sol_doc(paper,title,code,setno):
    d=Document(); d.add_heading("Scheme & Solution",0)
    d.add_paragraph(f"Course: {code} – {title}     Set: {setno}")
    t=d.add_table(rows=1,cols=3); t.style="Table Grid"
    for c,x in zip(t.rows[0].cells,["Q.No.","Solution","Marks"]): c.text=x
    n=1
    for pair in paper["descriptive"]:
        for q in pair:
            r=t.add_row().cells; r[0].text=str(n)
            r[1].text=f"a) {q['a']['solution']}\n\nb) {q['b']['solution']}"
            r[2].text="5"; n+=1
    o=io.BytesIO(); d.save(o); return o.getvalue()


def get_bytes(f):
    f.seek(0)
    return f.read()

def set_cell(c, text):
    c.text = str(text)

def fill_qp_template(template_bytes, paper, meta):
    d=Document(io.BytesIO(template_bytes))
    if len(d.tables)<4:
        raise ValueError("Question-paper template structure is not compatible with the current Nitte SEE format.")
    t0,t1,t2,t3=d.tables[:4]
    if len(t0.rows)>=2:
        set_cell(t0.rows[0].cells[1],meta.get("setter","")); set_cell(t0.rows[0].cells[3],meta.get("set",""))
        set_cell(t0.rows[1].cells[1],meta.get("department","")); set_cell(t0.rows[1].cells[3],meta.get("date",""))
    if len(t1.rows)>=5:
        set_cell(t1.rows[2].cells[0],f'{meta.get("semester","")} Semester B.Sc (CBCS) Degree Examinations')
        set_cell(t1.rows[3].cells[0],f'Academic Year: {meta.get("year","")}')
        set_cell(t1.rows[4].cells[0],f'{meta.get("code","")} – {meta.get("title","")} ({meta.get("scheme","")})\n(For {meta.get("branches","")})')
    # MCQs: current SEE template uses 3 rows/question
    for i,q in enumerate(paper["mcqs"][:50]):
        r=i*3
        if r+2>=len(t2.rows): break
        set_cell(t2.rows[r].cells[0],f"{i+1}.")
        try:
            t2.rows[r].cells[1].merge(t2.rows[r].cells[4])
        except Exception:
            pass
        set_cell(t2.rows[r].cells[1],q["question"])
        set_cell(t2.rows[r+1].cells[0],""); set_cell(t2.rows[r+1].cells[1],"A)"); set_cell(t2.rows[r+1].cells[2],q["options"]["A"]); set_cell(t2.rows[r+1].cells[3],"B)"); set_cell(t2.rows[r+1].cells[4],q["options"]["B"])
        set_cell(t2.rows[r+2].cells[0],""); set_cell(t2.rows[r+2].cells[1],"C)"); set_cell(t2.rows[r+2].cells[2],q["options"]["C"]); set_cell(t2.rows[r+2].cells[3],"D)"); set_cell(t2.rows[r+2].cells[4],q["options"]["D"])
    rows=[((1,2),(4,5)),((7,8),(10,11)),((13,14),(16,17)),((19,20),(22,23)),((25,26),(28,29))]
    qn=1
    for ui,pair in enumerate(paper["descriptive"][:5]):
        for alt,(ra,rb) in enumerate(rows[ui]):
            q=pair[alt]
            for rr,part,label in [(ra,q["a"],"a)"),(rb,q["b"],"b)")]:
                set_cell(t3.rows[rr].cells[0],str(qn) if label=="a)" else "")
                set_cell(t3.rows[rr].cells[1],label); set_cell(t3.rows[rr].cells[2],part["question"]); set_cell(t3.rows[rr].cells[3],part["marks"])
                set_cell(t3.rows[rr].cells[4],q.get("bt","")); set_cell(t3.rows[rr].cells[5],q.get("co","")); set_cell(t3.rows[rr].cells[6],q.get("po",""))
            qn+=1
    o=io.BytesIO(); d.save(o); return o.getvalue()

def fill_key_template(template_bytes,paper,meta):
    d=Document(io.BytesIO(template_bytes))
    if not d.tables: raise ValueError("MCQ answer-key template has no table.")
    for p in d.paragraphs:
        if "Program:" in p.text and "Semester:" in p.text: p.text=f'Program: B.Sc    Semester: {meta.get("semester","")}    QP SET No.: {meta.get("set","")}'
        elif "Course Code:" in p.text and "Course Title:" in p.text: p.text=f'Course Code: {meta.get("code","")}    Course Title: {meta.get("title","")}'
        elif p.text.strip().startswith("Name of the Faculty:"): p.text=f'Name of the Faculty: {meta.get("setter","")}'
        elif p.text.strip().startswith("Affiliation:"): p.text=f'Affiliation: {meta.get("department","")}'
    t=d.tables[0]; ans=[q["answer"].upper() for q in paper["mcqs"][:50]]
    for r in range(1,min(11,len(t.rows))):
        for b in range(5):
            n=r+b*10
            if n<=len(ans) and b*2+1<len(t.rows[r].cells):
                set_cell(t.rows[r].cells[b*2],f"{n}."); set_cell(t.rows[r].cells[b*2+1],ans[n-1])
    o=io.BytesIO(); d.save(o); return o.getvalue()

def fill_sol_template(template_bytes,paper,meta):
    d=Document(io.BytesIO(template_bytes))
    if len(d.tables)<2: raise ValueError("Scheme & Solution template structure is not compatible.")
    h=d.tables[0]
    if len(h.rows)>=2:
        set_cell(h.rows[0].cells[1],meta.get("title","")); set_cell(h.rows[0].cells[3],meta.get("code",""))
        set_cell(h.rows[1].cells[1],meta.get("setter","")); set_cell(h.rows[1].cells[3],meta.get("set",""))
    t=d.tables[1]
    while len(t.rows)>1: t._tbl.remove(t.rows[-1]._tr)
    n=1
    for pair in paper["descriptive"]:
        for q in pair:
            r=t.add_row().cells; set_cell(r[0],n); set_cell(r[1],f'a) {q["a"]["solution"]}\n\nb) {q["b"]["solution"]}'); set_cell(r[2],5); n+=1
    o=io.BytesIO(); d.save(o); return o.getvalue()

with st.sidebar:
    sets=st.slider("Target number of sets",1,4,1,help="For fastest generation, create one set at a time. You can continue later without losing completed sets.")
    difficulty=st.selectbox("Difficulty",["Easy","Easy–Moderate","Moderate","Moderate–Hard"],1)
    if st.button("Start Fresh / Clear Generated Sets",use_container_width=True):
        for k in ["papers","used_questions","zip"]:
            st.session_state.pop(k,None)
        st.rerun()

t1,t2,t3,t4=st.tabs(["1. Course Setup","2. Sources & Templates","3. Generate & Review","4. Export"])
with t1:
    a,b,c=st.columns(3); title=a.text_input("Course title"); code=b.text_input("Course code"); semester=c.text_input("Semester")
    a,b,c=st.columns(3); year=a.text_input("Academic year"); scheme=b.text_input("Scheme",value="2025 Scheme"); branches=c.text_input("Branches",value="CAPT / CAFD")
    a,b,c=st.columns(3); setter=a.text_input("QP setter / Faculty"); department=b.text_input("Department / Affiliation"); date=c.text_input("Date")
    co=st.text_area("Course Outcomes",height=140,placeholder="CO1 ...\nCO2 ...")

with t2:
    st.subheader("Source material")
    syllabus=st.file_uploader("Syllabus",["pdf","docx","txt"],key="sy")
    reference=st.file_uploader("Reference book / notes",["pdf","docx","txt"],key="ref")
    st.subheader("University Word templates")
    qp_template=st.file_uploader("Question Paper Template (.docx)",["docx"],key="qpt")
    key_template=st.file_uploader("MCQ Answer Key Template (.docx)",["docx"],key="akt")
    sol_template=st.file_uploader("Scheme & Solution Template (.docx)",["docx"],key="sot")
    if syllabus:
        with st.spinner("Reading syllabus (cached after the first read)..."):
            st.session_state["syllabus"]=read_file(syllabus)
        st.success("Syllabus ready ✓")
    if reference:
        with st.spinner("Reading reference material (cached after the first read)..."):
            st.session_state["reference"]=read_file(reference)
        st.success("Reference material ready ✓")

with t3:
    existing=len(st.session_state.get("papers",[]))
    st.caption(f"Completed sets in this session: {existing} / {sets}")
    c1,c2=st.columns(2)
    next_clicked=c1.button("Generate Next Set",type="primary",use_container_width=True,disabled=existing>=sets)
    all_clicked=c2.button("Generate Up To Target",use_container_width=True,disabled=existing>=sets)
    if next_clicked or all_clicked:
        if not st.session_state.get("syllabus") or not st.session_state.get("reference") or not co.strip():
            st.error("Enter COs and upload syllabus + reference material.")
        else:
            try:
                units=split_units(st.session_state["syllabus"])
                papers=st.session_state.get("papers",[])
                used=st.session_state.get("used_questions","")
                target=min(sets, len(papers)+(1 if next_clicked else sets-len(papers)))
                overall=st.progress(len(papers)/max(sets,1),text="Ready")
                for sidx in range(len(papers),target):
                    pending=st.session_state.get("pending_set")
                    if not pending or pending.get("setno") != sidx+1:
                        pending={"setno":sidx+1,"units":{}}
                        st.session_state["pending_set"]=pending
                    with st.status(f"Generating Set {sidx+1}...",expanded=True) as status:
                        for i,u in enumerate(units,1):
                            if str(i) in pending["units"]:
                                status.write(f"Unit {i} already saved ✓")
                                continue
                            status.write(f"Unit {i}: selecting relevant reference material...")
                            status.write(f"Unit {i}: generating with Gemini (temporary 503 errors are retried automatically)...")
                            x=generate(i,u,st.session_state["reference"],co,difficulty,used)
                            pending["units"][str(i)]=x
                            st.session_state["pending_set"]=pending
                            for q in x["mcqs"]:
                                used+="\n"+q["question"]
                            for q in x["descriptive"]:
                                used+="\n"+q["a"]["question"]+"\n"+q["b"]["question"]
                            st.session_state["used_questions"]=used
                            status.write(f"Unit {i} complete and saved ✓")
                        mc=[]; desc=[]
                        for i in range(1,6):
                            x=pending["units"][str(i)]
                            for q in x["mcqs"]:
                                q["unit"]=i; q.setdefault("po",""); mc.append(q)
                            desc.append(x["descriptive"])
                            for q in x["descriptive"]: q.setdefault("po","")
                        paper={"mcqs":balance(mc),"descriptive":desc}
                        papers.append(paper)
                        st.session_state["papers"]=papers
                        st.session_state.pop("pending_set",None)
                        status.update(label=f"Set {sidx+1} complete ✓",state="complete",expanded=False)
                    overall.progress(len(papers)/max(sets,1),text=f"{len(papers)} of {sets} set(s) complete")
                st.success(f"Generation finished. {len(papers)} set(s) are ready for review.")
            except Exception as e:
                st.error(f"Generation stopped: {e}")
                if st.session_state.get("papers"):
                    st.info("Completed sets and completed units of the current set were kept. Click Generate Next Set to resume from the failed unit.")
    if st.session_state.get("papers"):

        n=st.selectbox("Review Set",range(1,len(st.session_state["papers"])+1)); p=st.session_state["papers"][n-1]
        st.markdown("### MCQs")
        for i,q in enumerate(p["mcqs"],1):
            with st.expander(f'Q{i}. {q["question"]}'):
                q["question"]=st.text_area("Question",q["question"],key=f"q{n}_{i}")
                cols=st.columns(4)
                for j,L in enumerate("ABCD"): q["options"][L]=cols[j].text_input(L,q["options"][L],key=f"o{n}_{i}_{L}")
                q["answer"]=st.selectbox("Correct answer",list("ABCD"),index=list("ABCD").index(q["answer"]),key=f"a{n}_{i}")
        st.markdown("### Descriptive questions and solutions")
        qn=1
        for u,pair in enumerate(p["descriptive"],1):
            for alt,q in enumerate(pair,1):
                with st.expander(f"Question {qn} – Unit {u}"):
                    q["a"]["question"]=st.text_area("a) Question",q["a"]["question"],key=f"daq{n}_{u}_{alt}")
                    q["a"]["solution"]=st.text_area("a) Solution",q["a"]["solution"],height=110,key=f"das{n}_{u}_{alt}")
                    q["b"]["question"]=st.text_area("b) Question",q["b"]["question"],key=f"dbq{n}_{u}_{alt}")
                    q["b"]["solution"]=st.text_area("b) Solution",q["b"]["solution"],height=110,key=f"dbs{n}_{u}_{alt}")
                qn+=1

with t4:
    ps=st.session_state.get("papers",[])
    if not ps: st.info("Generate papers first.")
    elif not all([qp_template,key_template,sol_template]): st.info("Upload all three Word templates in Sources & Templates.")
    else:
        if st.button("Build DOCX Package Using Uploaded Templates",type="primary",use_container_width=True):
            try:
                qb,kb,sb=get_bytes(qp_template),get_bytes(key_template),get_bytes(sol_template)
                out=io.BytesIO()
                with zipfile.ZipFile(out,"w",zipfile.ZIP_DEFLATED) as z:
                    for i,p in enumerate(ps,1):
                        meta={"title":title,"code":code,"semester":semester,"year":year,"scheme":scheme,"branches":branches,"setter":setter,"department":department,"date":date,"set":str(i)}
                        z.writestr(f"Set_{i}/Question_Paper_Set_{i}.docx",fill_qp_template(qb,p,meta))
                        z.writestr(f"Set_{i}/MCQ_Answer_Key_Set_{i}.docx",fill_key_template(kb,p,meta))
                        z.writestr(f"Set_{i}/Scheme_Solution_Set_{i}.docx",fill_sol_template(sb,p,meta))
                st.session_state["zip"]=out.getvalue(); st.success("Template-based package ready.")
            except Exception as e: st.error(f"Export failed: {e}")
        if st.session_state.get("zip"):
            st.download_button("Download All Sets",st.session_state["zip"],"Question_Paper_Package.zip","application/zip",use_container_width=True)

st.divider()
st.caption("Public Web v2.2 Fast • Cached source extraction • unit-by-unit progress • automatic AI retries • one-set-at-a-time generation • template-based DOCX export.")
