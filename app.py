import streamlit as st
import sqlite3
import datetime
import os
import tempfile
import google.generativeai as genai

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

# Default API Key
DEFAULT_API_KEY = ""

# ==================== HELPER FUNCTIONS ====================
def analyze_homework(api_key, file_bytes, mime_type, file_name, student_name, assignment_title, instructions):
    clean_key = api_key.strip()
    genai.configure(api_key=clean_key)
    
    ext = os.path.splitext(file_name)[1]
    if not ext:
        ext = ".pdf" if "pdf" in mime_type else ".jpg"
        
    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
        tmp.write(file_bytes)
        tmp_path = tmp.name

    try:
        uploaded_file = genai.upload_file(tmp_path, mime_type=mime_type)
        
        prompt = f"""You are a Senior Cambridge IGCSE Biology (0610 / 0970) Chief Examiner.
Evaluate the attached student answer sheet.
Student Name: {student_name}
Assignment: {assignment_title}
Teacher Focus/Instructions: {instructions}

Provide a detailed diagnostic evaluation report in Markdown:
1. Executive Summary & Estimated Raw Score / Grade Equivalent.
2. Strengths (AO1 Knowledge, AO2 Application, AO3 Practical).
3. Specific Misconceptions & Missing Cambridge Mark Scheme Keywords.
4. Actionable Next Steps for Improvement.
"""
        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content([uploaded_file, prompt])
        return response.text
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

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
    
    api_key_input = st.text_input("Gemini API Key", value=DEFAULT_API_KEY, type="password", help="Default key loaded automatically.")
    
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
        active_key = api_key_input if api_key_input.strip() else DEFAULT_API_KEY
        if not active_key:
            st.error("❌ Please enter your Gemini API Key.")
        elif not student_name or not assignment_title:
            st.error("❌ Please enter student name and assignment title.")
        elif not uploaded_file:
            st.error("❌ Please upload a homework file.")
        else:
            with st.spinner("Analyzing homework with AI and submitting to teacher..."):
                file_bytes = uploaded_file.read()
                mime_type = uploaded_file.type
                file_name = uploaded_file.name
                
                try:
                    # AI Processing
                    ai_draft = analyze_homework(
                        active_key, file_bytes, mime_type, file_name, 
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
    TEACHER_PIN = "1234"  # Change your secret PIN here
    
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
 
             
