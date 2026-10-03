import streamlit as st
import sqlite3
import datetime
import io
import random
import google.generativeai as genai

st.set_page_config(
    page_title="IGCSE Biology Assessment & Analytics Portal",
    page_icon="🧬",
    layout="wide"
)

# 🙈 HIDE STREAMLIT FOOTER, TOOLBAR & "MANAGE APP" BUTTON
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

# Updated DB filename to prevent schema conflicts with previous versions
DB_FILE = "homework_portal_v6.db"

# 🔑 Teacher Security Passcode
TEACHER_PIN = "Omar_Biology_2026_Secure"

# 🔑 4-Digit Student PIN Mapping (PIN -> Student Name)
STUDENT_PINS = {
    "1234": "Alia",
    "5678": "Lara"
}

# 🔑 4-Digit Parent PIN Mapping (PIN -> (Parent Name, Linked Student Name))
PARENT_PINS = {
    "1111": ("Nahed", "Alia"),
    "2222": ("Nashwa", "Lara")
}

# 🌟 Motivational & Cambridge Strategy Quote Library
MOTIVATIONAL_QUOTES = [
    "🌟 *'Success is the sum of small efforts, repeated day in and day out.'* — Keep pushing for that A*!",
    "🧬 *'Precision in biological terms turns good answers into top marks.'* Great job submitting!",
    "🎯 *'Remember: Always use net movement when defining diffusion and osmosis!'* Solid revision habit!",
    "🚀 *'Small daily improvements lead to outstanding exam results.'* Submission logged successfully!",
    "🔬 *'Mastering command words (Describe vs Explain) is your secret weapon.'* Keep up the fantastic momentum!"
]

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    # Table for Submissions
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
    # Table for Deadlines
    c.execute('''
        CREATE TABLE IF NOT EXISTS deadlines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            assignment_title TEXT UNIQUE,
            due_date TEXT
        )
    ''')
    
    # Safe migration check for existing tables missing 'is_late'
    c.execute("PRAGMA table_info(submissions)")
    columns = [col[1] for col in c.fetchall()]
    if "is_late" not in columns:
        c.execute("ALTER TABLE submissions ADD COLUMN is_late INTEGER DEFAULT 0")
        
    conn.commit()
    conn.close()

init_db()

DEFAULT_CAMBRIDGE_INSTRUCTIONS = (
    "Strictly enforce Cambridge Mark Scheme keywords: "
    "1. Diffusion must include 'net movement', 'higher to lower concentration', 'concentration gradient', 'random movement'. "
    "2. Osmosis must include 'net movement of water molecules', 'higher water potential', 'lower water potential', 'partially permeable membrane'. "
    "3. Active transport must include 'against concentration gradient', 'energy from respiration / ATP', 'carrier proteins'. "
    "4. Distinguish chloroplast (organelle/site) from chlorophyll (green pigment absorbing light). "
    "5. Magnification: M = I/A, consistent unit conversion (1 mm = 1000 um), no units for magnification, with 'x' sign."
)

def analyze_homework_gemini(student_name, assignment_title, instructions, file_bytes, mime_type, file_name):
    api_key = st.secrets.get("GEMINI_API_KEY", "").strip().strip('"').strip("'")
    
    if not api_key:
        raise Exception("GEMINI_API_KEY is missing in Streamlit Secrets!")

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-3.8-flash")

    prompt_text = f"""You are a Senior Cambridge IGCSE Biology (0610 / 0970) Chief Examiner.
You are evaluating a student's actual homework submission attached as an image or PDF.
Candidate Name: {student_name}
Assignment: {assignment_title}
Instructions & Mark Scheme Standard: {instructions}

Provide a comprehensive, rigorous Cambridge-style diagnostic evaluation report in Markdown format, and on the very first line provide an estimated numeric percentage score or raw mark out of total (e.g., [SCORE: 85%]). Structure:
1. **[SCORE: XX%] Executive Summary & Grade Equivalent**
2. **Detailed Question-by-Question Breakdown & Mark Scheme Alignment**
3. **Specific Biological Misconceptions & Errors Identified**
4. **Actionable Next Steps for Improvement**
"""

    if mime_type and "image" in mime_type:
        file_part = {"mime_type": mime_type, "data": file_bytes}
    else:
        file_part = {"mime_type": "application/pdf", "data": file_bytes}

    response = model.generate_content([prompt_text, file_part])
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

st.title("🧬 IGCSE Biology Assessment & Analytics Portal")

portal_tab = st.selectbox(
    "Select Portal View:",
    [
        "📤 Student Portal (Submit & View Results)", 
        "👨‍👩‍👧 Parent Analytics Dashboard", 
        "🔒 Teacher Secure Portal"
    ]
)

# -------------------- 1. STUDENT PORTAL --------------------
if portal_tab == "📤 Student Portal (Submit & View Results)":
    st.header("Student Portal")
    
    s_tab1, s_tab2 = st.tabs(["📤 Submit Homework", "📊 My Results & Manage Submissions"])
    
    # --- SUBMIT HOMEWORK TAB ---
    with s_tab1:
        st.subheader("Upload New Assignment")
        
        student_pin_sub = st.text_input("Enter Your 4-Digit Student PIN", type="password", max_chars=4, key="st_sub_pin")
        
        if student_pin_sub:
            matched_student = STUDENT_PINS.get(student_pin_sub)
            
            if matched_student:
                st.success(f"🔓 Authenticated as: **{matched_student}**")
                
                # Fetch deadlines
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
                
                uploaded_file = st.file_uploader(
                    "Upload Homework File (PDF, PNG, JPG)", 
                    type=["pdf", "png", "jpg", "jpeg"]
                )
                
                if st.button("🚀 Submit Homework", type="primary"):
                    if not assignment_title or not uploaded_file:
                        st.error("❌ Please provide an assignment title and upload a file.")
                    else:
                        file_bytes = uploaded_file.read()
                        file_name = uploaded_file.name
                        mime_type = uploaded_file.type if uploaded_file.type else "application/pdf"
                        now_dt = datetime.datetime.now()
                        now_str = now_dt.strftime("%Y-%m-%d %H:%M:%S")
                        
                        # Check late status against active deadline
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
                            st.success(f"⚡ Homework submitted instantly for **{matched_student}**! Your teacher will review and grade it soon.")
                            
                        st.info(f"💡 **Exam Tip & Motivation:**\n\n{selected_quote}")
            else:
                st.error("🔒 Invalid 4-Digit PIN! Please check your code.")
        else:
            st.info("🔑 Please enter your 4-digit PIN to upload your homework.")

    # --- VIEW RESULTS & UNSUBMIT TAB ---
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
                                    st.info(f"🎯 **Consistent Mastery!** Maintained your solid score of {score:.1f}%.")
                                else:
                                    st.warning(f"📈 Score dropped by **{abs(diff):.1f}%**. Check feedback below to target your weak spots!")
                            
                            st.markdown(report)
                            if t_bytes:
                                st.download_button(
                                    label=f"📥 Download Teacher's Marked File ({t_name})",
                                    data=t_bytes,
                                    file_name=t_name,
                                    mime=t_mime if t_mime else "application/pdf",
                                    key=f"st_dl_{sub_id}_{i}"
                                )
                        else:
                            st.warning(f"⏳ **{a_title}** — **PENDING REVIEW** by your teacher ({sub_time}){late_badge}")
                            
                            # 🔄 UNSUBMIT WRONG DOCUMENT OPTION
                            col_unsub1, col_unsub2 = st.columns([3, 1])
                            with col_unsub1:
                                st.caption("Uploaded the wrong document by mistake?")
                            with col_unsub2:
                                if st.button(f"🗑️ Unsubmit File", key=f"unsub_{sub_id}"):
                                    conn = sqlite3.connect(DB_FILE)
                                    c = conn.cursor()
                                    c.execute("DELETE FROM submissions WHERE id = ?", (sub_id,))
                                    conn.commit()
                                    conn.close()
                                    st.warning("⚠️ Homework submission unsubmitted/removed! You can now re-upload the correct document.")
                                    st.rerun()
                        st.divider()
                else:
                    st.info(f"ℹ️️ No homework records found for {matched_student} yet.")
            else:
                st.error("🔒 Invalid 4-Digit Student PIN!")

# -------------------- 2. PARENT ANALYTICS PORTAL --------------------
elif portal_tab == "👨‍👩‍👧 Parent Analytics Dashboard":
    st.header("👨‍👩‍👧 Parent Analytics & Performance Portal")
    st.info("Welcome! Please enter your 4-digit access PIN to view your daughter's performance and analytics.")
    
    parent_pin_input = st.text_input("Enter Parent 4-Digit PIN", type="password", max_chars=4)
    
    if parent_pin_input:
        parent_info = PARENT_PINS.get(parent_pin_input)
        
        if parent_info:
            parent_name, student_name = parent_info
            st.success(f"🔓 Welcome, {parent_name}! Viewing performance report for: **{student_name}**")
            
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute('''
                SELECT assignment_title, estimated_score, final_report, submitted_at, is_late 
                FROM submissions 
                WHERE LOWER(student_name) = LOWER(?) AND status = 'APPROVED'
                ORDER BY id ASC
            ''', (student_name,))
            p_results = c.fetchall()
            
            # Check for recent late submissions
            c.execute('''
                SELECT assignment_title, submitted_at 
                FROM submissions 
                WHERE LOWER(student_name) = LOWER(?) AND is_late = 1 
                ORDER BY id DESC LIMIT 1
            ''', (student_name,))
            late_notice = c.fetchone()
            conn.close()
            
            # 🔔 LATE SUBMISSION PARENT NOTIFICATION BANNER
            if late_notice:
                st.error(f"🔔 **Notification:** {student_name} submitted **{late_notice[0]}** after the set deadline ({late_notice[1]}).")
            
            if p_results:
                scores = [row[1] for row in p_results]
                avg_score = sum(scores) / len(scores) if scores else 0
                latest_score = scores[-1]
                
                if latest_score >= 85.0 or (len(scores) > 1 and scores[-1] > scores[-2]):
                    st.snow()
                    st.success(f"🎉 **Outstanding Achievement Highlight!** {student_name} scored **{latest_score:.1f}%** on her latest assignment! Great progress!")
                
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
                    late_tag = " (⚠️ Submitted Late)" if row[4] == 1 else ""
                    with st.expander(f"📌 Assignment: {row[0]} (Score: {row[1]}%){late_tag} - {row[3]}"):
                        st.markdown(row[2])
            else:
                st.info(f"ℹ️ No approved performance reports found yet for {student_name}.")
        else:
            st.error("🔒 Invalid 4-Digit Parent PIN!")

# -------------------- 3. TEACHER SECURE PORTAL --------------------
else:
    st.header("🔒 Teacher Secure Dashboard")
    pin = st.text_input("Enter Teacher Secret Passcode", type="password")
    
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
        
        st.subheader("⚙️ Cambridge Mark Scheme Instructions Control")
        teacher_instructions = st.text_area(
            "Customize AI evaluation focus:",
            value=DEFAULT_CAMBRIDGE_INSTRUCTIONS,
            height=140
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
                    st.error(f"🚨 **LATE SUBMISSION NOTIFICATION:** {s_name} submitted this assignment after the deadline on {sub_time}.")
                
                col_file, col_edit = st.columns([1, 1])
                
                with col_file:
                    st.subheader(f"📄 Original File ({f_name})")
                    if m_type and "image" in m_type:
                        st.image(f_bytes, caption=f"Submitted by {s_name}", use_column_width=True)
                    else:
                        st.download_button("⬇ Download File", data=f_bytes, file_name=f_name, mime=m_type)
                    
                    st.divider()
                    st.subheader("✍️ Upload Teacher Marked File")
                    corrected_file_upload = st.file_uploader("Upload corrected notes", type=["pdf", "png", "jpg"], key=f"up_{sub_id}")
                
                with col_edit:
                    st.subheader("✏️ AI Report Generation & Editing")
                    
                    if not ai_draft:
                        if st.button("⚡ Generate AI Draft Report (Gemini 3.8-Flash)", type="secondary"):
                            with st.spinner("Analyzing submission with Gemini 3.8-Flash..."):
                                try:
                                    generated_draft = analyze_homework_gemini(
                                        s_name, a_title, teacher_instructions, f_bytes, m_type, f_name
                                    )
                                    score_val = extract_score_from_text(generated_draft)
                                    
                                    conn = sqlite3.connect(DB_FILE)
                                    c = conn.cursor()
                                    c.execute("UPDATE submissions SET ai_draft = ?, estimated_score = ? WHERE id = ?", (generated_draft, score_val, sub_id))
                                    conn.commit()
                                    conn.close()
                                    st.success("✅ Draft generated successfully!")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"⚠️ Error generating draft: {e}")
                    
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
        st.error("🔒 Incorrect Passcode!")
    else:
        st.info("🔒 Enter teacher passcode.")
       
 
             
