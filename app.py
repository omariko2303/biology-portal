import streamlit as st
import sqlite3
import datetime
import io
import google.generativeai as genai

# ==================== PAGE CONFIG & SETUP ====================
st.set_page_config(
    page_title="IGCSE Biology Assessment Portal",
    page_icon="🧬",
    layout="wide"
)

DB_FILE = "homework_portal_v4.db"

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
            teacher_corrected_bytes BLOB,
            teacher_corrected_name TEXT,
            teacher_corrected_mime TEXT,
            status TEXT,
            submitted_at TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# المعايير الافتراضية لكامبريدج
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

Carefully inspect the handwritten answers or diagrams in the attached document. Provide a comprehensive, rigorous Cambridge-style diagnostic evaluation report in Markdown format:
1. **Executive Summary & Estimated Raw Score / Grade Equivalent** (Provide a realistic estimated score out of total marks).
2. **Detailed Question-by-Question Breakdown & Mark Scheme Alignment** (Analyze exact correct keywords used vs. missing ones).
3. **Specific Misconceptions & Errors** (Correct biological inaccuracies).
4. **Actionable Next Steps for Improvement** (Precise guidance for an A*).
"""

    if mime_type and "image" in mime_type:
        file_part = {"mime_type": mime_type, "data": file_bytes}
    else:
        file_part = {"mime_type": "application/pdf", "data": file_bytes}

    response = model.generate_content([prompt_text, file_part])
    return response.text

# ==================== MAIN UI ====================
st.title("🧬 IGCSE Biology Assessment Portal")

tab1, tab2, tab3 = st.tabs([
    "📤 Student Portal (Submit Homework)", 
    "📊 Student Results & Status Lookup", 
    "🔒 Teacher Secure Portal"
])

# -------------------- TAB 1: STUDENT SUBMIT --------------------
with tab1:
    st.header("Upload Homework (PDF, JPG, or PNG)")
    
    col1, col2 = st.columns(2)
    with col1:
        student_name = st.text_input("Student Name", placeholder="e.g., Lara")
    with col2:
        assignment_title = st.text_input("Assignment Title", placeholder="e.g., hw")
        
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
                    ai_draft = analyze_homework_gemini(
                        student_name, assignment_title, DEFAULT_CAMBRIDGE_INSTRUCTIONS, file_bytes, mime_type, file_name
                    )
                    
                    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    c.execute('''
                        INSERT INTO submissions 
                        (student_name, assignment_title, file_name, file_bytes, mime_type, ai_draft, final_report, teacher_corrected_bytes, teacher_corrected_name, teacher_corrected_mime, status, submitted_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', ?)
                    ''', (student_name, assignment_title, file_name, file_bytes, mime_type, ai_draft, "", None, "", "", now))
                    conn.commit()
                    conn.close()
                    
                    st.success(f"✅ Submission successful, {student_name}! Your homework has been sent to your teacher for review.")
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
                SELECT assignment_title, file_name, final_report, teacher_corrected_bytes, teacher_corrected_name, teacher_corrected_mime, status, submitted_at 
                FROM submissions 
                WHERE LOWER(student_name) = LOWER(?)
                ORDER BY id DESC
            ''', (search_name.strip(),))
            results = c.fetchall()
            conn.close()
            
            if results:
                for row in results:
                    a_title, f_name, report, t_bytes, t_name, t_mime, status, sub_time = row
                    
                    if status == 'APPROVED':
                        st.success(f"📚 **{a_title}** — Status: **APPROVED** (Submitted: {sub_time})")
                        
                        # عرض تقرير المعلم/الذكاء الاصطناعي النهائي
                        st.markdown("### 📝 Evaluation Report")
                        st.markdown(report)
                        
                        # إذا قام المعلم برفع ملف مصحح، يظهر للطالب لتحميله أو مشاهدته
                        if t_bytes:
                            st.info(f"✍️ Your teacher has uploaded a corrected/marked copy of your assignment: **{t_name}**")
                            st.download_button(
                                label=f"📥 Download Teacher's Marked File ({t_name})",
                                data=t_bytes,
                                file_name=t_name,
                                mime=t_mime if t_mime else "application/pdf",
                                key=f"download_{a_title}_{sub_time}"
                            )
                        
                        st.download_button(
                            label="📥 Download Full Report as Text",
                            data=report,
                            file_name=f"{a_title}_Report.txt",
                            mime="text/plain",
                            key=f"txt_{a_title}_{sub_time}"
                        )
                    else:
                        st.warning(f"⏳ **{a_title}** — Status: **PENDING REVIEW** (Submitted: {sub_time}). Your teacher is currently reviewing your assignment and checking your work.")
                    st.divider()
            else:
                st.info("ℹ️ No submissions found for this name.")

# -------------------- TAB 3: TEACHER SECURE PORTAL --------------------
with tab3:
    st.header("Teacher Secure Dashboard")
    
    pin = st.text_input("Enter Teacher Secret Passcode", type="password")
    TEACHER_PIN = "Omar_Biology_2026_Secure"
    
    if pin == TEACHER_PIN:
        st.success("🔓 Authorized Teacher Access Granted")
        
        st.subheader("⚙️ Cambridge Mark Scheme Instructions (Teacher Control)")
        teacher_instructions = st.text_area(
            "Customize AI evaluation focus and guidelines for incoming assignments:",
            value=DEFAULT_CAMBRIDGE_INSTRUCTIONS,
            height=160
        )
        st.divider()
        
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
        
        dashboard_mode = st.radio(
            "Select Dashboard Management Mode:", 
            ["⏳ Review Pending Submissions", "✅ Manage Approved Reports"],
            horizontal=True
        )
        
        st.divider()
        
        if dashboard_mode == "⏳ Review Pending Submissions":
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
                
                col_file, col_edit = st.columns([1, 1])
                
                with col_file:
                    st.subheader(f"📄 Student Original File ({f_name})")
                    if m_type and "image" in m_type:
                        st.image(f_bytes, caption=f"Submitted by {s_name}", use_column_width=True)
                    else:
                        st.download_button(
                            label=f"⬇ Download Original Student File",
                            data=f_bytes,
                            file_name=f_name,
                            mime=m_type if m_type else "application/pdf"
                        )
                    
                    st.divider()
                    st.subheader("✍️ Upload Teacher's Marked File (Optional)")
                    corrected_file_upload = st.file_uploader(
                        "Upload PDF/Image with your manual notes & corrections", 
                        type=["pdf", "png", "jpg", "jpeg"],
                        key=f"uploader_{sub_id}"
                    )
                
                with col_edit:
                    st.subheader("✏️ Edit AI Draft & Finalize Report")
                    final_report_input = st.text_area("Review and refine the diagnostic report before release:", value=ai_draft, height=450)
                    
                    col_btn1, col_btn2 = st.columns(2)
                    with col_btn1:
                        if st.button("✅ Approve & Publish Report to Student", type="primary"):
                            corr_bytes = corrected_file_upload.read() if corrected_file_upload else None
                            corr_name = corrected_file_upload.name if corrected_file_upload else ""
                            corr_mime = corrected_file_upload.type if corrected_file_upload else ""
                            
                            conn = sqlite3.connect(DB_FILE)
                            c = conn.cursor()
                            c.execute('''
                                UPDATE submissions 
                                SET final_report = ?, teacher_corrected_bytes = ?, teacher_corrected_name = ?, teacher_corrected_mime = ?, status = 'APPROVED' 
                                WHERE id = ?
                            ''', (final_report_input, corr_bytes, corr_name, corr_mime, sub_id))
                            conn.commit()
                            conn.close()
                            st.balloons()
                            st.success("🎉 Report and marked file approved and published to the student portal!")
                            st.rerun()
                    
                    with col_btn2:
                        if st.button("🗑️️ Delete Submission", type="secondary"):
                            conn = sqlite3.connect(DB_FILE)
                            c = conn.cursor()
                            c.execute("DELETE FROM submissions WHERE id = ?", (sub_id,))
                            conn.commit()
                            conn.close()
                            st.warning("⚠️ Submission deleted successfully!")
                            st.rerun()
            else:
                st.info("🎉 All caught up! No pending submissions.")
                
        else:
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("SELECT id, student_name, assignment_title, file_name, final_report, teacher_corrected_name, submitted_at FROM submissions WHERE status = 'APPROVED'")
            approved_list = c.fetchall()
            conn.close()
            
            if approved_list:
                approved_options = {f"ID #{row[0]} | Student: {row[1]} - {row[2]} ({row[6]})": row for row in approved_list}
                selected_app_option = st.selectbox("Select Approved Report to Manage:", list(approved_options.keys()))
                
                app_row = approved_options[selected_app_option]
                app_id, app_s_name, app_a_title, app_f_name, app_report, app_corr_name, app_time = app_row
                
                st.subheader(f"📖 Approved Report for {app_s_name} ({app_a_title})")
                st.markdown(app_report)
                if app_corr_name:
                    st.info(f"✍️ Attached Teacher Marked File: {app_corr_name}")
                
                st.divider()
                if st.button("🗑️ Delete This Approved Report Permanently", type="primary"):
                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    c.execute("DELETE FROM submissions WHERE id = ?", (app_id,))
                    conn.commit()
                    conn.close()
                    st.warning("⚠️ Approved report deleted successfully!")
                    st.rerun()
            else:
                st.info("ℹ️ No approved reports found.")
                
    elif pin != "":
        st.error("🔒 Incorrect Passcode! Access Denied.")
    else:
        st.info("🔒 Please enter the secure teacher passcode to access evaluation controls.")
       
 
             
