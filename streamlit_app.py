"""
Skill Assessment Agent -- Streamlit Frontend
UI/UX updated to True Gemini Aesthetic (Compact Sidebar, Open Flow, Soft Geometry)
"""

import os
import time
import streamlit as st
from dotenv import load_dotenv
import streamlit.components.v1 as components

load_dotenv()

# ──────────────────────────────────────────────
# Page Config
# ──────────────────────────────────────────────
st.set_page_config(
    page_title="Skill Assessment Agent",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ──────────────────────────────────────────────
# Gemini UI/UX Custom CSS Injection
# ──────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600&display=swap');

html, body, [class*="css"], .stApp, [data-testid="stAppViewContainer"] {
    font-family: 'Google Sans', 'Outfit', sans-serif !important;
    color: #1F1F1F !important;
}

.stApp {
    background-color: #FFFFFF !important;
}

[data-testid="stSidebar"] {
    background-color: #F0F4F9 !important;
    border-right: none !important;
    padding-top: 2rem !important;
}
[data-testid="stSidebar"] * {
    color: #1F1F1F !important;
}

[data-testid="stFileUploadDropzone"] {
    padding: 1rem !important;
    min-height: 80px !important;
    border-radius: 16px !important;
    background-color: #FFFFFF !important;
    border: 1px dashed #C4C7C5 !important;
}
[data-testid="stFileUploadDropzone"] div div::before {
    display: none !important;
}
[data-testid="stFileUploadDropzone"] div div small {
    display: none !important;
}

.stRadio > div {
    gap: 0.5rem !important;
}
[data-testid="stSidebar"] .stMarkdown {
    margin-bottom: -15px !important;
}

h1 {
    font-size: 2.25rem !important;
    font-weight: 400 !important;
    letter-spacing: -0.02em !important;
    color: #1F1F1F !important;
}
h3 {
    font-size: 1.25rem !important;
    font-weight: 500 !important;
}

.stTextArea textarea, .stTextInput input {
    border-radius: 16px !important;
    background-color: #F0F4F9 !important;
    border: none !important;
    color: #1F1F1F !important;
    padding: 1rem !important;
}
.stTextArea textarea:focus, .stTextInput input:focus {
    box-shadow: 0 0 0 2px #10B981 !important;
}

div[data-testid="stAlert"] {
    background-color: #F0F4F9 !important;
    border: none !important;
    border-radius: 16px !important;
    color: #1F1F1F !important;
}

.stProgress > div > div > div > div {
    background-color: #10B981 !important;
}

/* Skill overlap tags */
.skill-tag-matched {
    display: inline-block;
    padding: 3px 10px;
    border-radius: 20px;
    font-size: 0.8rem;
    font-weight: 500;
    margin: 2px 3px;
    background: #D1FAE5;
    color: #065F46;
}
.skill-tag-missing {
    display: inline-block;
    padding: 3px 10px;
    border-radius: 20px;
    font-size: 0.8rem;
    font-weight: 500;
    margin: 2px 3px;
    background: #FEE2E2;
    color: #991B1B;
}
.skill-tag-extra {
    display: inline-block;
    padding: 3px 10px;
    border-radius: 20px;
    font-size: 0.8rem;
    font-weight: 500;
    margin: 2px 3px;
    background: #DBEAFE;
    color: #1E40AF;
}

/* Priority badges */
.priority-critical { background: #FEE2E2; color: #991B1B; padding: 2px 10px; border-radius: 12px; font-size: 0.75rem; font-weight: 600; }
.priority-high { background: #FFEDD5; color: #9A3412; padding: 2px 10px; border-radius: 12px; font-size: 0.75rem; font-weight: 600; }
.priority-medium { background: #DBEAFE; color: #1E40AF; padding: 2px 10px; border-radius: 12px; font-size: 0.75rem; font-weight: 600; }
.priority-low { background: #D1FAE5; color: #065F46; padding: 2px 10px; border-radius: 12px; font-size: 0.75rem; font-weight: 600; }

</style>
""", unsafe_allow_html=True)

# ──────────────────────────────────────────────
# Session State Initialization
# ──────────────────────────────────────────────
defaults = {
    "parsed_resume": None,
    "parsed_jd": None,
    "resume_text": None,
    "jd_text": None,
    "current_step": "upload",
    "assessment_results": None,
    "gap_analysis": None,
    "learning_plan": None,
    "loaded_paths": [],
    "current_gap_index": 0,
    "orchestrator": None,
    "chat_history": [],
    "awaiting_answer": False,
    "current_question_obj": None,
    "assessment_started": False,
}
for key, val in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = val


# ──────────────────────────────────────────────
# Helper function: Gemini Style Stepper
# ──────────────────────────────────────────────
def render_stepper(current_step_id):
    steps = [
        {"id": "upload", "label": "1. Upload Docs"},
        {"id": "parsed", "label": "2. AI Parsing"},
        {"id": "assessment", "label": "3. Assessment"},
        {"id": "results", "label": "4. Results"}
    ]

    step_map = {"upload": 0, "parsed": 1, "assessment": 2, "results": 3}
    current_idx = step_map.get(current_step_id, 0)

    html = '<div style="display: flex; justify-content: space-between; align-items: center; margin: 0.5rem 0 2.5rem 0; font-family: \'Google Sans\', sans-serif;">'

    for i, step in enumerate(steps):
        if i < current_idx:
            color = "#10B981"
            weight = "600"
        elif i == current_idx:
            color = "#1F1F1F"
            weight = "600"
        else:
            color = "#C4C7C5"
            weight = "400"

        html += f'<div style="color: {color}; font-weight: {weight}; font-size: 0.95rem;">{step["label"]}</div>'

        if i < len(steps) - 1:
            line_color = "#10B981" if i < current_idx else "#E3E3E3"
            html += f'<div style="flex-grow: 1; height: 1px; background-color: {line_color}; margin: 0 1rem;"></div>'

    html += '</div>'
    st.markdown(html, unsafe_allow_html=True)


# ──────────────────────────────────────────────
# Sidebar
# ──────────────────────────────────────────────
with st.sidebar:
    st.markdown("<div style='font-size: 1.1rem; font-weight: 500; margin-bottom: 0.5rem;'>Input Documents</div>", unsafe_allow_html=True)

    resume_file = st.file_uploader(
        "Resume (PDF, DOCX, TXT)",
        type=["pdf", "docx", "txt"],
        label_visibility="collapsed"
    )

    st.markdown("<br>", unsafe_allow_html=True)

    st.markdown("<div style='font-size: 0.9rem; font-weight: 500; margin-bottom: 0.5rem;'>Job Description</div>", unsafe_allow_html=True)
    jd_input_method = st.radio(
        "Job Description Input",
        ["Paste Text", "Upload File"],
        horizontal=True,
        label_visibility="collapsed"
    )

    jd_text_input = ""
    jd_file = None
    if jd_input_method == "Paste Text":
        jd_text_input = st.text_area(
            "Paste Job Description",
            height=120,
            placeholder="Paste JD text here...",
            label_visibility="collapsed"
        )
    else:
        jd_file = st.file_uploader(
            "Upload JD",
            type=["pdf", "docx", "txt"],
            key="jd_upload",
            label_visibility="collapsed"
        )

    st.markdown("<br><br>", unsafe_allow_html=True)

    with st.expander("Advanced Settings"):
        max_skills_to_assess = st.slider(
            "Skills to assess", 1, 10, 1,
        )

    col_sb1, col_sb2 = st.columns(2)
    with col_sb1:
        if st.button("Start Over", use_container_width=True):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()
    with col_sb2:
        if st.button("Clear Cache", use_container_width=True):
            import shutil
            cache_dir = os.path.join(os.path.dirname(__file__), ".cache")
            if os.path.exists(cache_dir):
                shutil.rmtree(cache_dir)
            st.rerun()


# ──────────────────────────────────────────────
# Header & Stepper
# ──────────────────────────────────────────────
st.markdown("<h1>AI Skill Assessment Agent</h1>", unsafe_allow_html=True)
st.markdown("<p style='color: #444746; font-size: 1.1rem; margin-top: -10px; margin-bottom: 2rem;'>Upload a resume and job description to generate a personalized learning plan.</p>", unsafe_allow_html=True)

render_stepper(st.session_state.current_step)


# ══════════════════════════════════════════════
# STEP 1: Upload
# ══════════════════════════════════════════════
if st.session_state.current_step == "upload":

    col1, col2 = st.columns(2, gap="large")

    with col1:
        with st.container(border=True):
            st.markdown("### Resume Status")
            if resume_file:
                st.markdown(f"**Ready:** `{resume_file.name}`")
                from app.utils.pdf_parser import extract_text
                try:
                    resume_text = extract_text(resume_file, resume_file.name)
                    st.session_state.resume_text = resume_text
                    st.caption(f"Extracted {len(resume_text)} characters")
                except Exception as e:
                    st.error(f"Error extracting text: {e}")
            else:
                st.markdown("<p style='color:#444746; font-size: 0.95rem;'>Awaiting resume upload from the sidebar...</p>", unsafe_allow_html=True)

    with col2:
        with st.container(border=True):
            st.markdown("### Job Description Status")
            if jd_input_method == "Paste Text" and jd_text_input:
                st.session_state.jd_text = jd_text_input
                st.markdown("**Text Loaded**")
                st.caption(f"Extracted {len(jd_text_input)} characters")
            elif jd_input_method == "Upload File" and jd_file:
                from app.utils.pdf_parser import extract_text
                try:
                    jd_text = extract_text(jd_file, jd_file.name)
                    st.session_state.jd_text = jd_text
                    st.markdown(f"**Ready:** `{jd_file.name}`")
                    st.caption(f"Extracted {len(jd_text)} characters")
                except Exception as e:
                    st.error(f"Error extracting JD: {e}")
            else:
                st.markdown("<p style='color:#444746; font-size: 0.95rem;'>Awaiting Job Description from the sidebar...</p>", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    both_ready = st.session_state.resume_text and st.session_state.jd_text

    if both_ready:
        col_btn1, col_btn2, col_btn3 = st.columns([1, 2, 1])
        with col_btn2:
            if st.button("Analyze Documents", type="primary", use_container_width=True):
                with st.spinner("AI is analyzing your resume and job description..."):
                    try:
                        from app.agents.parser_agent import parse_both
                        parsed_resume, parsed_jd = parse_both(
                            st.session_state.resume_text,
                            st.session_state.jd_text,
                        )
                        st.session_state.parsed_resume = parsed_resume
                        st.session_state.parsed_jd = parsed_jd
                        st.session_state.current_step = "parsed"
                        st.rerun()
                    except Exception as e:
                        st.error(f"Parsing failed: {e}")
                        st.exception(e)
    else:
        st.info("Please provide both a resume and a job description to proceed.")


# ══════════════════════════════════════════════
# STEP 2: Parsed Results
# ══════════════════════════════════════════════
elif st.session_state.current_step == "parsed":
    parsed_resume = st.session_state.parsed_resume
    parsed_jd = st.session_state.parsed_jd

    col1, col2 = st.columns(2, gap="large")

    with col1:
        with st.container(border=True):
            st.markdown("### Candidate Profile")
            st.markdown(
                f"**Name:** {parsed_resume.candidate_name}  \n"
                f"**Role:** {parsed_resume.current_role}  \n"
                f"**Experience:** {parsed_resume.total_experience_years or 'N/A'} years"
            )
            if parsed_resume.education:
                st.caption(", ".join(parsed_resume.education[:2]))
            if parsed_resume.summary:
                st.markdown(f"_{parsed_resume.summary}_")

            st.markdown("<br>", unsafe_allow_html=True)
            st.markdown("#### Skills Found")
            for skill in parsed_resume.skills:
                level_colors = {
                    "novice": "#EF4444", "beginner": "#F97316",
                    "intermediate": "#EAB308", "advanced": "#22C55E", "expert": "#3B82F6",
                }
                color = level_colors.get(skill.claimed_level.value, "#6B7280")
                exp_str = f" ({skill.years_experience}y)" if skill.years_experience else ""
                st.markdown(
                    f'<span style="color:{color}; font-weight:500;">{skill.name}</span>'
                    f' <span style="color:#888; font-size:0.85rem;">{skill.claimed_level.value.title()}{exp_str}</span>',
                    unsafe_allow_html=True,
                )

    with col2:
        with st.container(border=True):
            st.markdown("### Job Requirements")
            st.markdown(
                f"**Title:** {parsed_jd.job_title}  \n"
                f"**Company:** {parsed_jd.company or 'N/A'}  \n"
                f"**Seniority:** {parsed_jd.seniority_level}"
            )
            if parsed_jd.summary:
                st.markdown(f"_{parsed_jd.summary}_")

            st.markdown("<br>", unsafe_allow_html=True)
            st.markdown("#### Required Skills")
            for skill in parsed_jd.skills:
                req_colors = {"required": "#EF4444", "preferred": "#EAB308", "nice_to_have": "#22C55E"}
                color = req_colors.get(skill.requirement_type.value, "#6B7280")
                st.markdown(
                    f'<span style="color:{color}; font-weight:500;">{skill.name}</span>'
                    f' <span style="color:#888; font-size:0.85rem;">'
                    f'Min: {skill.required_level.value.title()} '
                    f'({skill.requirement_type.value.replace("_"," ").title()})</span>',
                    unsafe_allow_html=True,
                )

    # ── Skill Overlap ──
    st.markdown("<br>", unsafe_allow_html=True)
    with st.container(border=True):
        st.markdown("### Skill Overlap Analysis")

        resume_skill_names = {s.name.lower() for s in parsed_resume.skills}
        jd_skill_names = {s.name.lower() for s in parsed_jd.skills}

        matched = resume_skill_names & jd_skill_names
        missing = jd_skill_names - resume_skill_names
        extra = resume_skill_names - jd_skill_names

        col_m1, col_m2, col_m3 = st.columns(3)
        with col_m1:
            st.metric("Matched Skills", len(matched))
            tags = "".join(f'<span class="skill-tag-matched">{s.title()}</span>' for s in sorted(matched))
            if tags:
                st.markdown(tags, unsafe_allow_html=True)
        with col_m2:
            st.metric("Missing from Resume", len(missing))
            tags = "".join(f'<span class="skill-tag-missing">{s.title()}</span>' for s in sorted(missing))
            if tags:
                st.markdown(tags, unsafe_allow_html=True)
        with col_m3:
            st.metric("Extra Skills", len(extra))
            tags = "".join(f'<span class="skill-tag-extra">{s.title()}</span>' for s in sorted(extra))
            if tags:
                st.markdown(tags, unsafe_allow_html=True)

    # Next step
    st.markdown("<br>", unsafe_allow_html=True)
    col_btn1, col_btn2, col_btn3 = st.columns([1, 2, 1])
    with col_btn2:
        if st.button("Start Conversational Assessment", type="primary", use_container_width=True):
            st.session_state.current_step = "assessment"
            st.rerun()


# ══════════════════════════════════════════════
# STEP 3: Assessment
# ══════════════════════════════════════════════
elif st.session_state.current_step == "assessment":
    from app.agents.assessor_agent import AssessmentOrchestrator, MIN_QUESTIONS_PER_SKILL, MAX_QUESTIONS_PER_SKILL

    if st.session_state.orchestrator is None:
        st.session_state.orchestrator = AssessmentOrchestrator(
            parsed_resume=st.session_state.parsed_resume,
            parsed_jd=st.session_state.parsed_jd,
            max_skills=max_skills_to_assess,
        )
        st.session_state.chat_history = []
        st.session_state.awaiting_answer = False
        st.session_state.current_question_obj = None
        st.session_state.assessment_started = False

    orchestrator = st.session_state.orchestrator

    with st.container(border=True):
        st.markdown("### Conversational Assessment")

        if not st.session_state.assessment_started:
            st.markdown(
                "<p style='color: #444746;'>The following skills will be assessed based on job requirements. "
                f"You will be asked {MIN_QUESTIONS_PER_SKILL}-{MAX_QUESTIONS_PER_SKILL} adaptive questions per skill.</p>",
                unsafe_allow_html=True,
            )
            overview = orchestrator.get_skill_overview()
            for item in overview:
                req_label = item["requirement"].replace("_", " ").title()
                st.markdown(
                    f"**{item['index']}. {item['skill']}** -- "
                    f"Required: {item['required_level'].title()} ({req_label}) | "
                    f"Claimed: {item['claimed_level'].title()}"
                )

            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("Begin Assessment", type="primary"):
                st.session_state.assessment_started = True
                question_obj = orchestrator.get_next_question()
                if question_obj:
                    st.session_state.current_question_obj = question_obj
                    st.session_state.awaiting_answer = True
                    st.session_state.chat_history.append({
                        "role": "assistant",
                        "content": (
                            f"**Assessing: {question_obj.skill_name}** "
                            f"(Skill {orchestrator.current_skill_number}/{orchestrator.total_skills})\n\n"
                            f"**Question {question_obj.question_number}** "
                            f"[{question_obj.difficulty.value.title()}]:\n\n"
                            f"{question_obj.question}"
                        ),
                    })
                st.rerun()
        else:
            # Progress
            total = orchestrator.total_skills
            completed = orchestrator.current_skill_index
            if orchestrator.is_complete:
                completed = total
            st.progress(
                completed / total if total > 0 else 0,
                text=f"Progress: {completed}/{total} skills assessed",
            )

            # Chat history
            for msg in st.session_state.chat_history:
                with st.chat_message(msg["role"]):
                    st.markdown(msg["content"])

            # Answer input
            if st.session_state.awaiting_answer and not orchestrator.is_complete:
                answer = st.chat_input("Type your answer here...")

                if answer:
                    st.session_state.chat_history.append({"role": "user", "content": answer})

                    with st.spinner("Evaluating your response..."):
                        response = orchestrator.submit_answer(answer)

                    score_display = "| " * response.score + ". " * (5 - response.score)
                    eval_msg = f"**Score:** [{score_display.strip()}] {response.score}/5\n\n{response.reasoning}"
                    st.session_state.chat_history.append({"role": "assistant", "content": eval_msg})

                    question_obj = orchestrator.get_next_question()
                    if question_obj:
                        prev_skill = response.skill_name
                        new_skill = question_obj.skill_name

                        if new_skill != prev_skill:
                            st.session_state.chat_history.append({
                                "role": "assistant",
                                "content": (
                                    f"**{prev_skill} assessment complete.**\n\n"
                                    f"Moving to: **{new_skill}** "
                                    f"(Skill {orchestrator.current_skill_number}/{orchestrator.total_skills})"
                                ),
                            })

                        st.session_state.current_question_obj = question_obj
                        st.session_state.chat_history.append({
                            "role": "assistant",
                            "content": (
                                f"**Question {question_obj.question_number}** "
                                f"[{question_obj.difficulty.value.title()}]:\n\n"
                                f"{question_obj.question}"
                            ),
                        })
                        st.session_state.awaiting_answer = True
                    else:
                        st.session_state.awaiting_answer = False
                        st.session_state.chat_history.append({
                            "role": "assistant",
                            "content": "**Assessment Complete.** All skills have been assessed. View your results below.",
                        })

                    st.rerun()

    # Assessment summary and next button (outside the chat container)
    if orchestrator.is_complete:
        results = orchestrator.get_all_results()
        st.session_state.assessment_results = results

        st.markdown("<br>", unsafe_allow_html=True)
        with st.container(border=True):
            st.markdown("### Assessment Summary")
            for result in results:
                claimed = result.claimed_level.value.title()
                assessed = result.assessed_level.value.title()

                if result.assessed_level.numeric >= result.claimed_level.numeric:
                    indicator = "PASS"
                    ind_color = "#065F46"
                    ind_bg = "#D1FAE5"
                elif result.assessed_level.numeric == result.claimed_level.numeric - 1:
                    indicator = "CLOSE"
                    ind_color = "#92400E"
                    ind_bg = "#FEF3C7"
                else:
                    indicator = "GAP"
                    ind_color = "#991B1B"
                    ind_bg = "#FEE2E2"

                st.markdown(
                    f"**{result.skill_name}:** {claimed} &rarr; {assessed} "
                    f'<span style="background:{ind_bg}; color:{ind_color}; padding:2px 10px; '
                    f'border-radius:12px; font-size:0.8rem; font-weight:600;">{indicator}</span> '
                    f'<span style="color:#888; font-size:0.85rem;">(Confidence: {result.confidence:.0%})</span>',
                    unsafe_allow_html=True,
                )

                # Show Q&A detail in expander
                with st.expander(f"View {result.skill_name} Q&A detail"):
                    for resp in result.responses:
                        st.markdown(f"**Q [{resp.difficulty.value.title()}]:** {resp.question}")
                        st.markdown(f"**A:** {resp.candidate_answer[:300]}")
                        st.caption(f"Score: {resp.score}/5 -- {resp.reasoning}")
                        st.markdown("---")

        st.markdown("<br>", unsafe_allow_html=True)
        col_btn1, col_btn2, col_btn3 = st.columns([1, 2, 1])
        with col_btn2:
            if st.button("View Gap Analysis & Learning Plan", type="primary", use_container_width=True):
                st.session_state.current_step = "results"
                st.rerun()


# ══════════════════════════════════════════════
# STEP 4: Results Dashboard
# ══════════════════════════════════════════════
elif st.session_state.current_step == "results":
    from app.agents.gap_analyzer import analyze_gaps
    from app.agents.plan_generator import generate_learning_plan_base, generate_paths_batch
    from app.models.schemas import GapAnalysisResult, PersonalizedLearningPlan, GapPriority

    if st.session_state.gap_analysis is None:
        with st.spinner("Analyzing skill gaps..."):
            st.session_state.gap_analysis = analyze_gaps(
                st.session_state.parsed_resume,
                st.session_state.parsed_jd,
                st.session_state.assessment_results or [],
            )

    if st.session_state.learning_plan is None:
        with st.spinner("Analyzing high-level learning strategy..."):
            st.session_state.learning_plan = generate_learning_plan_base(
                st.session_state.parsed_resume,
                st.session_state.parsed_jd,
                st.session_state.gap_analysis,
            )
        st.session_state.loaded_paths = []
        st.session_state.current_gap_index = 0

    gap_analysis = st.session_state.gap_analysis
    learning_plan = st.session_state.learning_plan
    
    total_gaps = gap_analysis.gaps
    batch_size = 3

    # Load the first batch automatically
    if st.session_state.current_gap_index == 0 and len(total_gaps) > 0:
        with st.spinner("Generating your top priority learning paths..."):
            first_batch = total_gaps[0:batch_size]
            new_paths = generate_paths_batch(first_batch, st.session_state.parsed_jd.job_title)
            st.session_state.loaded_paths.extend(new_paths)
            st.session_state.current_gap_index += batch_size
            
            # Keep the main plan object synced for PDF generation
            learning_plan.learning_paths = st.session_state.loaded_paths

    # ── Top Metrics ──
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Overall Match", f"{gap_analysis.overall_match_score:.0f}%")
    with col2:
        st.metric("Skill Gaps", len(gap_analysis.gaps))
    with col3:
        st.metric("Learning Hours", f"{learning_plan.total_estimated_hours:.0f}h")
    with col4:
        st.metric("Est. Weeks", f"{learning_plan.estimated_weeks:.1f}")

    st.caption("Weeks estimated at 10 hours/week of study")
    st.markdown(f"_{gap_analysis.summary}_")

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Radar Chart ──
    with st.container(border=True):
        st.markdown("### Skill Comparison")

        import plotly.graph_objects as go

        assessed_results = st.session_state.assessment_results or []
        assessed_map = {r.skill_name.lower(): r for r in assessed_results}
        resume_map = {s.name.lower(): s for s in st.session_state.parsed_resume.skills}

        skill_names = []
        required_levels = []
        current_levels = []

        for jd_skill in st.session_state.parsed_jd.skills:
            skill_names.append(jd_skill.name)
            required_levels.append(jd_skill.required_level.numeric)
            assessed = assessed_map.get(jd_skill.name.lower())
            if assessed:
                current_levels.append(assessed.assessed_level.numeric)
            else:
                rs = resume_map.get(jd_skill.name.lower())
                current_levels.append(rs.claimed_level.numeric if rs else 1)

        if skill_names:
            fig = go.Figure()
            fig.add_trace(go.Scatterpolar(
                r=required_levels, theta=skill_names, fill="toself",
                name="Required", line=dict(color="#EF4444"), opacity=0.25,
                fillcolor="rgba(239,68,68,0.08)",
            ))
            fig.add_trace(go.Scatterpolar(
                r=current_levels, theta=skill_names, fill="toself",
                name="Current", line=dict(color="#10B981"), opacity=0.25,
                fillcolor="rgba(16,185,129,0.08)",
            ))
            fig.update_layout(
                polar=dict(
                    bgcolor="rgba(0,0,0,0)",
                    radialaxis=dict(
                        visible=True, range=[0, 5],
                        tickvals=[1, 2, 3, 4, 5],
                        ticktext=["Novice", "Beginner", "Intermed.", "Advanced", "Expert"],
                        gridcolor="#E3E3E3", linecolor="#E3E3E3",
                    ),
                    angularaxis=dict(gridcolor="#E3E3E3", linecolor="#E3E3E3"),
                ),
                showlegend=True,
                height=450,
                margin=dict(t=40, b=40, l=80, r=80),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#444746", family="Google Sans, Outfit, sans-serif"),
                legend=dict(
                    orientation="h", yanchor="bottom", y=-0.15,
                    xanchor="center", x=0.5,
                    font=dict(color="#444746"),
                ),
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No skills to compare.")

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Strengths ──
    if gap_analysis.strengths:
        with st.container(border=True):
            st.markdown("### Strengths")
            for s in gap_analysis.strengths:
                st.markdown(f"- {s}")

        st.markdown("<br>", unsafe_allow_html=True)

    # ── Gap Analysis Detail ──
    with st.container(border=True):
        st.markdown("### Skill Gap Analysis")

        if not gap_analysis.gaps:
            st.success("No skill gaps found. Candidate meets all requirements.")
        else:
            for gap in gap_analysis.gaps:
                priority_class = f"priority-{gap.priority.value}"
                st.markdown(
                    f'**{gap.skill_name}** '
                    f'<span class="{priority_class}">{gap.priority.value.upper()}</span>',
                    unsafe_allow_html=True,
                )

                c1, c2, c3, c4 = st.columns(4)
                c1.caption("Current")
                c1.markdown(f"**{gap.current_level.value.title()}**")
                c2.caption("Required")
                c2.markdown(f"**{gap.required_level.value.title()}**")
                c3.caption("Gap")
                c3.markdown(f"**{gap.gap_size} level(s)**")
                c4.caption("Est. Hours")
                c4.markdown(f"**{gap.estimated_hours:.0f}h**")

                details = []
                if gap.adjacent_skills:
                    details.append(f"Related skills: {', '.join(gap.adjacent_skills)}")
                details.append(f"Learnability: {gap.learnability_score:.0%}")
                st.caption(" | ".join(details))

                st.markdown("<hr style='margin: 0.5rem 0; border-color: #F0F0F0;'>", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Quick Wins & Long Term ──
    has_qw = bool(learning_plan.quick_wins)
    has_lt = bool(learning_plan.long_term_goals)
    if has_qw or has_lt:
        col_qw, col_lt = st.columns(2, gap="large")
        with col_qw:
            if has_qw:
                with st.container(border=True):
                    st.markdown("### Quick Wins")
                    st.caption("Skills acquirable in under 20 hours")
                    for qw in learning_plan.quick_wins:
                        st.markdown(f"- {qw}")
        with col_lt:
            if has_lt:
                with st.container(border=True):
                    st.markdown("### Long-term Goals")
                    st.caption("Skills requiring 60+ hours of investment")
                    for lt in learning_plan.long_term_goals:
                        st.markdown(f"- {lt}")

        st.markdown("<br>", unsafe_allow_html=True)

    # ── Learning Plan (Paginated) ──
    st.markdown("### Personalized Learning Plan")
    for path in st.session_state.loaded_paths:
        priority_class = f"priority-{path.priority.value}"
        with st.container(border=True):
            st.markdown(
                f'#### {path.skill_name} '
                f'<span class="{priority_class}">{path.priority.value.upper()}</span>',
                unsafe_allow_html=True,
            )
            st.markdown(
                f"**{path.current_level.value.title()}** &rarr; **{path.target_level.value.title()}** "
                f"| ~{path.total_estimated_hours:.0f}h total"
            )
            st.markdown(f"<p style='color: #444746;'>{path.why_learn}</p>", unsafe_allow_html=True)

            if path.leverage_existing:
                st.markdown("**Your advantages:**")
                for adv in path.leverage_existing:
                    st.markdown(f"- {adv}")

            st.markdown("<hr style='margin: 1rem 0; border-color: #E3E3E3;'>", unsafe_allow_html=True)

            for i, milestone in enumerate(path.milestones, 1):
                st.markdown(f"**Milestone {i}: {milestone.title}** (~{milestone.estimated_hours:.0f}h)")
                if milestone.description:
                    st.caption(milestone.description)

                if milestone.resources:
                    for r in milestone.resources:
                        tag = "FREE" if r.is_free else "PAID"
                        tag_color = "#10B981" if r.is_free else "#EAB308"
                        hours_str = f" ~{r.estimated_hours:.0f}h" if r.estimated_hours else ""
                        if r.url:
                            st.markdown(
                                f'- [{r.title}]({r.url}) ({r.resource_type})'
                                f' <span style="color:{tag_color}; font-size:0.8rem; font-weight:500;">[{tag}]</span>'
                                f'{hours_str}',
                                unsafe_allow_html=True,
                            )
                        else:
                            st.markdown(
                                f'- {r.title} ({r.resource_type})'
                                f' <span style="color:{tag_color}; font-size:0.8rem; font-weight:500;">[{tag}]</span>'
                                f'{hours_str}',
                                unsafe_allow_html=True,
                            )

                if milestone.practice_project:
                    st.markdown(f"**Project:** {milestone.practice_project}")

                if i < len(path.milestones):
                    st.markdown("<hr style='margin: 0.8rem 0; border-color: #F5F5F5;'>", unsafe_allow_html=True)

    # Pagination Button
    if st.session_state.current_gap_index < len(total_gaps):
        remaining = len(total_gaps) - st.session_state.current_gap_index
        button_text = f"Generate Next {min(batch_size, remaining)} Paths 🚀"
        
        st.markdown("<br>", unsafe_allow_html=True)
        col_btn1, col_btn2, col_btn3 = st.columns([1, 2, 1])
        with col_btn2:
            if st.button(button_text, type="primary", use_container_width=True):
                with st.spinner("Analyzing and generating next paths..."):
                    start_idx = st.session_state.current_gap_index
                    end_idx = start_idx + batch_size
                    
                    next_batch = total_gaps[start_idx:end_idx]
                    new_paths = generate_paths_batch(next_batch, st.session_state.parsed_jd.job_title)
                    
                    st.session_state.loaded_paths.extend(new_paths)
                    st.session_state.current_gap_index += batch_size
                    
                    # Sync to main object
                    learning_plan.learning_paths = st.session_state.loaded_paths
                    
                    st.rerun()

    # ── PDF Export ──
    st.markdown("<br>", unsafe_allow_html=True)
    with st.container(border=True):
        st.markdown("### Export Report")
        st.caption("Download a complete PDF report with assessment results, gap analysis, and your personalized learning plan.")

        col_pdf1, col_pdf2, col_pdf3 = st.columns([1, 2, 1])
        with col_pdf2:
            if st.button("Generate PDF Report", type="primary", use_container_width=True):
                with st.spinner("Generating PDF..."):
                    from app.utils.modern_pdf_generator import generate_pdf

                    pdf_bytes = generate_pdf(
                        learning_plan,
                        gap_analysis,
                        st.session_state.assessment_results or []
                    )

                    st.session_state.pdf_bytes = pdf_bytes

            if "pdf_bytes" in st.session_state and st.session_state.pdf_bytes:
                st.download_button(
                    "Download PDF",
                    st.session_state.pdf_bytes,
                    file_name="report.pdf",
                    mime="application/pdf"
                )

    # ── Strengths Summary ──
    if learning_plan.strengths_summary:
        st.markdown("<br>", unsafe_allow_html=True)
        with st.container(border=True):
            st.markdown("### Remember Your Strengths")
            st.markdown(learning_plan.strengths_summary)

components.html("""
<script>
function printPage() {
    window.parent.print();
}
</script>

<button onclick="printPage()" 
style="
    padding:10px 20px;
    background:#10B981;
    color:white;
    border:none;
    border-radius:8px;
    cursor:pointer;
    font-size:16px;
">
Download PDF
</button>
""", height=80)

st.markdown("""
<style>
@media print {

    /* Hide sidebar */
    [data-testid="stSidebar"] {
        display: none !important;
    }

    /* Hide header */
    header {
        display: none !important;
    }

    /* Remove padding */
    .block-container {
        padding: 0 !important;
    }

    /* Ensure full width */
    .main {
        width: 100% !important;
    }
}
</style>
""", unsafe_allow_html=True)