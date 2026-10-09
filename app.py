import streamlit as st
import datetime
import random
import base64
import uuid
import requests
import google.generativeai as genai
from supabase import create_client

# ---------------------------------------------------------
# PAGE CONFIGURATION & CUSTOM STYLES
# ---------------------------------------------------------
st.set_page_config(
    page_title="IGCSE Biology Assessment & Analytics Portal",
    page_icon="🧬",
    layout="wide"
)

# Hide Streamlit UI elements
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
# SUPABASE INITIALIZATION
# ---------------------------------------------------------
SUPABASE_URL = st.secrets.get("SUPABASE_URL", "")
SUPABASE_KEY = st.secrets.get("SUPABASE_KEY", "")

if not SUPABASE_URL or not SUPABASE_KEY:
    st.error("❌ Supabase URL or Key is missing in Streamlit Secrets! Please add them.")
    st.stop()

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ---------------------------------------------------------
# CONSTANTS & AUTHENTICATION DICTIONARIES
# ---------------------------------------------------------
TEACHER_PIN = "Omar_Biology_2026_Secure"

STUDENT_PINS = {
    "1234": "Alia",
    "5678": "Lara"
}

PARENT_PINS = {
    "1111": ("Nahed", "Alia"),
    "2222": ("Nashwa", "Lara")
}

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

VIEW_STUDENT = "📤 Student Portal (Submit & View Results)"
VIEW_PARENT = "👨‍👩‍👧 Parent Analytics Dashboard"
VIEW_TEACHER = "🔒 Teacher Secure Portal"

# ---------------------------------------------------------
# HELPER FUNCTIONS
# ---------------------------------------------------------
def analyze_homework_gemini(student_name, assignment_title, instructions, file_bytes, mime_type, file_name, actual_mark=None, total_mark=None, mark_scheme_bytes=None, mark_scheme_mime=None):
    api_key = st.secrets.get("GEMINI_API_KEY", "").strip().strip('"').strip("'")
    if not api_key:
        raise Exception("GEMINI_API_KEY is missing in Streamlit Secrets!")

    genai.configure(api_key=api_key)
    
    generation_config = {
        "temperature": 0.1,
        "top_p": 0.95
    }
    model = genai.GenerativeModel("gemini-1.5-flash", generation_config=generation_config)

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

    if mark_scheme_bytes:
        ms_mime = mark_scheme_mime if mark_scheme_mime else "application/pdf"
        contents.append("OFFICIAL CAMBRIDGE MARK SCHEME ATTACHMENT:")
        contents.append({"mime_type": ms_mime, "data": mark_scheme_bytes})

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

def get_missing_assignments(student_name):
    try:
        deadlines_res = supabase.table("deadlines").select("*").execute()
        all_deadlines = [(row["assignment_title"], row["due_date"]) for row in deadlines_res.data]
        
        subs_res = supabase.table("submissions").select("assignment_title").ilike("student_name", student_name).execute()
        submitted_titles = set(row["assignment_title"].lower().strip() for row in subs_res.data)
    except Exception as e:
        return []

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
    
    with s_tab1:
        st.subheader("Upload New Assignment")
        student_pin_sub = st.text_input("Enter Your 4-Digit Student PIN", type="password", max_chars=4, key="st_sub_pin")
        
        if student_pin_sub:
            matched_student = STUDENT_PINS.get(student_pin_sub)
            if matched_student:
                st.success(f"🔓 Authenticated as: **{matched_student}**")
                
                try:
                    deadline_records = supabase.table("deadlines").select("*").order("id", desc=True).execute().data
                except:
                    deadline_records = []
                
                assignment_title = st.text_input("Assignment Title", placeholder="e.g., Ch 3 Osmosis HW")
                
                if deadline_records:
                    st.info("📅 **Active Homework Deadlines:**")
                    for d in deadline_records:
                        st.caption(f"• **{d['assignment_title']}**: Due by **{d['due_date']}**")
                
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
                        file_url = ""
                        file_name = ""
                        mime_type = ""
                        
                        # UPLOAD TO SUPABASE STORAGE
                        if submit_mode == "📁 Direct File Upload (Downloaded PDF/Image)":
                            raw_bytes = uploaded_file.getvalue()
                            if not raw_bytes or len(raw_bytes) == 0:
                                st.error("❌ Uploaded file is empty. Please re-select the file.")
                                st.stop()
                            
                            file_name = uploaded_file.name
                            mime_type = uploaded_file.type if uploaded_file.type else "application/pdf"
                            
                            # Create a unique filename
                            file_ext = file_name.split('.')[-1] if '.' in file_name else 'pdf'
                            storage_path = f"{matched_student}/{uuid.uuid4()}.{file_ext}"
                            
                            try:
                                # Upload to Storage (Using 'homework_files' bucket)
                                supabase.storage.from_("homework_files").upload(
                                    path=storage_path,
                                    file=raw_bytes,
                                    file_options={"content-type": mime_type}
                                )
                                # Get the public URL
                                file_url = supabase.storage.from_("homework_files").get_public_url(storage_path)
                            except Exception as e:
                                st.error(f"❌ Storage upload failed: {e}")
                                st.stop()
                        else:
                            file_url = drive_link.strip()
                            file_name = "Google_Drive_Link.txt"
                            mime_type = "text/url"
                            
                        now_dt = datetime.datetime.now()
                        now_str = now_dt.strftime("%Y-%m-%d %H:%M:%S")
                        
                        is_late = 0
                        try:
                            d_res = supabase.table("deadlines").select("*").ilike("assignment_title", assignment_title.strip()).execute().data
                            if d_res:
                                due_dt = datetime.datetime.strptime(d_res[0]["due_date"], "%Y-%m-%d %H:%M:%S")
                                if now_dt > due_dt:
                                    is_late = 1
                        except:
                            pass
                        
                        submission_data = {
                            "student_name": matched_student,
                            "assignment_title": assignment_title.strip(),
                            "file_name": file_name,
                            "file_url": file_url, # STORING URL
                            "mime_type": mime_type,
                            "ai_draft": "",
                            "final_report": "",
                            "estimated_score": 0.0,
                            "teacher_corrected_url": None,
                            "teacher_corrected_name": "",
                            "teacher_corrected_mime": "",
                            "status": "PENDING",
                            "submitted_at": now_str,
                            "is_late": is_late
                        }
                        
                        try:
                            supabase.table("submissions").insert(submission_data).execute()
                            st.balloons()
                            selected_quote = random.choice(MOTIVATIONAL_QUOTES)
                            
                            if is_late == 1:
                                st.warning(f"⚠️ Homework submitted for **{matched_student}**, but logged as **LATE** (Past set deadline).")
                            else:
                                st.success(f"⚡ Homework submitted instantly for **{matched_student}**!")
                                
                            st.info(f"💡 **Exam Tip & Motivation:**\n\n{selected_quote}")
                        except Exception as e:
                            st.error(f"❌ Database error during submission: {e}")
            else:
                st.error("🔒 Invalid 4-Digit Student PIN!")
        else:
            st.info("🔑 Please enter your 4-digit PIN to upload your homework.")

    with s_tab2:
        st.subheader("🔒 View Performance & Manage Submissions")
        entered_student_pin = st.text_input("Enter Your 4-Digit PIN", type="password", max_chars=4, key="student_pin_view")
        
        if entered_student_pin:
            matched_student = STUDENT_PINS.get(entered_student_pin)
            if matched_student:
                st.success(f"🔓 Welcome back, {matched_student}!")
                try:
                    res = supabase.table("submissions").select("*").ilike("student_name", matched_student).order("id", desc=False).execute()
                    results = res.data
                except Exception as e:
                    results = []
                
                if results:
                    st.subheader(f"📊 Assessment Reports for {matched_student}")
                    for i, row in enumerate(reversed(results)):
                        sub_id = row["id"]
                        a_title = row["assignment_title"]
                        score = row["estimated_score"]
                        report = row["final_report"]
                        t_url = row.get("teacher_corrected_url", "")
                        t_name = row.get("teacher_corrected_name", "")
                        t_mime = row.get("teacher_corrected_mime", "")
                        status = row["status"]
                        sub_time = row["submitted_at"]
                        is_late = row["is_late"]
                        
                        late_badge = " ⚠️ **(SUBMITTED LATE)**" if is_late == 1 else ""
                        
                        if status == 'APPROVED':
                            st.success(f"📚 **{a_title}** — **APPROVED** ({sub_time}){late_badge}")
                            orig_index = len(results) - 1 - i
                            if orig_index > 0:
                                prev_score = results[orig_index - 1]["estimated_score"]
                                diff = score - prev_score
                                if diff > 0:
                                    st.info(f"🔥 **Progress Boost!** Score increased by **+{diff:.1f}%** compared to previous assignment!")
                                elif diff == 0:
                                    st.info(f"🎯 **Consistent Mastery!** Maintained your score of {score:.1f}%.")
                                else:
                                    st.warning(f"📈 Score dropped by **{abs(diff):.1f}%**. Review feedback below!")
                            
                            st.markdown(report)
                            if t_url:
                                st.markdown(f"📥 **[Download Marked File ({t_name})]({t_url})**")
                        else:
                            st.warning(f"⏳ **{a_title}** — **PENDING REVIEW** ({sub_time}){late_badge}")
                            col_u1, col_u2 = st.columns([3, 1])
                            with col_u1:
                                st.caption("Uploaded wrong document by mistake?")
                            with col_u2:
                                if st.button(f"🗑️ Unsubmit File", key=f"unsub_{sub_id}"):
                                    try:
                                        supabase.table("submissions").delete().eq("id", sub_id).execute()
                                        st.warning("⚠️ Submission removed! You can now re-upload.")
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"Error removing submission: {e}")
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
            
            try:
                p_res = supabase.table("submissions").select("*").ilike("student_name", student_name).eq("status", "APPROVED").order("id", desc=False).execute()
                p_results = p_res.data
                
                l_res = supabase.table("submissions").select("*").ilike("student_name", student_name).eq("is_late", 1).order("id", desc=True).execute()
                late_notices = l_res.data
            except:
                p_results = []
                late_notices = []
            
            if late_notices:
                st.warning(f"⚠️ **COMPLETED LATE:** {student_name} submitted assignments past deadline:")
                for l in late_notices:
                    st.caption(f"• **{l['assignment_title']}** (Submitted: {l['submitted_at']})")
                st.divider()
            
            if p_results:
                scores = [row["estimated_score"] for row in p_results]
                avg_score = sum(scores) / len(scores) if scores else 0
                latest_score = scores[-1]
                
                if latest_score >= 85.0 or (len(scores) > 1 and scores[-1] > scores[-2]):
                    st.snow()
                    st.success(f"🎉 **Achievement Highlight!** {student_name} scored **{latest_score:.1f}%** on her latest assignment!")
                
                st.subheader(f"📈 Performance Tracking for {student_name}")
                chart_data = {row["assignment_title"]: row["estimated_score"] for row in p_results}
                st.line_chart(chart_data)
                
                m1, m2, m3 = st.columns(3)
                m1.metric("Average Score 📊", f"{avg_score:.1f}%")
                m2.metric("Latest Score 🎯", f"{latest_score:.1f}%")
                m3.metric("Assignments Completed 📝", len(p_results))
                
                st.divider()
                st.subheader("⚠️ Detailed Evaluation Reports & Key Takeaways")
                for row in reversed(p_results):
                    late_tag = " (⚠️ Completed Late)" if row["is_late"] == 1 else ""
                    with st.expander(f"📌 Assignment: {row['assignment_title']} (Score: {row['estimated_score']}%){late_tag} - {row['submitted_at']}"):
                        st.markdown(row["final_report"])
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
        
        with st.expander("📅 **Set Assignment Deadlines**"):
            d_title = st.text_input("Assignment Title for Deadline", placeholder="e.g., Ch 3 Osmosis HW")
            d_date = st.date_input("Due Date")
            d_time = st.time_input("Due Time", value=datetime.time(23, 59))
            
            if st.button("📌 Save Assignment Deadline"):
                full_due_str = f"{d_date.strftime('%Y-%m-%d')} {d_time.strftime('%H:%M:%S')}"
                try:
                    supabase.table("deadlines").upsert(
                        {"assignment_title": d_title.strip(), "due_date": full_due_str},
                        on_conflict="assignment_title"
                    ).execute()
                    st.success(f"✅ Deadline set for '{d_title}' at {full_due_str}")
                except Exception as e:
                    st.error(f"Error saving deadline: {e}")
        
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
                
                try:
                    late_hw = supabase.table("submissions").select("*").ilike("student_name", s_name).eq("is_late", 1).execute().data
                except:
                    late_hw = []
                
                if late_hw:
                    st.warning(f"⚠️ **Completed Late ({len(late_hw)} Submissions):**")
                    for l in late_hw:
                        st.caption(f"• **{l['assignment_title']}** (Submitted on {l['submitted_at']})")
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
        
        try:
            pending_count = len(supabase.table("submissions").select("*").eq("status", "PENDING").execute().data)
            approved_count = len(supabase.table("submissions").select("*").eq("status", "APPROVED").execute().data)
            late_count = len(supabase.table("submissions").select("*").eq("is_late", 1).execute().data)
        except:
            pending_count, approved_count, late_count = 0, 0, 0
        
        m1, m2, m3 = st.columns(3)
        m1.metric("Pending Reviews ⏳", pending_count)
        m2.metric("Approved Reports ✅", approved_count)
        m3.metric("Late Submissions ⚠️️", late_count)
        st.divider()
        
        dashboard_mode = st.radio(
            "Select Management Action:", 
            ["⏳ Review Pending Submissions & Generate Follow-up Questions", "✅ Manage Approved Reports"],
            horizontal=True
        )
        st.divider()
        
        if dashboard_mode == "⏳ Review Pending Submissions & Generate Follow-up Questions":
            try:
                pending_list = supabase.table("submissions").select("*").eq("status", "PENDING").execute().data
            except:
                pending_list = []
            
            if pending_list:
                options = {f"ID #{row['id']} | Student: {row['student_name']} - {row['assignment_title']} ({'⚠️ LATE' if row['is_late']==1 else 'ON TIME'})": row for row in pending_list}
                selected_option = st.selectbox("Select Submission:", list(options.keys()))
                
                selected_row = options[selected_option]
                sub_id = selected_row["id"]
                s_name = selected_row["student_name"]
                a_title = selected_row["assignment_title"]
                f_name = selected_row["file_name"]
                m_type = selected_row["mime_type"]
                f_url = selected_row.get("file_url", "")
                ai_draft = selected_row["ai_draft"]
                sub_time = selected_row["submitted_at"]
                is_late = selected_row["is_late"]
                
                if is_late == 1:
                    st.error(f"🚨 **LATE SUBMISSION NOTIFICATION:** {s_name} submitted this assignment after deadline on {sub_time}.")
                
                col_file, col_edit = st.columns([1, 1])
                
                with col_file:
                    st.subheader(f"📄 Original File ({f_name})")
                    if m_type == "text/url":
                        st.info("🔗 **Google Drive Shared Link Submission:**")
                        st.markdown(f"[👉 Click here to open student's Google Drive File]({f_url})")
                    elif m_type and "image" in m_type:
                        st.image(f_url, caption=f"Submitted by {s_name}", use_column_width=True)
                    else:
                        st.markdown(f"[📄 Click here to view/download the Student's PDF]({f_url})")
                    
                    st.divider()
                    st.subheader("📋 Official Cambridge Mark Scheme (PDF / Image)")
                    st.caption("Upload the official mark scheme PDF or answer key image for this specific quiz/exam.")
                    ms_file = st.file_uploader("Upload Mark Scheme PDF/Image", type=["pdf", "png", "jpg", "jpeg"], key=f"ms_up_{sub_id}")
                    
                    st.divider()
                    st.subheader("✍ Upload Teacher Marked File for Student")
                    corrected_file_upload = st.file_uploader("Upload corrected PDF notes for student", type=["pdf", "png", "jpg"], key=f"up_{sub_id}")
                
                with col_edit:
                    st.subheader("✏️ AI Report Generation & Editing")
                    
                    c_m1, c_m2 = st.columns(2)
                    with c_m1:
                        teacher_raw_score = st.number_input("Marks Obtained:", min_value=0.0, max_value=200.0, value=47.0, step=1.0, key=f"raw_{sub_id}")
                    with c_m2:
                        teacher_max_score = st.number_input("Total Max Marks:", min_value=1.0, max_value=200.0, value=67.0, step=1.0, key=f"max_{sub_id}")
                    
                    if not ai_draft:
                        if st.button("⚡ Generate AI Draft Report", type="secondary"):
                            with st.spinner("Analyzing student submission against Official Mark Scheme..."):
                                try:
                                    ms_bytes = ms_file.getvalue() if ms_file else None
                                    ms_mime = ms_file.type if ms_file else None
                                    
                                    # Fetch the file bytes for Gemini from the URL
                                    if m_type == "text/url":
                                        gemini_file_bytes = f_url.encode("utf-8")
                                    else:
                                        response = requests.get(f_url)
                                        gemini_file_bytes = response.content
                                    
                                    generated_draft = analyze_homework_gemini(
                                        s_name, a_title, teacher_instructions, gemini_file_bytes, m_type, f_name,
                                        actual_mark=teacher_raw_score, total_mark=teacher_max_score,
                                        mark_scheme_bytes=ms_bytes, mark_scheme_mime=ms_mime
                                    )
                                    calc_percentage = round((teacher_raw_score / teacher_max_score) * 100, 1) if teacher_max_score > 0 else 0.0
                                    
                                    supabase.table("submissions").update({
                                        "ai_draft": generated_draft,
                                        "estimated_score": calc_percentage
                                    }).eq("id", sub_id).execute()
                                    
                                    st.success("✅ Draft generated with accurate marks & mark scheme alignment!")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"❌ Error generating draft: {e}")
                    else:
                        st.info("💡 AI Draft is ready below. Review and edit as needed before final approval.")
                    
                    edited_report = st.text_area("Edit Final Report (Markdown):", value=ai_draft, height=350, key=f"edit_rep_{sub_id}")
                    
                    if st.button("✅ Approve & Publish Report to Student", type="primary"):
                        t_corr_url = None
                        t_corr_name = ""
                        t_corr_mime = ""
                        
                        if corrected_file_upload:
                            corr_bytes = corrected_file_upload.getvalue()
                            t_corr_name = corrected_file_upload.name
                            t_corr_mime = corrected_file_upload.type if corrected_file_upload.type else "application/pdf"
                            
                            corr_ext = t_corr_name.split('.')[-1] if '.' in t_corr_name else 'pdf'
                            corr_path = f"{s_name}/corrected_{uuid.uuid4()}.{corr_ext}"
                            
                            try:
                                # Upload to Storage (Using 'homework_files' bucket)
                                supabase.storage.from_("homework_files").upload(
                                    path=corr_path,
                                    file=corr_bytes,
                                    file_options={"content-type": t_corr_mime}
                                )
                                t_corr_url = supabase.storage.from_("homework_files").get_public_url(corr_path)
                            except Exception as e:
                                st.error(f"Error uploading corrected file: {e}")
                                st.stop()
                        
                        try:
                            supabase.table("submissions").update({
                                "final_report": edited_report,
                                "status": "APPROVED",
                                "teacher_corrected_url": t_corr_url,
                                "teacher_corrected_name": t_corr_name,
                                "teacher_corrected_mime": t_corr_mime
                            }).eq("id", sub_id).execute()
                            
                            st.success("🎉 Report approved and published successfully!")
                            st.balloons()
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ Error approving report: {e}")
            else:
                st.info("🎉 No pending submissions to review right now!")
        
        elif dashboard_mode == "✅ Manage Approved Reports":
            try:
                appr_list = supabase.table("submissions").select("*").eq("status", "APPROVED").execute().data
            except:
                appr_list = []
            
            if appr_list:
                options = {f"ID #{row['id']} | Student: {row['student_name']} - {row['assignment_title']} (Score: {row['estimated_score']}%)": row for row in appr_list}
                selected_option = st.selectbox("Select Approved Report to Manage:", list(options.keys()), key="manage_appr_select")
                
                selected_row = options[selected_option]
                sub_id = selected_row["id"]
                
                st.markdown(selected_row["final_report"])
                
                col_m1, col_m2 = st.columns(2)
                with col_m1:
                    if st.button("🔄 Revert Report Back to Pending", key=f"revert_{sub_id}"):
                        try:
                            supabase.table("submissions").update({"status": "PENDING"}).eq("id", sub_id).execute()
                            st.warning("⚠️ Report reverted to Pending review.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error reverting: {e}")
                with col_m2:
                    if st.button("🗑️️ Delete Submission Permanently", key=f"del_appr_{sub_id}", type="primary"):
                        try:
                            supabase.table("submissions").delete().eq("id", sub_id).execute()
                            st.error("🗑️ Submission deleted successfully.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error deleting: {e}")
            else:
                st.info("No approved reports.")
                
    elif pin != "":
        st.error("🔒 Incorrect Teacher Passcode!")
    else:
        st.info("🔒 Enter teacher secret passcode.")
       
 
             
