import streamlit as st
import sqlite3
import datetime
import pypdf
import io
import google.generativeai as genai

# ==================== PAGE CONFIG & SETUP ====================
st.set_page_config(
    page_title="IGCSE Biology Assessment Portal",
    page_icon="🧬",
    layout="wide"
)

# SQLite Database Setup
DB_FILE = "homework_portal_v3.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_name TEXT,
            assignment_title TEXT,
            file_name TEXT,
            file_bytes BLOB,
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

# ==================== HELPER: GEMINI AI VISION ANALYSIS ====================
def analyze_homework_gemini(student_name, assignment_title, instructions, file_bytes, mime_type, file_name):
    api_key = st.secrets.get("GEMINI_API_KEY", "").strip().strip('"').strip("'")
    
    if not api_key:
        raise Exception("GEMINI_API_KEY is missing in Streamlit Secrets! Please add it in App Settings -> Secrets.")

    genai.configure(api_key=api_key)
    
    # استخدام النموذج المعتمد
    model = genai.GenerativeModel("gemini-3.8-flash")

    prompt_text = f"""You are a Senior Cambridge IGCSE Biology (0610 / 0970) Chief Examiner.
You are evaluating a student's actual homework submission attached as an image, scan, or PDF.
Candidate Name: {student_name}
Assignment: {assignment_title}
Teacher Focus & Instructions: {instructions}

Carefully inspect the handwritten answers, text, or diagrams in the attached document. Provide a comprehensive, rigorous Cambridge-style diagnostic evaluation report in Markdown format:
1. **Executive Summary & Estimated Raw Score / Grade Equivalent** (Provide a realistic estimated score out of total marks based on what is written).
2. **Detailed Question-by-Question Breakdown & Mark Scheme Alignment** (Analyze what the student wrote, pointing out exact correct keywords used vs. missing Cambridge mark scheme keywords).
3. **Specific Misconceptions & Errors** (Correct any biological inaccuracies, e.g., water potential vs water concentration, chloroplast vs chlorophyll).
4. **Actionable Next Steps for Improvement** (Precise guidance for the student to achieve an A*).
"""

    # إرسال الملف مباشرة كجزء بصري أو ثنائي ليعمل Gemini على تحليله وقراءته بشكل حقيقي
    if mime_type and "image" in mime_type:
        file_part = {
            "mime_type": mime_type,
            "data": file_bytes
        }
    else:
        # إذا كان PDF نرسله كملف ثنائي ليقوم النموذج بقراءته وفحصه بصرياً
        file_part = {
            "mime_type": "application/pdf",
            "data": file_bytes
        }

    response = model.generate_content([prompt_text, file_part])
    return response.text

# ==================== MAIN UI ====================
st.title("🧬 IGCSE Biology Assessment & Teacher Portal")

tab1, tab2, tab3 = st.tabs([
    "📤 Student Portal (Submit Homework)", 
    "📊 Student Results & Status Lookup", 
    "🔒 Teacher Review Dashboard"
])

# -------------------- TAB 1: STUDENT SUBMIT --------------------
with tab1:
    st.header("Upload Homework (PDF, JPG, or PNG)")
    
    col1, col2 = st.columns(2)
    with col1:
        student_name = st.text_input("Student Name", placeholder="e.g., Lara")
    with col2:
        assignment_title = st.text_input("Assignment Title", placeholder="e.g., hw")
        
    instructions = st.text_area(
        "Teacher Instructions / Mark Scheme Focus", 
        value="Strictly enforce Cambridge Mark Scheme keywords (e.g. net movement, water potential, chloroplast vs chlorophyll, magnification formulas, active transport)."
    )
    
    uploaded_file = st.file_uploader(
        "Upload Homework File (Accepted formats: PDF, PNG, JPG, JPEG)", 
        type=["pdf", "png", "jpg", "jpeg"]
    )
    
    if st.button("🚀 Submit Homework to Teacher & AI", type="primary"):
        if not student_name or not assignment_title:
            st.error("❌ Please enter student name and assignment title.")
        elif not uploaded_file:
            st.error("❌ Please upload a homework file.")
        else:
            with st.spinner("Analyzing student work with Gemini AI vision and submitting..."):
                file_bytes = uploaded_file.read()
                file_name = uploaded_file.name
                mime_type = uploaded_file.type if uploaded_file.type else "application/pdf"
                
                try:
                    # توليد تقييم حقيقي يعتمد على قراءة الملف
                    ai_draft = analyze_homework_gemini(
                        student_name, assignment_title, instructions, file_bytes, mime_type, file_name
                    )
                    
                    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    c.execute('''
                        INSERT INTO submissions 
                        (student_name, assignment_title, file_name, file_bytes, mime_type, ai_draft, final_report, status, submitted_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, 'PENDING', ?)
                    ''', (student_name, assignment_title, file_name, file_bytes, mime_type, ai_draft, "", now))
                    conn.commit()
                    conn.close()
                    
                    st.success(f"✅ Submission successful, {student_name}! Your homework has been evaluated by AI and sent to the teacher for review.")
                except Exception as e:
                    st.error(f"⚠️ Error during AI processing: {e}")

# -------------------- TAB 2: STUDENT LOOKUP --------------------
with tab2:
    st.header("Check Submission Status & Approved Reports")
    search_name = st.text_input("Enter Your Student Name to Lookup Results")
    
    if st.button("🔍 Check My Submissions"):
        if search_name.strip():
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute('''
                SELECT assignment_title, file_name, final_report, status, submitted_at 
                FROM submissions 
                WHERE LOWER(student_name) = LOWER(?)
                ORDER BY id DESC
            ''', (search_name.strip(),))
            results = c.fetchall()
            conn.close()
            
            if results:
                for row in results:
                    a_title, f_name, report, status, sub_time = row
                    
                    if status == 'APPROVED':
                        st.success(f"📚 **{a_title}** — Status: **APPROVED** (Submitted: {sub_time})")
                        st.markdown(report)
                        st.download_button(
                            label="📥 Download Approved Report as Text",
                            data=report,
                            file_name=f"{a_title}_Report.txt",
                            mime="text/plain"
                        )
                    else:
                        st.warning(f"⏳ **{a_title}** — Status: **PENDING REVIEW** (Submitted: {sub_time}). Your teacher is currently reviewing your assignment.")
                    st.divider()
            else:
                st.info("ℹ️ No submissions found for this name. Make sure you entered the exact name used during submission.")

# -------------------- TAB 3: TEACHER DASHBOARD --------------------
with tab3:
    st.header("Teacher Review Dashboard")
    
    pin = st.text_input("Teacher Passcode (PIN)", type="password")
    TEACHER_PIN = "1234"
    
    if pin == TEACHER_PIN:
        st.success("🔓 Access Granted")
        
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM submissions WHERE status = 'PENDING'")
        pending_count = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM submissions WHERE status = 'APPROVED'")
        approved_count = c.fetchone()[0]
        conn.close()
        
        m1, m2 = st.columns(2)
        m1.metric("Pending Reviews ⏳", pending_count)
        m2.metric("Approved Reports ✅", approved_count)
        st.divider()
        
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT id, student_name, assignment_title, file_name, mime_type, file_bytes, ai_draft, submitted_at FROM submissions WHERE status = 'PENDING'")
        pending_list = c.fetchall()
        conn.close()
        
        if pending_list:
            options = {f"ID #{row[0]} | Student: {row[1]} - {row[2]} ({row[7]})": row for row in pending_list}
            selected_option = st.selectbox("Select Pending Submission to Review:", list(options.keys()))
            
            selected_row = options[selected_option]
            sub_id, s_name, a_title, f_name, m_type, f_bytes, ai_draft, sub_time = selected_row
            
            st.divider()
            col_file, col_edit = st.columns([1, 1])
            
            with col_file:
                st.subheader(f"📄 Student File ({f_name})")
                if m_type and "image" in m_type:
                    st.image(f_bytes, caption=f"Submitted by {s_name}", use_column_width=True)
                else:
                    st.download_button(
                        label=f"⬇ Download Student File",
                        data=f_bytes,
                        file_name=f_name,
                        mime=m_type if m_type else "application/pdf"
                    )
            
            with col_edit:
                st.subheader("✏️ AI Draft Evaluation (Teacher Editing)")
                final_report_input = st.text_area("Review and refine the AI diagnostic report before release:", value=ai_draft, height=450)
                
                if st.button("✅ Approve & Publish Report to Student", type="primary"):
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
                    st.success("🎉 Report approved and successfully released to the student portal!")
                    st.rerun()
        else:
            st.info("🎉 All caught up! No pending student submissions to review.")
    elif pin != "":
        st.error("🔒 Incorrect PIN!")
       
 
             
