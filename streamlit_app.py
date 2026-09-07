import io, json, re, zipfile, requests
import streamlit as st
from pypdf import PdfReader
from docx import Document

st.set_page_config(page_title="Question Paper Maker",page_icon="📝",layout="wide")
st.title("📝 Question Paper Maker")
st.caption("Public web version — generate question papers, MCQ keys and proper solutions from your own source material.")

def read_file(f):
    f.seek(0)
    if f.name.lower().endswith(".pdf"):
        return "\n".join((p.extract_text() or "") for p in PdfReader(f).pages)
    if f.name.lower().endswith(".docx"):
        d=Document(f); out=[p.text for p in d.paragraphs if p.text.strip()]
        for t in d.tables:
            for r in t.rows:
                s=" | ".join(c.text.strip() for c in r.cells if c.text.strip())
                if s: out.append(s)
        return "\n".join(out)
    return f.read().decode("utf-8",errors="ignore")

def split_units(text):
    m=list(re.finditer(r"(?im)\bunit\s*[-–:]?\s*(?:[ivx]+|\d+)\b",text))
    if len(m)<5: raise ValueError("Five Unit headings were not detected. Please use Unit 1 ... Unit 5 headings.")
    out=[]
    for i,x in enumerate(m[:5]):
        end=m[i+1].start() if i+1<len(m) else len(text)
        out.append(text[x.start():end].strip())
    return out

def call_ai(prompt):
    key=st.secrets.get("GEMINI_API_KEY","")
    model=st.secrets.get("GEMINI_MODEL","gemini-2.5-flash")
    if not key: raise RuntimeError("Website owner has not configured the AI key.")
    url=f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
    payload={"contents":[{"parts":[{"text":prompt}]}],
             "generationConfig":{"temperature":0.25,"responseMimeType":"application/json"}}
    r=requests.post(url,json=payload,timeout=240)
    if not r.ok: raise RuntimeError(f"AI service error {r.status_code}: {r.text[:300]}")
    return r.json()["candidates"][0]["content"]["parts"][0]["text"]

def get_json(s):
    s=re.sub(r"^```(?:json)?\s*","",s.strip()); s=re.sub(r"\s*```$","",s)
    return json.loads(s)

def generate(unit_no,unit,reference,co,difficulty,used):
    # Keep prompt size practical for a public MVP.
    ref=reference[:30000]
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
        raise ValueError("AI returned an incomplete unit. Please regenerate.")
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

with st.sidebar:
    sets=st.slider("Number of sets",1,4,1)
    difficulty=st.selectbox("Difficulty",["Easy","Easy–Moderate","Moderate","Moderate–Hard"],1)

t1,t2,t3=st.tabs(["1. Course & Sources","2. Generate & Review","3. Download"])
with t1:
    a,b=st.columns(2); title=a.text_input("Course title"); code=b.text_input("Course code")
    co=st.text_area("Course Outcomes",height=140,placeholder="CO1 ...\nCO2 ...")
    syllabus=st.file_uploader("Syllabus",["pdf","docx","txt"])
    reference=st.file_uploader("Reference book / notes",["pdf","docx","txt"])
    if syllabus: st.session_state["syllabus"]=read_file(syllabus); st.success("Syllabus loaded.")
    if reference: st.session_state["reference"]=read_file(reference); st.success("Reference material loaded.")

with t2:
    if st.button("Generate Question Papers",type="primary",use_container_width=True):
        if not st.session_state.get("syllabus") or not st.session_state.get("reference") or not co.strip():
            st.error("Enter COs and upload syllabus + reference material.")
        else:
            try:
                units=split_units(st.session_state["syllabus"]); papers=[]; used=""; bar=st.progress(0)
                for s in range(sets):
                    mc=[]; desc=[]
                    for i,u in enumerate(units,1):
                        x=generate(i,u,st.session_state["reference"],co,difficulty,used)
                        for q in x["mcqs"]:
                            q["unit"]=i; mc.append(q); used+="\n"+q["question"]
                        desc.append(x["descriptive"])
                        for q in x["descriptive"]: used+="\n"+q["a"]["question"]+"\n"+q["b"]["question"]
                    papers.append({"mcqs":balance(mc),"descriptive":desc}); bar.progress((s+1)/sets)
                st.session_state["papers"]=papers; st.success("Generation complete.")
            except Exception as e: st.error(str(e))
    if st.session_state.get("papers"):
        n=st.selectbox("Preview Set",range(1,len(st.session_state["papers"])+1))
        p=st.session_state["papers"][n-1]
        st.write(f"**{len(p['mcqs'])} MCQs generated.**")
        for i,q in enumerate(p["mcqs"],1):
            with st.expander(f"Q{i}. {q['question']}"):
                st.write("A)",q["options"]["A"]); st.write("B)",q["options"]["B"])
                st.write("C)",q["options"]["C"]); st.write("D)",q["options"]["D"])
                st.caption(f"Correct: {q['answer']} | {q.get('bt','')} | {q.get('co','')}")

with t3:
    if not st.session_state.get("papers"): st.info("Generate papers first.")
    else:
        if st.button("Prepare Download Package",type="primary",use_container_width=True):
            out=io.BytesIO()
            with zipfile.ZipFile(out,"w",zipfile.ZIP_DEFLATED) as z:
                for i,p in enumerate(st.session_state["papers"],1):
                    z.writestr(f"Set_{i}/Question_Paper_Set_{i}.docx",make_qp_doc(p,title,code,i))
                    z.writestr(f"Set_{i}/MCQ_Answer_Key_Set_{i}.docx",make_key_doc(p,title,code,i))
                    z.writestr(f"Set_{i}/Scheme_Solution_Set_{i}.docx",make_sol_doc(p,title,code,i))
            st.session_state["zip"]=out.getvalue()
        if st.session_state.get("zip"):
            st.download_button("Download Question Papers + Keys + Solutions",st.session_state["zip"],
                               "Question_Paper_Package.zip","application/zip",use_container_width=True)

st.divider()
st.caption("Public Web v2 MVP • Review generated examination content before official use. AI usage is subject to the website owner's provider quota.")
