import streamlit as st
import sqlite3
import datetime
import base64
import os
import io
import google.generativeai as genai

# ==========================================
# 1. STREAMLIT PAGE CONFIG & CUSTOM STYLING
# ==========================================
st.set_page_config(
    page_title="IGCSE Biology Assessment Portal",
    page_icon="🧬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for polished Cambridge/Academic aesthetic
st.markdown("""
<style>
    /* Main Theme Overrides */
    .stApp {
        background-color: #f8f9fa;
    }
    
    /* Headers & Typography */
    h1, h2, h3 {
        font-family: 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
        color: #1a365d;
    }
    
    /* Custom Badges */
    .badge-pending {
        background-color: #fef3c7;
        color: #92400e;
        padding: 4px 12px;
        border-radius: 12px;
        font-weight: 600;
        font-size: 0.85rem;
    }
    .badge-approved {
        background-color: #d1fae5;
        color: #065f46;
        padding: 4px 12px;
        border-radius: 12px;
        font-weight: 600;
        font-size: 0.85rem;
    }
    
    /* Stats Metric Cards */
    .metric-card {
        background-color: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 10px;
        padding: 16px;
        text-align: center;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }
    .metric-card h3 {
        margin: 0;
        font-size: 2rem;
        color: #0d9488;
    }
    .metric-card p {
        margin: 4px 0 0 0;
        color: #64748b;
        font-size: 0.9rem;
    }
    
    /* Report Container */
    .report-box {
        background-color: #ffffff;
        border: 1px solid #cbd5e1;
        border-left: 5px solid #0284c7;
        padding: 20px;
        border-radius: 6px;
        margin-top: 10px;
    }
</style>
""", unsafe_allow_html=True)


# ==========================================
# 2. DATABASE MANAGEMENT (SQLite)
# ==========================================
DB_FILE = "homework_portal.db"

def get_db_connection():
    """Returns a thread-safe connection to the SQLite database."""
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initializes SQLite database and creates submissions table if not present."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_name TEXT NOT NULL,
            assignment_title TEXT NOT NULL,
            teacher_instructions TEXT,
            file_bytes BLOB NOT NULL,
            file_name TEXT NOT NULL,
            mime_type TEXT NOT NULL,
            ai_draft_report TEXT NOT NULL,
            final_report TEXT DEFAULT '',
            status TEXT DEFAULT 'PENDING',
            submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

# Initialize DB on app load
init_db()

def save_submission(student_name, assignment_title, teacher_instructions, file_bytes, file_name, mime_type, ai_draft_report):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO submissions (student_name, assignment_title, teacher_instructions, file_bytes, file_name, mime_type, ai_draft_report, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'PENDING')
    """, (student_name, assignment_title, teacher_instructions, sqlite3.Binary(file_bytes), file_name, mime_type, ai_draft_report))
    conn.commit()
    sub_id = cursor.lastrowid
    conn.close()
    return sub_id

def get_pending_submissions():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, student_name, assignment_title, teacher_instructions, file_name, mime_type, ai_draft_report, submitted_at
        FROM submissions 
        WHERE status = 'PENDING' 
        ORDER BY submitted_at DESC
    """)
    rows = cursor.fetchall()
    conn.close()
    return rows

def get_submission_by_id(sub_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM submissions WHERE id = ?", (sub_id,))
    row = cursor.fetchone()
    conn.close()
    return row

def update_submission_approval(sub_id, final_report):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE submissions 
        SET final_report = ?, status = 'APPROVED' 
        WHERE id = ?
    """, (final_report, sub_id))
    conn.commit()
    conn.close()

def search_approved_submissions(student_name):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, student_name, assignment_title, final_report, submitted_at
        FROM submissions 
        WHERE LOWER(student_name) = LOWER(?) AND status = 'APPROVED'
        ORDER BY submitted_at DESC
    """, (student_name.strip(),))
    rows = cursor.fetchall()
    conn.close()
    return rows

def get_portal_stats():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM submissions WHERE status = 'PENDING'")
    pending = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM submissions WHERE status = 'APPROVED'")
    approved = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM submissions")
    total = cursor.fetchone()[0]
    conn.close()
    return pending, approved, total


# ==========================================
# 3. GEMINI AI EVALUATION ENGINE
# ==========================================
def get_gemini_api_key():
    """Retrieves API key from Streamlit secrets or sidebar input fallback."""
    if "GEMINI_API_KEY" in st.secrets:
        return st.secrets["GEMINI_API_KEY"]
    elif "gemini_api_key" in st.session_state:
        return st.session_state["gemini_api_key"]
    return None

def evaluate_submission_with_gemini(api_key, student_name, assignment_title, teacher_instructions, file_bytes, mime_type):
    """
    Evaluates student homework using Gemini 1.5 Flash model with in-memory multimodal payload.
    """
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-1.5-flash")

    system_prompt = f"""
You are acting as a Senior Chief Examiner for Cambridge IGCSE Biology (Syllabus 0610 / 0970).
Your task is to thoroughly mark and evaluate the attached student homework submission.

### ASSIGNMENT CONTEXT:
- **Student Name:** {student_name}
- **Assignment Title:** {assignment_title}
- **Teacher Focus & Specific Mark Scheme Criteria:** 
  {teacher_instructions}

### ASSESSMENT STANDARDS & FRAMEWORK:
Evaluate the student's work strictly against Cambridge IGCSE Biology Assessment Objectives:
1. **AO1 - Knowledge with Understanding:** Accurate scientific terms (e.g. active site, denature, turgid, flaccid, pathogen, transpiration stream, limiting factor, allele, codominance).
2. **AO2 - Handling Information & Problem Solving:** Applying biological principles to new contexts, graph interpretations, numerical calculations (including magnification $M = I / A$).
3. **AO3 - Experimental Skills & Investigations:** Identifying variables (independent, dependent, controlled), experimental errors, and improvements.

### REQUIRED EVALUATION REPORT STRUCTURE:
Generate a detailed, constructive feedback report formatted in Markdown:

---
# 🧬 IGCSE Biology Assessment Draft Report

### 📊 Overall Grade & Marks Estimate
- **Estimated Cambridge Grade:** [e.g., A* (9), A (8), B (7), C (5), etc.]
- **Mark Summary:** [Estimated Mark / Total Mark, e.g., 28/35]

### 💡 Strengths & Effective Terminology
- Bullet points highlighting precise terminology used correctly.
- Conceptual mastery shown in biological diagrams, calculations, or explanations.

### ⚠️ Areas for Improvement & Misconceptions
- Specific biological inaccuracies or incomplete definitions.
- Missing Cambridge mark scheme keywords (e.g., mentioning "cell wall expands" instead of "exerts turgor pressure").

### 📝 Question-by-Question Detailed Breakdown
Break down the student's responses visible in the uploaded work, specifying:
- **Correct points awarded**
- **Missing mark-scheme points**
- **Examiner's tip for higher tier performance**

### 🎯 Next Steps & Target Action
- 2-3 concise action items for the student to revise.
---
"""

    # Direct memory payload for multimodal API (supports PDF and images)
    file_part = {
        "mime_type": mime_type,
        "data": file_bytes
    }

    response = model.generate_content([system_prompt, file_part])
    return response.text


# ==========================================
# 4. MAIN APP INTERFACE
# ==========================================
st.title("🧬 IGCSE Biology Assessment & Teacher Portal")
st.caption("AI-Powered Cambridge IGCSE (0610/0970) Evaluation & Teacher Moderation Engine")

# Sidebar Configuration & Secrets Management
with st.sidebar:
    st.header("⚙️ Portal Settings")
    api_key = get_gemini_api_key()
    
    if not api_key:
        st.warning("⚠️ Gemini API Key missing from `secrets.toml`.")
        user_key = st.text_input("Enter Gemini API Key:", type="password")
        if user_key:
            st.session_state["gemini_api_key"] = user_key
            st.success("API Key saved for current session!")
            st.rerun()
    else:
        st.success("🔑 Gemini API Key Active")

    st.divider()
    st.markdown("### 📌 Cambridge Syllabus")
    st.info("**Syllabus Code:** 0610 / 0970\n\n**Core AO Target:** AO1, AO2, AO3\n\n**Engine:** Gemini 1.5 Flash")


# Main App Navigation Tabs
tab1, tab2, tab3 = st.tabs([
    "📤 Submit Homework", 
    "📊 Student Results", 
    "🔒 Teacher Dashboard"
])

# ------------------------------------------
# TAB 1: STUDENT SUBMISSION PORTAL
# ------------------------------------------
with tab1:
    st.subheader("Submit Your Biology Homework")
    st.write("Upload your completed handwritten or typed homework (PDF or Images) for instant AI evaluation.")

    with st.form("submission_form", clear_on_submit=False):
        col_a, col_b = st.columns(2)
        with col_a:
            student_name = st.text_input("Student Full Name *", placeholder="e.g. Sarah Ahmed")
        with col_b:
            assignment_title = st.text_input("Assignment Title *", placeholder="e.g. Enzymes & Rates of Reaction Worksheet")

        teacher_instructions = st.text_area(
            "Teacher Mark Scheme Focus / Key Topics (Optional)",
            value="Focus on enzyme active site specificity, denaturation mechanisms, optimum pH/temperature graphs, and precise usage of collision theory terms.",
            height=100,
            help="Provide syllabus guidelines or specific criteria for the AI examiner to focus on."
        )

        uploaded_file = st.file_uploader(
            "Upload Submission (PDF, PNG, JPG, JPEG) *",
            type=["pdf", "png", "jpg", "jpeg"],
            help="Heavy PDFs and image scans are directly evaluated."
        )

        submit_btn = st.form_submit_button("🚀 Submit Homework for Marking", use_container_width=True)

    if submit_btn:
        active_key = get_gemini_api_key()
        if not active_key:
            st.error("Please configure your Gemini API Key in the sidebar or `.streamlit/secrets.toml` to submit.")
        elif not student_name.strip():
            st.error("Please enter your Student Name.")
        elif not assignment_title.strip():
            st.error("Please enter the Assignment Title.")
        elif uploaded_file is None:
            st.error("Please upload your homework file (PDF or Image).")
        else:
            try:
                with st.spinner("🤖 Chief Examiner AI is reviewing your submission against Cambridge Mark Schemes..."):
                    file_bytes = uploaded_file.read()
                    mime_type = uploaded_file.type
                    file_name = uploaded_file.name

                    # Fallback mime-type mapping for images
                    if mime_type == "image/jpg":
                        mime_type = "image/jpeg"

                    ai_draft = evaluate_submission_with_gemini(
                        api_key=active_key,
                        student_name=student_name,
                        assignment_title=assignment_title,
                        teacher_instructions=teacher_instructions,
                        file_bytes=file_bytes,
                        mime_type=mime_type
                    )

                    sub_id = save_submission(
                        student_name=student_name,
                        assignment_title=assignment_title,
                        teacher_instructions=teacher_instructions,
                        file_bytes=file_bytes,
                        file_name=file_name,
                        mime_type=mime_type,
                        ai_draft_report=ai_draft
                    )

                    st.balloons()
                    st.success(f"🎉 Homework successfully submitted! Reference ID: #{sub_id}")
                    st.info("📌 Status: **PENDING TEACHER REVIEW**. Once your teacher reviews and approves the report, you can view it under the **'Student Results'** tab.")
                    
                    with st.expander("🔍 Preview Draft AI Evaluation (Pending Review)"):
                        st.markdown(ai_draft)

            except Exception as e:
                st.error(f"Error evaluating submission: {str(e)}")


# ------------------------------------------
# TAB 2: STUDENT RESULTS LOOKUP
# ------------------------------------------
with tab2:
    st.subheader("Lookup Released Assessment Reports")
    st.write("Enter your full name as submitted to search for teacher-released evaluation reports.")

    search_name = st.text_input("Enter Student Name to Search:", placeholder="e.g. Sarah Ahmed")
    
    if search_name.strip():
        results = search_approved_submissions(search_name)
        if results:
            st.success(f"Found {len(results)} approved report(s) for '{search_name}'")
            for row in results:
                with st.expander(f"📖 {row['assignment_title']} (Submitted: {row['submitted_at']})", expanded=True):
                    st.markdown(f"<div class='report-box'>{row['final_report']}</div>", unsafe_allow_html=True)
                    st.download_button(
                        label="📥 Download Report (.md)",
                        data=row['final_report'],
                        file_name=f"{row['student_name']}_{row['assignment_title']}_Report.md",
                        mime="text/markdown",
                        key=f"dl_{row['id']}"
                    )
        else:
            st.info(f"No approved reports found for '{search_name}'. If you submitted recently, your teacher may still be reviewing your work.")


# ------------------------------------------
# TAB 3: TEACHER REVIEW DASHBOARD
# ------------------------------------------
with tab3:
    st.subheader("Teacher Moderation & Approval Dashboard")

    # Secure Passcode Verification
    if "teacher_authenticated" not in st.session_state:
        st.session_state["teacher_authenticated"] = False

    if not st.session_state["teacher_authenticated"]:
        col1, col2 = st.columns([1, 2])
        with col1:
            passcode = st.text_input("Enter Teacher Passcode / PIN:", type="password", key="pin_input")
            if st.button("Unlock Dashboard", use_container_width=True):
                if passcode == "1234":  # Default PIN
                    st.session_state["teacher_authenticated"] = True
                    st.rerun()
                else:
                    st.error("Incorrect Passcode. Default PIN is '1234'.")
    else:
        # Teacher Top Bar
        top_col1, top_col2 = st.columns([3, 1])
        with top_col1:
            st.write("Welcome, **Cambridge Biology Moderator**. Review, edit, and release reports below.")
        with top_col2:
            if st.button("🔒 Lock Dashboard"):
                st.session_state["teacher_authenticated"] = False
                st.rerun()

        st.divider()

        # Analytics Metrics
        pending_cnt, approved_cnt, total_cnt = get_portal_stats()
        m_col1, m_col2, m_col3 = st.columns(3)
        with m_col1:
            st.markdown(f"<div class='metric-card'><h3>{pending_cnt}</h3><p>Pending Review</p></div>", unsafe_allow_html=True)
        with m_col2:
            st.markdown(f"<div class='metric-card'><h3>{approved_cnt}</h3><p>Approved Reports</p></div>", unsafe_allow_html=True)
        with m_col3:
            st.markdown(f"<div class='metric-card'><h3>{total_cnt}</h3><p>Total Submissions</p></div>", unsafe_allow_html=True)

        st.write("")
        st.subheader("Pending Submissions")

        pending_items = get_pending_submissions()
        if not pending_items:
            st.success("✨ All caught up! No pending submissions to review.")
        else:
            # Dropdown selection for pending submission
            options = {f"#{item['id']} - {item['student_name']} ({item['assignment_title']})": item['id'] for item in pending_items}
            selected_label = st.selectbox("Select Submission to Evaluate:", list(options.keys()))
            selected_id = options[selected_label]

            # Retrieve full submission data (including raw file bytes)
            sub_data = get_submission_by_id(selected_id)

            st.markdown("---")
            
            # Split View Layout: Left = Student Submission File, Right = AI Report Editor
            left_col, right_col = st.columns([1, 1])

            with left_col:
                st.markdown("### 📄 Student Submitted Work")
                st.write(f"**Student:** {sub_data['student_name']}")
                st.write(f"**Assignment:** {sub_data['assignment_title']}")
                st.write(f"**Submitted:** {sub_data['submitted_at']}")
                st.write(f"**File Name:** `{sub_data['file_name']}`")
                
                if sub_data['teacher_instructions']:
                    with st.expander("Teacher Instructions / Key Topics Focus"):
                        st.write(sub_data['teacher_instructions'])

                # Render File Preview or Download
                file_b = sub_data['file_bytes']
                mtype = sub_data['mime_type']

                if mtype.startswith("image/"):
                    st.image(file_b, caption=f"Submitted Image: {sub_data['file_name']}", use_column_width=True)
                elif mtype == "application/pdf":
                    st.info("📄 PDF File Uploaded.")
                    st.download_button(
                        label="⬇️ Download PDF Submission",
                        data=file_b,
                        file_name=sub_data['file_name'],
                        mime="application/pdf",
                        use_container_width=True
                    )
                    # Embed PDF preview via base64 HTML object tag
                    base64_pdf = base64.b64encode(file_b).decode('utf-8')
                    pdf_display = f'<iframe src="data:application/pdf;base64,{base64_pdf}" width="100%" height="500" type="application/pdf"></iframe>'
                    st.markdown(pdf_display, unsafe_allow_html=True)

            with right_col:
                st.markdown("### 📝 Edit & Approve Assessment Report")
                st.caption("Modify the AI draft feedback below before releasing it to the student.")

                edited_report = st.text_area(
                    "Final Report Editor (Markdown Supported):",
                    value=sub_data['ai_draft_report'],
                    height=500
                )

                if st.button("✅ Approve & Release to Student", type="primary", use_container_width=True):
                    update_submission_approval(selected_id, edited_report)
                    st.success(f"Report for submission #{selected_id} approved and released successfully!")
                    st.rerun()
       
 
             
