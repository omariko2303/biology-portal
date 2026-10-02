import streamlit as st
import sqlite3
import datetime
import os
import requests
import tempfile
import google.generativeai as genai

# ==================== PAGE CONFIG & SETUP ====================
st.set_page_config(
    page_title="IGCSE Biology Homework Portal",
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

# ==================== HELPER FUNCTIONS ====================
def send_discord_notification(webhook_url, student_name, assignment):
    if webhook_url and webhook_url.strip():
        msg = {
            "content": f"🔔 **واجب جديد مرفوع!**\n👤 **الطالب:** {student_name}\n📚 **الواجب:** {assignment}\n⏳ بانتظار مراجعتك واعتمادك من لوحة المعلم."
        }
        try:
            requests.post(webhook_url, json=msg)
        except Exception:
            pass

def analyze_homework(api_key, file_bytes, mime_type, file_name, student_name, assignment_title, instructions):
    genai.configure(api_key=api_key)
    
    # Write bytes to temp file for Gemini API processing
    ext = os.path.splitext(file_name)[1]
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
st.title("🧬 IGCSE Biology Homework & Assessment Portal")

tab1, tab2, tab3 = st.tabs([
    "📤 بوابة الطالب (رفع الواجب)", 
    "📊 استعلام النتيجة (للطلاب)", 
    "🔒 لوحة المعلم (المراجعة والاعتماد)"
])

# -------------------- TAB 1: STUDENT SUBMIT --------------------
with tab1:
    st.header("إرسال الواجب (PDF أو صور)")
    
    api_key = st.text_input("Gemini API Key", type="password", help="أدخل مفتاح Gemini API")
    
    col1, col2 = st.columns(2)
    with col1:
        student_name = st.text_input("اسم الطالب", placeholder="مثال: Lara")
    with col2:
        assignment_title = st.text_input("عنوان الواجب", placeholder="مثال: Cell Biology & Osmosis")
        
    instructions = st.text_area(
        "تركيز التصحيح / Mark Scheme Focus", 
        value="Strictly enforce Cambridge Mark Scheme keywords (e.g. net movement, water potential, chloroplast vs chlorophyll, magnification formulas)."
    )
    
    uploaded_file = st.file_uploader("ارفق ملف الواجب (PDF, PNG, JPG)", type=["pdf", "png", "jpg", "jpeg"])
    
    if st.button("🚀 إرسال الواجب للمعلم", type="primary"):
        if not api_key:
            st.error("❌ يرجى أدخال Gemini API Key.")
        elif not student_name or not assignment_title:
            st.error("❌ يرجى ملء اسم الطالب وعنوان الواجب.")
        elif not uploaded_file:
            st.error("❌ يرجى اختيار ملف الواجب.")
        else:
            with st.spinner("جاري تحليل الواجب بواسطة الذكاء الاصطناعي وإرساله للمعلم..."):
                file_bytes = uploaded_file.read()
                mime_type = uploaded_file.type
                file_name = uploaded_file.name
                
                try:
                    # AI Processing
                    ai_draft = analyze_homework(
                        api_key, file_bytes, mime_type, file_name, 
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
                    
                    st.success(f"✅ تم تسليم الواجب بنجاح يا {student_name}! الواجب الآن قيد مراجعة المعلم، وستظهر لك النتيجة فور اعتمادها.")
                except Exception as e:
                    st.error(f"⚠️ حدث خطأ أثناء المعالجة: {e}")

# -------------------- TAB 2: STUDENT LOOKUP --------------------
with tab2:
    st.header("عرض نتائج الواجبات المعتمدة")
    search_name = st.text_input("أدخل اسم الطالب لمشاهدة النتائج المعتمدة")
    
    if st.button("🔍 بحث عن النتائج"):
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
                    st.subheader(f"📚 {row[0]} (تاريخ الاعتماد: {row[2]})")
                    st.markdown(row[1])
                    st.divider()
            else:
                st.info("ℹ️ لا توجد نتائج معتمدة حالياً بهذا الاسم. إذا كنت قد رفعت الواجب مؤخراً، فهو لا يزال قيد مراجعة المعلم.")

# -------------------- TAB 3: TEACHER DASHBOARD --------------------
with tab3:
    st.header("لوحة تحكم المعلم")
    
    pin = st.text_input("الرقم السري للمعلم", type="password")
    TEACHER_PIN = "1234"  # يمكنك تغيير الرقم السري من هنا
    
    if pin == TEACHER_PIN:
        st.success("🔓 تم فتح لوحة التحكم")
        
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT id, student_name, assignment_title, file_name, mime_type, ai_draft, submitted_at, file_bytes FROM submissions WHERE status = 'PENDING'")
        pending = c.fetchall()
        conn.close()
        
        if pending:
            options = {f"ID #{row[0]} | الطالب: {row[1]} - {row[2]} ({row[6]})": row for row in pending}
            selected_option = st.selectbox("اختر الواجب للمراجعة والاعتماد:", list(options.keys()))
            
            selected_row = options[selected_option]
            sub_id, s_name, a_title, f_name, m_type, ai_draft, sub_time, f_bytes = selected_row
            
            st.divider()
            col_file, col_edit = st.columns([1, 1])
            
            with col_file:
                st.subheader("📄 ملف الطالب المرفوع")
                if "image" in m_type:
                    st.image(f_bytes)
                else:
                    st.download_button(
                        label=f"⬇️ تحميل ملف الطالب ({f_name})",
                        data=f_bytes,
                        file_name=f_name,
                        mime=m_type
                    )
            
            with col_edit:
                st.subheader("✏️ مسودة التقرير (تعديل المعلم)")
                final_report_input = st.text_area("تعديل التقرير قبل نشره للطالب:", value=ai_draft, height=400)
                
                if st.button("✅ اعتماد ونشر التقرير للطالب", type="primary"):
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
                    st.success("🎉 تم اعتماد التقرير بنجاح! يمكن للطالب رؤيته الآن.")
                    st.rerun()
        else:
            st.info("🎉 لا توجد واجبات معلقة حالياً!")
    elif pin != "":
        st.error("🔒 الرقم السري غير صحيح!")
