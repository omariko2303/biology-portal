import streamlit as st
import sqlite3
import datetime
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
            student_answer TEXT,
            ai_draft TEXT,
            final_report TEXT,
            status TEXT,
            submitted_at TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# ==================== HELPER FUNCTIONS (GEMINI API) ====================
def analyze_text_gemini(student_name, assignment_title, instructions, student_answer):
    api_key = st.secrets.get("GEMINI_API_KEY", "").strip().strip('"').strip("'")
    
    if not api_key:
        raise Exception("GEMINI_API_KEY is missing in Streamlit Secrets! Please add it in App Settings -> Secrets.")

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-1.5-flash")

    prompt_text = f"""You are a Senior Cambridge IGCSE Biology (0610 / 0970) Chief Examiner.
Evaluate the student's submitted text answer.
Student Name: {student_name}
Assignment: {assignment_title}
Teacher Focus/Instructions: {instructions}

Student Answer:
{student_answer}

Provide a comprehensive diagnostic evaluation report in Markdown format:
1. Executive Summary & Estimated Raw Score / Grade Equivalent.
2. Strengths (AO1 Knowledge, AO2 Application, AO3 Practical).
3. Specific Misconceptions & Missing Cambridge Mark Scheme Keywords.
4. Actionable Next Steps for Improvement.
"""

    response = model.generate_content(prompt_text)
    return response.text

# ==================== MAIN UI ====================
st.title("🧬 IGCSE Biology Assessment & Teacher Portal")

tab1, tab2, tab3 = st.tabs([
    "📤 Student Portal (Submit Text Answer)", 
    "📊 Student Results (Approved Reports)", 
    "🔒 Teacher Dashboard (Review & Release)"
])

# -------------------- TAB 1: STUDENT SUBMIT --------------------
with tab1:
    st.header("Submit Homework Answer (Text Mode)")
    
    col1, col2 = st.columns(2)
    with col1:
        student_name = st.text_input("Student Name", placeholder="e.g., Omar")
    with col2:
        assignment_title = st.text_input("Assignment Title", placeholder="e.g., Cell Structure & Osmosis Quiz")
        
    instructions = st.text_area(
        "Teacher Instructions / Mark Scheme Focus", 
        value="Strictly enforce Cambridge Mark Scheme keywords (e.g. net movement, water potential, chloroplast vs chlorophyll, magnification formulas)."
    )
    
    student_answer = st.text_area(
        "Type or Paste Your Homework Answer Here", 
        placeholder="Write your biological explanations, definitions, and answers here...",
        height=200
    )
    
    if st.button("🚀 Submit Answer to Teacher", type="primary"):
        if not student_name or not assignment_title:
            st.error("❌ Please enter student name and assignment title.")
        elif not student_answer.strip():
            st.error("❌ Please write your answer before submitting.")
        else:
            with st.spinner("Analyzing answer with Gemini AI and submitting to teacher..."):
                try:
                    ai_draft = analyze_text_gemini(
                        student_name, assignment_title, instructions, student_answer
                    )
                    
                    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    c.execute('''
                        INSERT INTO submissions 
                        (student_name, assignment_title, student_answer, ai_draft, final_report, status, submitted_at)
                        VALUES (?, ?, ?, ?, ?, 'PENDING', ?)
                    ''', (student_name, assignment_title, student_answer, ai_draft, "", now))
                    conn.commit()
                    conn.close()
                    
                    st.success(f"✅ Submission successful, {student_name}! Your answer is pending teacher review. Results will appear here once approved.")
                except Exception as e:
                    st.error(f"⚠️ Error processing text: {e}")

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
        c.execute("SELECT id, student_name, assignment_title, student_answer, ai_draft, submitted_at FROM submissions WHERE status = 'PENDING'")
        pending = c.fetchall()
        conn.close()
        
        if pending:
            options = {f"ID #{row[0]} | Student: {row[1]} - {row[2]} ({row[5]})": row for row in pending}
            selected_option = st.selectbox("Select Pending Submission:", list(options.keys()))
            
            selected_row = options[selected_option]
            sub_id, s_name, a_title, s_answer, ai_draft, sub_time = selected_row
            
            st.divider()
            col_ans, col_edit = st.columns([1, 1])
            
            with col_ans:
                st.subheader("📝 Student's Submitted Answer")
                st.info(s_answer)
            
            with col_edit:
                st.subheader("✏️ AI Draft Evaluation (Teacher Edit)")
                final_report_input = st.text_area("Review and edit evaluation before releasing to student:", value=ai_draft, height=300)
                
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
       
 
             
