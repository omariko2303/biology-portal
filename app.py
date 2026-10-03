import streamlit as st
import sqlite3
import datetime
import io
import random
import google.generativeai as genai

# ---------------------------------------------------------
# PAGE CONFIGURATION & CUSTOM STYLES
# ---------------------------------------------------------
st.set_page_config(
    page_title="IGCSE Biology Assessment & Analytics Portal",
    page_icon="🧬",
    layout="wide"
)

# Hide Streamlit UI elements (Header, Footer, Toolbar, Deployment/Manage Buttons)
hide_streamlit_style = """
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    div[data-testid="stDecoration"] {visibility: hidden;}
    div[data-testid="stStatusWidget"] {visibility: hidden;}
    [data-testid="manage-app-button"] {display: none !important;}
    .stDeployButton {display:none !important;}
    </style>
"""
st.markdown(hide_streamlit_style, unsafe_allow_html=True)

# ---------------------------------------------------------
# CONSTANTS & AUTHENTICATION DICTIONARIES
# ---------------------------------------------------------
DB_FILE = "homework_portal_v6.db"

# 🔑 Teacher Password
TEACHER_PIN = "Omar_Biology_2026_Secure"

# 🔑 Student 4-Digit PINs (PIN -> Student Name)
STUDENT_PINS = {
    "1234": "Alia",
    "5678": "Lara"
}

# 🔑 Parent 4-Digit PINs (PIN -> (Parent Name, Linked Student Name))
PARENT_PINS = {
    "1111": ("Nahed", "Alia"),
    "2222": ("Nashwa", "Lara")
}

# 🌟 Motivational & Strategy Quotes
MOTIVATIONAL_QUOTES = [
    "🌟 *'Success is the sum of small efforts, repeated day in and day out.'* — Keep pushing for that A*!",
    "🧬 *'Precision in biological terms turns good answers into top marks.'* Great job submitting!",
    "🎯 *'Remember: Always use net movement when defining diffusion and osmosis!'* Solid revision habit!",
    "🚀 *'Small daily improvements lead to outstanding exam results.'* Submission logged successfully!",
    "🔬 *'Mastering command words (Describe vs Explain) is your secret weapon.'* Keep up the fantastic momentum!"
]

DEFAULT_CAMBRIDGE_INSTRUCTIONS = (
    "Strictly enforce Cambridge Mark Scheme keywords: "
    "1. Diffusion must include 'net movement', 'higher to lower concentration', 'concentration gradient', 'random movement'. "
    "2. Osmosis must include 'net movement of water molecules', 'higher water potential', 'lower water potential', 'partially permeable membrane'. "
    "3. Active transport must include 'against concentration gradient', 'energy from respiration / ATP', 'carrier proteins'. "
    "4. Distinguish chloroplast (organelle/site) from chlorophyll (green pigment absorbing light). "
    "5. Magnification: M = I/A, consistent unit conversion (1 mm = 1000 um), no units for magnification, with 'x' sign."
)

# Navigation View Constants
VIEW_STUDENT = "📤 Student Portal (Submit & View Results)"
VIEW_PARENT = "👨‍👩‍‍👧 Parent Analytics Dashboard"
VIEW_TEACHER = "🔒 Teacher Secure Portal"

# ---------------------------------------------------------
# DATABASE INITIALIZATION
# ---------------------------------------------------------
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # Submissions Table
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
            estimated_score REAL,
            teacher_corrected_bytes BLOB,
            teacher_corrected_name TEXT,
            teacher_corrected_mime TEXT,
            status TEXT,
            submitted_at TEXT,
            is_late INTEGER DEFAULT 0
        )
    ''')
    
    # Deadlines Table
    c.execute('''
        CREATE TABLE IF NOT EXISTS deadlines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            assignment_title TEXT UNIQUE,
            due_date TEXT
        )
    ''')
    
    # Safe migration check for existing schemas
    c.execute("PRAGMA table_info(submissions)")
    columns = [col[1] for col in c.fetchall()]
    if "is_late" not in columns:
        c.execute("ALTER TABLE submissions ADD COLUMN is_late INTEGER DEFAULT 0")
        
    conn.commit()
    conn.close()

init_db()

# ---------------------------------------------------------
# HELPER FUNCTIONS
# ---------------------------------------------------------
def analyze_homework_gemini(student_name, assignment_title, instructions, file_bytes, mime_type, file_name, actual_mark=None, total_mark=None, mark_scheme_bytes=None, mark_scheme_mime=None):
    api_key = st.secrets.get("GEMINI_API_KEY", "").strip().strip('"').strip("'")
    if not api_key:
        raise Exception("GEMINI_API_KEY is missing in Streamlit Secrets!")

    genai.configure(api_key=api_key)
    
    # Low temperature (0.1) forces strict factual compliance with mark schemes
    generation_config = {
        "temperature": 0.1,
        "top_p": 0.95
    }
    model = genai.GenerativeModel("gemini-3.8-flash", generation_config=generation_config)

    calc_pct = round((actual_mark / total_mark) * 100, 1) if (actual_mark is not None and total_mark and total_mark > 0) else 0.0

    prompt_text = f"""You are a Senior Cambridge IGCSE Biology (0610 / 0970) Chief Examiner.
Candidate Name: {student_name}
Assignment/Quiz Title: {assignment_title}
General Marking Guidelines: {instructions}

CRITICAL SCORE INSTRUCTIONS:
The teacher has marked this submission manually. The candidate scored EXACTLY {actual_mark} out of {total_mark} ({calc_pct}%).
You MUST use this exact mark ({actual_mark}/{total_mark} - {calc_pct}%) as absolute truth. Do NOT recalculate or invent a different total score.

EVALUATION TASK:
1. Examine the attached Student Submission PDF/Image (or Google Drive link text).
2. If an Official Cambridge Mark Scheme PDF/Image is provided, compare the student's exact written answers line-by-line against that Mark Scheme.
3. Identify precisely where the candidate earned marks and where marks were lost (missing keywords, incorrect terminology, incomplete explanations).
4. Provide a structured Markdown report.

Start line 1 with: [SCORE: {calc_pct}%]

Structure:
1. **Executive Summary & Grade Equivalent** (Reflect score: {actual_mark}/{total_mark} - {calc_pct}%)
2. **Detailed Question-by-Question Breakdown & Mark Scheme Alignment**
3. **Specific Biological Misconceptions & Missing Mark Points**
4. **Actionable Revision Plan for Next Session**
"""

    contents = [prompt_text]

    # Attach Official Mark Scheme file if uploaded by teacher
    if mark_scheme_bytes:
        ms_mime = mark_scheme_mime if mark_scheme_mime else "application/pdf"
        contents.append("OFFICIAL CAMBRIDGE MARK SCHEME ATTACHMENT:")
        contents.append({"mime_type": ms_mime, "data": mark_scheme_bytes})

    # Attach Student Submission
    contents.append("STUDENT SUBMISSION ATTACHMENT:")
    if mime_type == "text/url":
        url_text = file_bytes.decode("utf-8") if isinstance(file_bytes, bytes) else str(file_bytes)
        contents.append(f"Student Shared Google Drive Link: {url_text}")
    elif mime_type and "image" in mime_type:
        contents.append({"mime_type": mime_type, "data": file_bytes})
    else:
        contents.append({"mime_type": "application/pdf", "data": file_bytes})

    response = model.generate_content(contents)
    return response.text

def extract_score_from_text(report_text):
    import re
    match = re.search(r'\[SCORE:\s*([\d\.]+)%?\]', report_text)
    if match:
        try:
            return float(match.group(1))
        except:
            return 75.0
    return 75.0

def get_missing_assignments(student_name):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT assignment_title, due_date FROM deadlines")
    all_deadlines = c.fetchall()
    
    c.execute("SELECT LOWER(assignment_title) FROM submissions WHERE LOWER(student_name) = LOWER(?)", (student_name,))
    submitted_titles = set(row[0] for row in c.fetchall())
    conn.close()
    
    missing = []
    now_dt = datetime.datetime.now()
    
    for d_title, d_date_str in all_deadlines:
        if d_title.lower().strip() not in submitted_titles:
            try:
                due_dt = datetime.datetime.strptime(d_date_str, "%Y-%m-%d %H:%M:%S")
                if now_dt > due_dt:
                    missing.append((d_title, d_date_str))
            except:
                pass
    return missing

# ---------------------------------------------------------
# MAIN APP HEADER & ROUTING
# ---------------------------------------------------------
st.title("🧬 IGCSE Biology Assessment & Analytics Portal")

portal_tab = st.selectbox(
    "Select Portal View:",
    [VIEW_STUDENT, VIEW_PARENT, VIEW_TEACHER]
)

# ---------------------------------------------------------
# 1. STUDENT PORTAL VIEW
# ---------------------------------------------------------
if portal_tab == VIEW_STUDENT:
    st.header("Student Portal")
    s_tab1, s_tab2 = st.tabs(["📤 Submit Homework", "📊 My Results & Manage Submissions"])
    
    # --- TAB 1: SUBMIT ASSIGNMENT ---
    with s_tab1:
        st.subheader("Upload New Assignment")
        student_pin_sub = st.text_input("Enter Your 4-Digit Student PIN", type="password", max_chars=4, key="st_sub_pin")
        
        if student_pin_sub:
            matched_student = STUDENT_PINS.get(student_pin_sub)
            if matched_student:
                st.success(f"🔓 Authenticated as: **{matched_student}**")
                
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                c.execute("SELECT assignment_title, due_date FROM deadlines ORDER BY id DESC")
                deadline_records = c.fetchall()
                conn.close()
                
                assignment_title = st.text_input("Assignment Title", placeholder="e.g., Ch 3 Osmosis HW")
                
                if deadline_records:
                    st.info("📅 **Active Homework Deadlines:**")
                    for d_title, d_date in deadline_records:
                        st.caption(f"• **{d_title}**: Due by **{d_date}**")
                
                submit_mode = st.radio(
                    "Select How You Want to Submit:",
                    ["📁 Direct File Upload (Downloaded PDF/Image)", "🔗 Google Drive Shared Link"],
                    horizontal=True
                )
                
                uploaded_file = None
                drive_link = ""
                
                if submit_mode == "📁 Direct File Upload (Downloaded PDF/Image)":
                    st.caption("💡 **Tip:** If using Google Drive on mobile, download the file to your phone first before uploading here.")
                    uploaded_file = st.file_uploader(
                        "Upload Homework File (PDF, PNG, JPG)", 
                        type=["pdf", "png", "jpg", "jpeg"],
                        key="mobile_hw_uploader"
                    )
                else:
                    drive_link = st.text_input(
                        "Paste Google Drive Shared Link:", 
                        placeholder="https://drive.google.com/file/d/..."
                    )
                    st.caption("⚠️ Ensure link sharing is set to **'Anyone with the link can view'**.")
                
                if st.button("🚀 Submit Homework", type="primary"):
                    if not assignment_title.strip():
                        st.error("❌ Please enter an Assignment Title before submitting.")
                    elif submit_mode == "📁 Direct File Upload (Downloaded PDF/Image)" and uploaded_file is None:
                        st.error("❌ Upload failed or incomplete. Please select the file again from local downloads, or switch to 'Google Drive Shared Link' above.")
                    elif submit_mode == "🔗 Google Drive Shared Link" and not drive_link.strip():
                        st.error("❌ Please paste a valid Google Drive link before submitting.")
                    else:
                        file_bytes = None
                        file_name = ""
                        mime_type = ""
                        
                        if submit_mode == "📁 Direct File Upload (Downloaded PDF/Image)":
                            file_bytes = uploaded_file.getvalue()
                            if not file_bytes or len(file_bytes) == 0:
                                st.error("❌ Uploaded file is empty. Please re-select the file.")
                                st.stop()
                            file_name = uploaded_file.name
                            mime_type = uploaded_file.type if uploaded_file.type else "application/pdf"
                        else:
                            file_bytes = drive_link.strip().encode("utf-8")
                            file_name = "Google_Drive_Link.txt"
                            mime_type = "text/url"
                            
                        now_dt = datetime.datetime.now()
                        now_str = now_dt.strftime("%Y-%m-%d %H:%M:%S")
                        
                        is_late = 0
                        conn = sqlite3.connect(DB_FILE)
                        c = conn.cursor()
                        c.execute("SELECT due_date FROM deadlines WHERE LOWER(assignment_title) = LOWER(?)", (assignment_title.strip(),))
                        d_res = c.fetchone()
                        
                        if d_res:
                            try:
                                due_dt = datetime.datetime.strptime(d_res[0], "%Y-%m-%d %H:%M:%S")
                                if now_dt > due_dt:
                                    is_late = 1
                            except:
                                pass
                        
                        c.execute('''
                            INSERT INTO submissions 
                            (student_name, assignment_title, file_name, file_bytes, mime_type, ai_draft, final_report, estimated_score, teacher_corrected_bytes, teacher_corrected_name, teacher_corrected_mime, status, submitted_at, is_late)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (matched_student, assignment_title.strip(), file_name, file_bytes, mime_type, "", "", 0.0, None, "", "", "PENDING", now_str, is_late))
                        conn.commit()
                        conn.close()
                        
                        st.balloons()
                        selected_quote = random.choice(MOTIVATIONAL_QUOTES)
                        
                        if is_late == 1:
                            st.warning(f"⚠️ Homework submitted for **{matched_student}**, but logged as **LATE** (Past set deadline).")
                        else:
                            st.success(f"⚡ Homework submitted instantly for **{matched_student}**!")
                            
                        st.info(f"💡 **Exam Tip & Motivation:**\n\n{selected_quote}")
            else:
                st.error("🔒 Invalid 4-Digit Student PIN!")
        else:
            st.info("🔑 Please enter your 4-digit PIN to upload your homework.")

    # --- TAB 2: RESULTS & UNSUBMIT ---
    with s_tab2:
        st.subheader("🔒 View Performance & Manage Submissions")
        entered_student_pin = st.text_input("Enter Your 4-Digit PIN", type="password", max_chars=4, key="student_pin_view")
        
        if entered_student_pin:
            matched_student = STUDENT_PINS.get(entered_student_pin)
            if matched_student:
                st.success(f"🔓 Welcome back, {matched_student}!")
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                c.execute('''
                    SELECT id, assignment_title, estimated_score, final_report, teacher_corrected_bytes, teacher_corrected_name, teacher_corrected_mime, status, submitted_at, is_late 
                    FROM submissions 
                    WHERE LOWER(student_name) = LOWER(?)
                    ORDER BY id ASC
                ''', (matched_student,))
                results = c.fetchall()
                conn.close()
                
                if results:
                    st.subheader(f"📊 Assessment Reports for {matched_student}")
                    for i, row in enumerate(reversed(results)):
                        sub_id, a_title, score, report, t_bytes, t_name, t_mime, status, sub_time, is_late = row
                        late_badge = " ⚠️ **(SUBMITTED LATE)**" if is_late == 1 else ""
                        
                        if status == 'APPROVED':
                            st.success(f"📚 **{a_title}** — **APPROVED** ({sub_time}){late_badge}")
                            orig_index = len(results) - 1 - i
                            if orig_index > 0:
                                prev_score = results[orig_index - 1][2]
                                diff = score - prev_score
                                if diff > 0:
                                    st.info(f"🔥 **Progress Boost!** Score increased by **+{diff:.1f}%** compared to previous assignment!")
                                elif diff == 0:
                                    st.info(f"🎯 **Consistent Mastery!** Maintained your score of {score:.1f}%.")
                                else:
                                    st.warning(f"📈 Score dropped by **{abs(diff):.1f}%**. Review feedback below!")
                            
                            st.markdown(report)
                            if t_bytes:
                                st.download_button(
                                    label=f"📥 Download Marked File ({t_name})",
                                    data=t_bytes,
                                    file_name=t_name,
                                    mime=t_mime if t_mime else "application/pdf",
                                    key=f"st_dl_{sub_id}_{i}"
                                )
                        else:
                            st.warning(f"⏳ **{a_title}** — **PENDING REVIEW** ({sub_time}){late_badge}")
                            col_u1, col_u2 = st.columns([3, 1])
                            with col_u1:
                                st.caption("Uploaded wrong document by mistake?")
                            with col_u2:
                                if st.button(f"🗑️ Unsubmit File", key=f"unsub_{sub_id}"):
                                    conn = sqlite3.connect(DB_FILE)
                                    c = conn.cursor()
                                    c.execute("DELETE FROM submissions WHERE id = ?", (sub_id,))
                                    conn.commit()
                                    conn.close()
                                    st.warning("⚠️ Submission removed! You can now re-upload.")
                                    st.rerun()
                        st.divider()
                else:
                    st.info(f"ℹ️ No homework records found for {matched_student} yet.")
            else:
                st.error("🔒 Invalid 4-Digit Student PIN!")

# ---------------------------------------------------------
# 2. PARENT ANALYTICS PORTAL VIEW
# ---------------------------------------------------------
elif portal_tab == VIEW_PARENT:
    st.header("👨‍👩‍👧 Parent Analytics Dashboard")
    
    parent_pin_input = st.text_input("Enter Parent 4-Digit PIN", type="password", max_chars=4, key="parent_pin_entry")
    
    if parent_pin_input:
        parent_info = PARENT_PINS.get(parent_pin_input)
        if parent_info:
            parent_name, student_name = parent_info
            st.success(f"🔓 Welcome, {parent_name}! Viewing performance report for: **{student_name}**")
            
            missing_hw = get_missing_assignments(student_name)
            if missing_hw:
                st.error("🚨 **UNSUBMITTED / OVERDUE ASSIGNMENTS DETECTED:**")
                for m_title, m_due in missing_hw:
                    st.write(f"❌ **{m_title}** was due on **{m_due}** and has **NOT** been submitted yet.")
                st.divider()
            
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute('''
                SELECT assignment_title, estimated_score, final_report, submitted_at, is_late 
                FROM submissions 
                WHERE LOWER(student_name) = LOWER(?) AND status = 'APPROVED'
                ORDER BY id ASC
            ''', (student_name,))
            p_results = c.fetchall()
            
            c.execute('''
                SELECT assignment_title, submitted_at 
                FROM submissions 
                WHERE LOWER(student_name) = LOWER(?) AND is_late = 1 
                ORDER BY id DESC
            ''', (student_name,))
            late_notices = c.fetchall()
            conn.close()
            
            if late_notices:
                st.warning(f"⚠️ **COMPLETED LATE:** {student_name} submitted assignments past deadline:")
                for l_title, l_time in late_notices:
                    st.caption(f"• **{l_title}** (Submitted: {l_time})")
                st.divider()
            
            if p_results:
                scores = [row[1] for row in p_results]
                avg_score = sum(scores) / len(scores) if scores else 0
                latest_score = scores[-1]
                
                if latest_score >= 85.0 or (len(scores) > 1 and scores[-1] > scores[-2]):
                    st.snow()
                    st.success(f"🎉 **Achievement Highlight!** {student_name} scored **{latest_score:.1f}%** on her latest assignment!")
                
                st.subheader(f"📈 Performance Tracking for {student_name}")
                chart_data = {row[0]: row[1] for row in p_results}
                st.line_chart(chart_data)
                
                m1, m2, m3 = st.columns(3)
                m1.metric("Average Score 📊", f"{avg_score:.1f}%")
                m2.metric("Latest Score 🎯", f"{latest_score:.1f}%")
                m3.metric("Assignments Completed 📝", len(p_results))
                
                st.divider()
                st.subheader("⚠️ Detailed Evaluation Reports & Key Takeaways")
                for row in reversed(p_results):
                    late_tag = " (⚠️ Completed Late)" if row[4] == 1 else ""
                    with st.expander(f"📌 Assignment: {row[0]} (Score: {row[1]}%){late_tag} - {row[3]}"):
                        st.markdown(row[2])
            else:
                st.info(f"ℹ️ No approved performance reports found yet for {student_name}.")
        else:
            st.error("🔒 Invalid 4-Digit Parent PIN!")
    else:
        st.info("🔑 Welcome! Please enter your assigned 4-digit PIN to access your child's dashboard.")

# ---------------------------------------------------------
# 3. TEACHER SECURE PORTAL VIEW
# ---------------------------------------------------------
elif portal_tab == VIEW_TEACHER:
    st.header("🔒 Teacher Secure Dashboard")
    pin = st.text_input("Enter Teacher Secret Passcode", type="password", key="teacher_passcode_entry")
    
    if pin == TEACHER_PIN:
        st.success("🔓 Authorized Teacher Access Granted")
        
        # --- DEADLINE SETTING CONTROL ---
        with st.expander("📅 **Set Assignment Deadlines**"):
            d_title = st.text_input("Assignment Title for Deadline", placeholder="e.g., Ch 3 Osmosis HW")
            d_date = st.date_input("Due Date")
            d_time = st.time_input("Due Time", value=datetime.time(23, 59))
            
            if st.button("📌 Save Assignment Deadline"):
                full_due_str = f"{d_date.strftime('%Y-%m-%d')} {d_time.strftime('%H:%M:%S')}"
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                c.execute("INSERT OR REPLACE INTO deadlines (assignment_title, due_date) VALUES (?, ?)", (d_title.strip(), full_due_str))
                conn.commit()
                conn.close()
                st.success(f"✅ Deadline set for '{d_title}' at {full_due_str}")
        
        # --- OVERDUE & LATE SUBMISSIONS SUMMARY ---
        with st.expander("🚨 **Missing & Late Submissions Overview**"):
            st.subheader("Student Submission Compliance Breakdown")
            for s_pin, s_name in STUDENT_PINS.items():
                st.markdown(f"### 👤 Student: **{s_name}**")
                
                m_hw = get_missing_assignments(s_name)
                if m_hw:
                    st.error(f"❌ **Didn't Do Homework ({len(m_hw)} Missing):**")
                    for m_t, m_d in m_hw:
                        st.caption(f"• **{m_t}** (Deadline passed on {m_d})")
                else:
                    st.success("✅ No overdue unsubmitted homework!")
                
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                c.execute("SELECT assignment_title, submitted_at FROM submissions WHERE LOWER(student_name) = LOWER(?) AND is_late = 1", (s_name,))
                late_hw = c.fetchall()
                conn.close()
                
                if late_hw:
                    st.warning(f"⚠️ **Completed Late ({len(late_hw)} Submissions):**")
                    for l_t, l_s in late_hw:
                        st.caption(f"• **{l_t}** (Submitted on {l_s})")
                else:
                    st.info("👍 No late submissions recorded.")
                st.divider()

        st.subheader("⚙️ Cambridge Mark Scheme Instructions Control")
        teacher_instructions = st.text_area(
            "Customize AI evaluation focus:",
            value=DEFAULT_CAMBRIDGE_INSTRUCTIONS,
            height=120
        )
        st.divider()
        
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM submissions WHERE status = 'PENDING'")
        pending_count = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM submissions WHERE status = 'APPROVED'")
        approved_count = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM submissions WHERE is_late = 1")
        late_count = c.fetchone()[0]
        conn.close()
        
        m1, m2, m3 = st.columns(3)
        m1.metric("Pending Reviews ⏳", pending_count)
        m2.metric("Approved Reports ✅", approved_count)
        m3.metric("Late Submissions ⚠️", late_count)
        st.divider()
        
        dashboard_mode = st.radio(
            "Select Management Action:", 
            ["⏳ Review Pending Submissions & Generate Follow-up Questions", "✅ Manage Approved Reports"],
            horizontal=True
        )
        st.divider()
        
        if dashboard_mode == "⏳ Review Pending Submissions & Generate Follow-up Questions":
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("SELECT id, student_name, assignment_title, file_name, mime_type, file_bytes, ai_draft, submitted_at, is_late FROM submissions WHERE status = 'PENDING'")
            pending_list = c.fetchall()
            conn.close()
            
            if pending_list:
                options = {f"ID #{row[0]} | Student: {row[1]} - {row[2]} ({'⚠️ LATE' if row[8]==1 else 'ON TIME'})": row for row in pending_list}
                selected_option = st.selectbox("Select Submission:", list(options.keys()))
                
                selected_row = options[selected_option]
                sub_id, s_name, a_title, f_name, m_type, f_bytes, ai_draft, sub_time, is_late = selected_row
                
                if is_late == 1:
                    st.error(f"🚨 **LATE SUBMISSION NOTIFICATION:** {s_name} submitted this assignment after deadline on {sub_time}.")
                
                col_file, col_edit = st.columns([1, 1])
                
                with col_file:
                    st.subheader(f"📄 Original File ({f_name})")
                    if m_type == "text/url":
                        drive_url = f_bytes.decode("utf-8") if isinstance(f_bytes, bytes) else str(f_bytes)
                        st.info("🔗 **Google Drive Shared Link Submission:**")
                        st.markdown(f"[👉 Click here to open student's Google Drive File]({drive_url})")
                    elif m_type and "image" in m_type:
                        st.image(f_bytes, caption=f"Submitted by {s_name}", use_column_width=True)
                    else:
                        st.download_button("⬇ Download File", data=f_bytes, file_name=f_name, mime=m_type)
                    
                    st.divider()
                    
                    # 📋 Official Mark Scheme Upload (PDF/Image) for 95%+ diagnostic accuracy
                    st.subheader("📋 Official Cambridge Mark Scheme (PDF / Image)")
                    st.caption("Upload the official mark scheme PDF or answer key image for this specific quiz/exam.")
                    ms_file = st.file_uploader("Upload Mark Scheme PDF/Image", type=["pdf", "png", "jpg", "jpeg"], key=f"ms_up_{sub_id}")
                    
                    st.divider()
                    st.subheader("✍️️ Upload Teacher Marked File for Student")
                    corrected_file_upload = st.file_uploader("Upload corrected PDF notes for student", type=["pdf", "png", "jpg"], key=f"up_{sub_id}")
                
                with col_edit:
                    st.subheader("✏️ AI Report Generation & Editing")
                    
                    # Manual Raw Marks Override to guarantee 100% accurate score calculations
                    st.markdown("##### 🎯 Enter Exact Marks Awarded:")
                    c_m1, c_m2 = st.columns(2)
                    with c_m1:
                        teacher_raw_score = st.number_input("Marks Obtained:", min_value=0.0, max_value=200.0, value=47.0, step=1.0, key=f"raw_{sub_id}")
                    with c_m2:
                        teacher_max_score = st.number_input("Total Max Marks:", min_value=1.0, max_value=200.0, value=67.0, step=1.0, key=f"max_{sub_id}")
                    
                    if not ai_draft:
                        if st.button("⚡ Generate AI Draft Report (Gemini 3.8-Flash)", type="secondary"):
                            with st.spinner("Analyzing student submission against Official Mark Scheme..."):
                                try:
                                    ms_bytes = ms_file.getvalue() if ms_file else None
                                    ms_mime = ms_file.type if ms_file else None
                                    
                                    generated_draft = analyze_homework_gemini(
                                        s_name, a_title, teacher_instructions, f_bytes, m_type, f_name,
                                        actual_mark=teacher_raw_score, total_mark=teacher_max_score,
                                        mark_scheme_bytes=ms_bytes, mark_scheme_mime=ms_mime
                                    )
                                    calc_percentage = round((teacher_raw_score / teacher_max_score) * 100, 1) if teacher_max_score > 0 else 0.0
                                    
                                    conn = sqlite3.connect(DB_FILE)
                                    c = conn.cursor()
                                    c.execute("UPDATE submissions SET ai_draft = ?, estimated_score = ? WHERE id = ?", (generated_draft, calc_percentage, sub_id))
                                    conn.commit()
                                    conn.close()
                                    st.success("✅ Draft generated with accurate marks & mark scheme alignment!")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"⚠ Error generating draft: {e}")
                    
                    final_report_input = st.text_area(
                        "Refine Report:", 
                        value=ai_draft if ai_draft else "Click 'Generate AI Draft Report' above to auto-generate...", 
                        height=400
                    )
                    
                    if st.button("💡 Generate AI Follow-up Questions for Next Session"):
                        if not final_report_input or final_report_input.startswith("Click 'Generate"):
                            st.warning("Please generate or enter a report draft first.")
                        else:
                            with st.spinner("Generating targeted Past Paper questions..."):
                                fu_model = genai.GenerativeModel("gemini-3.8-flash")
                                fu_prompt = f"Based on this student's evaluation report, generate 3 challenging Cambridge IGCSE Biology Past Paper style follow-up questions to test the student on their weak spots during the next tutoring session:\n{final_report_input}"
                                fu_res = fu_model.generate_content(fu_prompt)
                                st.info("### 💡 Suggested Follow-up Questions for Next Lesson:")
                                st.markdown(fu_res.text)
                    
                    if st.button("✅ Approve & Publish", type="primary"):
                        corr_bytes = corrected_file_upload.read() if corrected_file_upload else None
                        corr_name = corrected_file_upload.name if corrected_file_upload else ""
                        corr_mime = corrected_file_upload.type if corrected_file_upload else ""
                        score_val = extract_score_from_text(final_report_input)
                        
                        conn = sqlite3.connect(DB_FILE)
                        c = conn.cursor()
                        c.execute('''
                            UPDATE submissions 
                            SET final_report = ?, estimated_score = ?, teacher_corrected_bytes = ?, teacher_corrected_name = ?, teacher_corrected_mime = ?, status = 'APPROVED' 
                            WHERE id = ?
                        ''', (final_report_input, score_val, corr_bytes, corr_name, corr_mime, sub_id))
                        conn.commit()
                        conn.close()
                        st.balloons()
                        st.success("🎉 Published successfully!")
                        st.rerun()
            else:
                st.info("🎉 No pending submissions.")
        else:
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("SELECT id, student_name, assignment_title, final_report, submitted_at FROM submissions WHERE status = 'APPROVED'")
            approved_list = c.fetchall()
            conn.close()
            
            if approved_list:
                approved_options = {f"ID #{row[0]} | Student: {row[1]} - {row[2]}": row for row in approved_list}
                selected_app_option = st.selectbox("Select Approved:", list(approved_options.keys()))
                app_row = approved_options[selected_app_option]
                st.markdown(app_row[3])
                
                col_act1, col_act2 = st.columns(2)
                with col_act1:
                    if st.button("↩️ Disapprove & Return to Pending"):
                        conn = sqlite3.connect(DB_FILE)
                        c = conn.cursor()
                        c.execute("UPDATE submissions SET status = 'PENDING' WHERE id = ?", (app_row[0],))
                        conn.commit()
                        conn.close()
                        st.info("🔄 Submission reverted back to 'PENDING' status for review.")
                        st.rerun()
                        
                with col_act2:
                    if st.button("🗑️ Delete Permanently"):
                        conn = sqlite3.connect(DB_FILE)
                        c = conn.cursor()
                        c.execute("DELETE FROM submissions WHERE id = ?", (app_row[0],))
                        conn.commit()
                        conn.close()
                        st.warning("Deleted!")
                        st.rerun()
            else:
                st.info("No approved reports.")
                
    elif pin != "":
        st.error("🔒 Incorrect Teacher Passcode!")
    else:
        st.info("🔒 Enter teacher secret passcode.")
       
 
             
