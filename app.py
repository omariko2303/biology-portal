import streamlit as st
import google.generativeai as genai

st.set_page_config(page_title="Biology Performance Portal", page_icon="🧬", layout="wide")

st.title("🧬 Biology Performance & Study Portal")
st.write("Welcome to your Biology analysis and study workspace.")

# Sidebar for settings
with st.sidebar:
    st.header("⚙️ Settings")
    api_key = st.text_input("Enter Gemini API Key:", type="password")
    if api_key:
        genai.configure(api_key=api_key)
        st.success("API Key saved!")

# Main Tabs
tab1, tab2, tab3 = st.tabs(["📊 Quiz Analysis", "📚 Core Topics", "🤖 AI Biology Tutor"])

with tab1:
    st.header("Quiz Performance Breakdown")
    quiz_name = st.text_input("Quiz Title:", "Cell Biology & Transport Mechanisms")
    score = st.number_input("Your Score (%):", min_value=0, max_value=100, value=85)
    weak_areas = st.text_area("Topics needing review:", "Active transport, Enzyme kinetics, Osmosis calculations")
    
    if st.button("Generate Feedback Report"):
        if not api_key:
            st.warning("Please enter your Gemini API Key in the sidebar.")
        else:
            try:
                model = genai.GenerativeModel('gemini-1.5-flash')
                prompt = f"Provide a concise, highly structured study plan for a Biology student who scored {score}% on '{quiz_name}'. Key topics needing review: {weak_areas}."
                response = model.generate_content(prompt)
                st.subheader("📋 Personal Study Plan")
                st.markdown(response.text)
            except Exception as e:
                st.error(f"Error generating report: {e}")

with tab2:
    st.header("Key Biology Syllabus Topics")
    st.markdown("""
    * **Cell Structure & Transport:** Organelles, Osmosis, Active Transport, Diffusion.
    * **Biological Molecules:** Carbohydrates, Proteins, Lipids, Enzymes.
    * **Genetics & Molecular Biology:** DNA Replication, Protein Synthesis, Inheritance.
    * **Physiology:** Gas Exchange, Circulatory System, Nervous System.
    """)

with tab3:
    st.header("Ask the AI Biology Tutor")
    user_query = st.text_input("Ask any Biology question or topic explanation:")
    if st.button("Get Answer"):
        if not api_key:
            st.warning("Please enter your Gemini API Key in the sidebar.")
        else:
            try:
                model = genai.GenerativeModel('gemini-1.5-flash')
                response = model.generate_content(f"You are an expert Biology tutor. Answer the following clearly: {user_query}")
                st.write(response.text)
            except Exception as e:
                st.error(f"Error: {e}")
