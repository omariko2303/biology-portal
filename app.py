import streamlit as st
import sqlite3
import datetime
import os
import base64
import requests
import io

# ==================== PAGE CONFIG & SETUP ====================
st.set_page_config(
    page_title="IGCSE Biology Assessment Portal",
    page_icon="🧬",
    layout="wide"
)

# SQLite Database Setup
DB_FILE = "homework_portal.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_name TEXT,
            assignment_title TEXT,
            file_bytes BLOB,
            file_name TEXT,
            mime_type TEXT,
            ai_draft TEXT,
            final_report TEXT,
            status TEXT,
            submitted_at TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# ==================== HELPER FUNCTIONS (GROQ DYNAMIC API) ====================
def extract_pdf_text(file_bytes):
    """Extract text safely from PDF bytes"""
    try:
        import pypdf
        reader = pypdf.PdfReader(io.BytesIO(file_bytes))
        text = ""
        for page in reader.pages:
            t = page.extract_text()
            if t:
                text += t + "\n"
        return text if text.strip() else "PDF contains scanned images or handwritten work."
    except Exception:
        try:
            return file_bytes.decode('utf-8', errors='ignore')[:3000]
        except:
            return "PDF file submitted."

def get_best_groq_model(headers, is_vision=False):
    """Fetch available models dynamically from Groq account"""
    try:
        res = requests.get("https://api.groq.com/openai/v1/models", headers=headers, timeout=5)
        if res.status_code == 200:
            models_data = res.json().get("data", [])
            model_ids = [m["id"] for m in models_data]
            
            if is_vision:
                vision_models = [m for m in model_ids if "vision" in m or "ma-3.2" in m]
                if vision_models:
                    return vision_models[0]
            
            text_models = [m for m in model_ids if "llama" in m and "vision" not in m]
            if text_models:
                return text_models[0]
            
            if model_ids:
                return model_ids[0]
    except Exception:
        pass
    
    return "llama-3.2-11b-vision-preview" if is_vision else "llama-3.1-8b-instant"

def analyze_homework_groq(file_bytes, mime_type, student_name, assignment_title, instructions):
    raw_key = st.secrets.get("GROQ_API_KEY", "")
    api_key = raw_key.strip().strip('"').strip("'")
    
    if not api_key:
        raise Exception("GROQ_API_KEY is missing in Streamlit Secrets! Please add it in App Settings -> Secrets.")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    prompt_text = f"""You are a Senior Cambridge IGCSE Biology (0610 / 0970) Chief Examiner.
Evaluate the student answer sheet submission.
Student Name: {student_name}
Assignment: {assignment_title}
Teacher Focus/Instructions: {instructions}

Provide a detailed diagnostic evaluation report in Markdown format:
1. Executive Summary & Estimated Raw Score / Grade Equivalent.
2. Strengths (AO1 Knowledge, AO2 Application, AO3 Practical).
3. Specific Misconceptions & Missing Cambridge Mark Scheme Keywords.
4. Actionable Next Steps for Improvement.
"""

    is_image = "image" in mime_type
    selected_model = get_best_groq_model(headers, is_vision=is_image)

    if is_image:
        base64_image = base64.b64encode(file_bytes).decode('utf-8')
        payload = {
            "model": selected_model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt_text},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime_type};base64,{base64_image}"
                            }
                        }
                    ]
                }
            ],
            "temperature": 0.2
        }
    else:
        extracted_text = extract_pdf_text(file_bytes)
        payload = {
            "model": selected_model,
            "messages": [
                {
                    "role": "user",
                    "content": f"{prompt_text}\n\nStudent Work Text Content:\n{extracted_text[:4000]}"
                }
            ],
            "temperature": 0.2
        }

    response = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload)
    res_json = response.json()

    if response.status_code == 200:
        return res_json['choices'][0]['message']['content']
    elif response.status_code == 401:
        raise Exception("Invalid Groq API Key! Please double-check your key in Streamlit Secrets.")
    else:
        error_msg = res_json.get('error', {}).get('message', response.text)
        raise Exception(f"Groq API Error: {error_msg}")

# ==================== MAIN UI ====================
st.title("🧬 IGCSE Biology Assessment & Teacher Portal")

tab1, tab2, tab3 = st.tabs([
    "📤 Student Portal (Submit Homework)", 
    "📊 Student Results (Approved Reports)", 
    "🔒 Teacher Dashboard (Review & Release)"
])

# -------------------- TAB 1: STUDENT SUBMIT --------------------
with tab1:
    st.header("Upload Homework (PDF or Images)")
    
    col1, col2 = st.columns(2)
    with col1:
        student_name = st.text_input("Student Name", placeholder="e.g., Lara")
    with col2:
        assignment_title = st.text_input("Assignment Title", placeholder="e.g., Cell Structure & Osmosis Quiz")
        
    instructions = st.text_area(
        "Teacher Instructions / Mark Scheme Focus", 
        value="Strictly enforce Cambridge Mark Scheme keywords (e.g. net movement, water potential, chloroplast vs chlorophyll, magnification formulas)."
    )
    
    uploaded_file = st.file_uploader("Upload Homework File (PDF, PNG, JPG)", type=["pdf", "png", "jpg", "jpeg"])
    
    if st.button("🚀 Submit Homework to Teacher", type="primary"):
        if not student_name or not assignment_title:
            st.error("❌ Please enter student name and assignment title.")
        elif not uploaded_file:
            st.error("❌ Please upload a homework file.")
        else:
            with st.spinner("Analyzing homework with AI and submitting to teacher..."):
                file_bytes = uploaded_file.read()
                mime_type = uploaded_file.type
                file_name = uploaded_file.name
                
                try:
                    # AI Processing via Dynamic Groq Fetch
                    ai_draft = analyze_homework_groq(
                        file_bytes, mime_type, 
                        student_name, assignment_title, instructions
                    )
                    
                    # Save to DB as PENDING
                    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    c.execute('''
                        INSERT INTO submissions 
                        (student_name, assignment_title, file_bytes, file_name, mime_type, ai_draft, final_report, status, submitted_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, 'PENDING', ?)
                    ''', (student_name, assignment_title, file_bytes, file_name, mime_type, ai_draft, "", now))
                    conn.commit()
                    conn.close()
                    
                    st.success(f"✅ Submission successful, {student_name}! Your homework is pending teacher review. Results will be visible once approved.")
                except Exception as e:
                    st.error(f"⚠️ Error processing file: {e}")

# -------------------- TAB 2: STUDENT LOOKUP --------------------
with tab2:
    st.header("Check Approved Homework Reports")
    search_name = st.text_input("Enter Student Name to view approved results")
    
    if st.button("🔍 Search Reports"):
        if search_name.strip():
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute('''
                SELECT assignment_title, final_report, submitted_at 
                FROM submissions 
                WHERE LOWER(student_name) = LOWER(?) AND status = 'APPROVED'
                ORDER BY id DESC
            ''', (search_name.strip(),))
            results = c.fetchall()
            conn.close()
            
            if results:
                for row in results:
                    st.subheader(f"📚 {row[0]} (Approved Date: {row[2]})")
                    st.markdown(row[1])
                    st.divider()
            else:
                st.info("ℹ️ No approved reports found for this name yet. If you submitted recently, your teacher is still reviewing it.")

# -------------------- TAB 3: TEACHER DASHBOARD --------------------
with tab3:
    st.header("Teacher Review Dashboard")
    
    pin = st.text_input("Teacher Passcode (PIN)", type="password")
    TEACHER_PIN = "1234"
    
    if pin == TEACHER_PIN:
        st.success("🔓 Access Granted")
        
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT id, student_name, assignment_title, file_name, mime_type, ai_draft, submitted_at, file_bytes FROM submissions WHERE status = 'PENDING'")
        pending = c.fetchall()
        conn.close()
        
        if pending:
            options = {f"ID #{row[0]} | Student: {row[1]} - {row[2]} ({row[6]})": row for row in pending}
            selected_option = st.selectbox("Select Pending Submission:", list(options.keys()))
            
            selected_row = options[selected_option]
            sub_id, s_name, a_title, f_name, m_type, ai_draft, sub_time, f_bytes = selected_row
            
            st.divider()
            col_file, col_edit = st.columns([1, 1])
            
            with col_file:
                st.subheader("📄 Uploaded Student File")
                if "image" in m_type:
                    st.image(f_bytes)
                else:
                    st.download_button(
                        label=f"⬇️ Download Student PDF ({f_name})",
                        data=f_bytes,
                        file_name=f_name,
                        mime=m_type
                    )
            
            with col_edit:
                st.subheader("✏️ AI Draft Evaluation (Teacher Edit)")
                final_report_input = st.text_area("Review and edit evaluation before releasing to student:", value=ai_draft, height=400)
                
                if st.button("✅ Approve & Release Report to Student", type="primary"):
                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    c.execute('''
                        UPDATE submissions 
                        SET final_report = ?, status = 'APPROVED' 
                        WHERE id = ?
                    ''', (final_report_input, sub_id))
                    conn.commit()
                    conn.close()
                    st.balloons()
                    st.success("🎉 Report approved and released to student!")
                    st.rerun()
        else:
            st.info("🎉 No pending submissions to review!")
    elif pin != "":
        st.error("🔒 Incorrect PIN!")
       
 
             
