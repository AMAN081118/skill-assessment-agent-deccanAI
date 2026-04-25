"""
Skill Assessment Agent — Streamlit Frontend
Step 2: Now with Resume + JD parsing via the Parser Agent.
"""

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

# ──────────────────────────────────────────────
# Page Config
# ──────────────────────────────────────────────
st.set_page_config(
    page_title="🎯 AI Skill Assessment Agent",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ──────────────────────────────────────────────
# Session State Initialization
# ──────────────────────────────────────────────
if "parsed_resume" not in st.session_state:
    st.session_state.parsed_resume = None
if "parsed_jd" not in st.session_state:
    st.session_state.parsed_jd = None
if "resume_text" not in st.session_state:
    st.session_state.resume_text = None
if "jd_text" not in st.session_state:
    st.session_state.jd_text = None
if "current_step" not in st.session_state:
    st.session_state.current_step = "upload"  # upload → parsed → assessment → results


# ──────────────────────────────────────────────
# Sidebar — Upload Documents
# ──────────────────────────────────────────────
with st.sidebar:
    st.header("📁 Upload Documents")

    resume_file = st.file_uploader(
        "Upload Resume",
        type=["pdf", "docx", "txt"],
        help="Supported formats: PDF, DOCX, TXT",
    )

    st.divider()

    jd_input_method = st.radio(
        "Job Description Input",
        ["Paste Text", "Upload File"],
    )

    jd_text_input = ""
    if jd_input_method == "Paste Text":
        jd_text_input = st.text_area(
            "Paste Job Description",
            height=300,
            placeholder="Paste the full job description here...",
        )
    else:
        jd_file = st.file_uploader(
            "Upload JD",
            type=["pdf", "docx", "txt"],
            key="jd_upload",
        )

    st.divider()
    st.header("⚙️ Settings")
    max_skills_to_assess = st.slider(
        "Max skills to assess", 3, 10, 5,
        help="Number of top skills to conversationally assess",
    )

    # Reset button
    st.divider()
    if st.button("🔄 Start Over", use_container_width=True):
        for key in ["parsed_resume", "parsed_jd", "resume_text", "jd_text", "current_step"]:
            if key in st.session_state:
                del st.session_state[key]
        st.rerun()


# ──────────────────────────────────────────────
# Header
# ──────────────────────────────────────────────
st.title("🎯 AI-Powered Skill Assessment & Learning Plan Agent")
st.markdown("*Upload a resume and job description to get started.*")

# ──────────────────────────────────────────────
# Progress Indicator
# ──────────────────────────────────────────────
steps = ["📄 Upload", "🔍 Parse", "💬 Assess", "📊 Results"]
step_map = {"upload": 0, "parsed": 1, "assessment": 2, "results": 3}
current_idx = step_map.get(st.session_state.current_step, 0)

cols = st.columns(len(steps))
for i, (col, step_name) in enumerate(zip(cols, steps)):
    if i < current_idx:
        col.success(step_name)
    elif i == current_idx:
        col.info(step_name)
    else:
        col.markdown(f"<div style='padding:8px;text-align:center;color:gray;'>{step_name}</div>", unsafe_allow_html=True)

st.divider()


# ──────────────────────────────────────────────
# Step 1: Upload & Extract Text
# ──────────────────────────────────────────────
if st.session_state.current_step == "upload":

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("📄 Resume")
        if resume_file:
            st.success(f"✅ Uploaded: {resume_file.name}")
            # Extract text
            from app.utils.pdf_parser import extract_text
            try:
                resume_text = extract_text(resume_file, resume_file.name)
                st.session_state.resume_text = resume_text
                with st.expander("Preview extracted text", expanded=False):
                    st.text(resume_text[:2000] + ("..." if len(resume_text) > 2000 else ""))
                st.caption(f"📏 Total characters extracted: {len(resume_text)}")
            except Exception as e:
                st.error(f"Error extracting text: {e}")
        else:
            st.info("👈 Upload a resume in the sidebar")

    with col2:
        st.subheader("📋 Job Description")
        if jd_input_method == "Paste Text" and jd_text_input:
            st.session_state.jd_text = jd_text_input
            st.success(f"✅ JD loaded ({len(jd_text_input)} characters)")
            with st.expander("Preview JD text", expanded=False):
                st.text(jd_text_input[:2000])
        elif jd_input_method == "Upload File" and "jd_file" in dir() and jd_file:
            from app.utils.pdf_parser import extract_text
            try:
                jd_text = extract_text(jd_file, jd_file.name)
                st.session_state.jd_text = jd_text
                st.success(f"✅ JD extracted ({len(jd_text)} characters)")
                with st.expander("Preview JD text", expanded=False):
                    st.text(jd_text[:2000])
            except Exception as e:
                st.error(f"Error extracting JD: {e}")
        else:
            st.info("👈 Provide a job description in the sidebar")

    # Parse button
    st.divider()
    both_ready = st.session_state.resume_text and st.session_state.jd_text

    if both_ready:
        if st.button("🚀 Analyze Resume & Job Description", type="primary", use_container_width=True):
            with st.spinner("🔍 AI is analyzing your resume and job description... This may take 15-30 seconds."):
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
                    st.error(f"❌ Parsing failed: {e}")
                    st.exception(e)
    else:
        st.warning("⚠️ Please upload both a resume AND a job description to proceed.")


# ──────────────────────────────────────────────
# Step 2: Display Parsed Results
# ──────────────────────────────────────────────
elif st.session_state.current_step == "parsed":
    parsed_resume = st.session_state.parsed_resume
    parsed_jd = st.session_state.parsed_jd

    st.subheader("🔍 Parsing Results")

    col1, col2 = st.columns(2)

    # ── Resume Summary ──
    with col1:
        st.markdown("### 👤 Candidate Profile")

        st.markdown(f"""
        | Field | Value |
        |---|---|
        | **Name** | {parsed_resume.candidate_name} |
        | **Current Role** | {parsed_resume.current_role} |
        | **Experience** | {parsed_resume.total_experience_years or 'N/A'} years |
        | **Education** | {', '.join(parsed_resume.education) if parsed_resume.education else 'N/A'} |
        """)

        st.markdown(f"**Summary:** {parsed_resume.summary}")

        st.markdown("#### 🛠️ Skills Found on Resume")
        for skill in parsed_resume.skills:
            level_colors = {
                "novice": "🔴",
                "beginner": "🟠",
                "intermediate": "🟡",
                "advanced": "🟢",
                "expert": "🔵",
            }
            emoji = level_colors.get(skill.claimed_level.value, "⚪")
            exp_str = f" ({skill.years_experience}y)" if skill.years_experience else ""
            st.markdown(f"{emoji} **{skill.name}** — {skill.claimed_level.value.title()}{exp_str}")
            if skill.context:
                st.caption(f"   ↳ {skill.context}")

    # ── JD Summary ──
    with col2:
        st.markdown("### 💼 Job Requirements")

        st.markdown(f"""
        | Field | Value |
        |---|---|
        | **Job Title** | {parsed_jd.job_title} |
        | **Company** | {parsed_jd.company or 'N/A'} |
        | **Seniority** | {parsed_jd.seniority_level} |
        """)

        st.markdown(f"**Summary:** {parsed_jd.summary}")

        st.markdown("#### 📋 Required Skills")
        for skill in parsed_jd.skills:
            req_emoji = {
                "required": "🔴",
                "preferred": "🟡",
                "nice_to_have": "🟢",
            }
            emoji = req_emoji.get(skill.requirement_type.value, "⚪")
            st.markdown(
                f"{emoji} **{skill.name}** — "
                f"Min: {skill.required_level.value.title()} "
                f"({skill.requirement_type.value.replace('_', ' ').title()})"
            )

    # ── Skill Overlap Preview ──
    st.divider()
    st.markdown("### 🔄 Quick Skill Overlap")

    resume_skill_names = {s.name.lower() for s in parsed_resume.skills}
    jd_skill_names = {s.name.lower() for s in parsed_jd.skills}

    matched = resume_skill_names & jd_skill_names
    missing = jd_skill_names - resume_skill_names
    extra = resume_skill_names - jd_skill_names

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("✅ Matched Skills", len(matched))
        for s in sorted(matched):
            st.markdown(f"  ✅ {s.title()}")

    with col2:
        st.metric("❌ Missing Skills", len(missing))
        for s in sorted(missing):
            st.markdown(f"  ❌ {s.title()}")

    with col3:
        st.metric("➕ Extra Skills", len(extra))
        for s in sorted(extra):
            st.markdown(f"  ➕ {s.title()}")

    # Next step button
    st.divider()
    if st.button("💬 Start Skill Assessment", type="primary", use_container_width=True):
        st.session_state.current_step = "assessment"
        st.rerun()


# ──────────────────────────────────────────────
# Step 3: Conversational Assessment
# ──────────────────────────────────────────────
elif st.session_state.current_step == "assessment":
    from app.agents.assessor_agent import AssessmentOrchestrator

    # Initialize orchestrator in session state
    if "orchestrator" not in st.session_state:
        st.session_state.orchestrator = AssessmentOrchestrator(
            parsed_resume=st.session_state.parsed_resume,
            parsed_jd=st.session_state.parsed_jd,
            max_skills=max_skills_to_assess,
        )
        st.session_state.chat_history = []
        st.session_state.awaiting_answer = False
        st.session_state.current_question_obj = None
        st.session_state.assessment_started = False

    orchestrator: AssessmentOrchestrator = st.session_state.orchestrator

    st.subheader("Conversational Skill Assessment")

    # Show skill overview before starting
    if not st.session_state.assessment_started:
        st.markdown("The following skills will be assessed based on the job requirements:")
        st.markdown("")

        overview = orchestrator.get_skill_overview()
        for item in overview:
            req_label = item["requirement"].replace("_", " ").title()
            st.markdown(
                f"**{item['index']}. {item['skill']}** -- "
                f"Required: {item['required_level'].title()} ({req_label}) | "
                f"Claimed: {item['claimed_level'].title()}"
            )

        st.markdown("")
        from app.agents.assessor_agent import MIN_QUESTIONS_PER_SKILL, MAX_QUESTIONS_PER_SKILL
        st.markdown(
            f"You will be asked {MIN_QUESTIONS_PER_SKILL}-{MAX_QUESTIONS_PER_SKILL} "
            f"questions per skill. Questions adapt based on your responses."
        )
        # Need to import the constants
        

        st.markdown("")
        if st.button("Begin Assessment", type="primary", use_container_width=True):
            st.session_state.assessment_started = True

            # Generate first question
            question_obj = orchestrator.get_next_question()
            if question_obj:
                st.session_state.current_question_obj = question_obj
                st.session_state.awaiting_answer = True
                st.session_state.chat_history.append({
                    "role": "assistant",
                    "content": (
                        f"--- Assessing: {question_obj.skill_name} "
                        f"(Skill {orchestrator.current_skill_number}/{orchestrator.total_skills}) ---\n\n"
                        f"Question {question_obj.question_number} "
                        f"[{question_obj.difficulty.value.title()} level]:\n\n"
                        f"{question_obj.question}"
                    ),
                })
            st.rerun()
    else:
        # Progress bar
        total_possible = orchestrator.total_skills
        completed = orchestrator.current_skill_index
        if orchestrator.is_complete:
            completed = total_possible
        st.progress(
            completed / total_possible if total_possible > 0 else 0,
            text=f"Progress: {completed}/{total_possible} skills assessed",
        )

        # Display chat history
        for msg in st.session_state.chat_history:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

        # Handle answer input
        if st.session_state.awaiting_answer and not orchestrator.is_complete:
            answer = st.chat_input("Type your answer here...")

            if answer:
                # Display user message
                st.session_state.chat_history.append({
                    "role": "user",
                    "content": answer,
                })

                # Evaluate answer
                with st.spinner("Evaluating your response..."):
                    response = orchestrator.submit_answer(answer)

                # Show evaluation
                score_bar = "|" * response.score + "." * (5 - response.score)
                eval_msg = (
                    f"Score: [{score_bar}] {response.score}/5\n\n"
                    f"{response.reasoning}"
                )
                st.session_state.chat_history.append({
                    "role": "assistant",
                    "content": eval_msg,
                })

                # Get next question or finish
                question_obj = orchestrator.get_next_question()
                if question_obj:
                    # Check if we moved to a new skill
                    prev_skill = response.skill_name
                    new_skill = question_obj.skill_name

                    if new_skill != prev_skill:
                        st.session_state.chat_history.append({
                            "role": "assistant",
                            "content": (
                                f"--- Assessment of {prev_skill} complete. "
                                f"Moving to: {new_skill} "
                                f"(Skill {orchestrator.current_skill_number}/{orchestrator.total_skills}) ---"
                            ),
                        })

                    st.session_state.current_question_obj = question_obj
                    st.session_state.chat_history.append({
                        "role": "assistant",
                        "content": (
                            f"Question {question_obj.question_number} "
                            f"[{question_obj.difficulty.value.title()} level]:\n\n"
                            f"{question_obj.question}"
                        ),
                    })
                    st.session_state.awaiting_answer = True
                else:
                    # Assessment complete
                    st.session_state.awaiting_answer = False
                    st.session_state.chat_history.append({
                        "role": "assistant",
                        "content": "--- Assessment Complete ---\nAll skills have been assessed. Click below to view your results.",
                    })

                st.rerun()

        # Show results button when complete
        if orchestrator.is_complete:
            st.markdown("")

            # Quick results preview
            results = orchestrator.get_all_results()
            st.markdown("### Assessment Summary")

            for result in results:
                claimed = result.claimed_level.value.title()
                assessed = result.assessed_level.value.title()

                if result.assessed_level.numeric >= result.claimed_level.numeric:
                    indicator = "[PASS]"
                elif result.assessed_level.numeric == result.claimed_level.numeric - 1:
                    indicator = "[CLOSE]"
                else:
                    indicator = "[GAP]"

                st.markdown(
                    f"**{result.skill_name}**: "
                    f"Claimed {claimed} -> Assessed {assessed} "
                    f"{indicator} (Confidence: {result.confidence:.0%})"
                )

            st.markdown("")

            # Store results in session state for next step
            st.session_state.assessment_results = results

            if st.button("View Gap Analysis and Learning Plan", type="primary", use_container_width=True):
                st.session_state.current_step = "results"
                st.rerun()

# ──────────────────────────────────────────────
# Step 4: Results Dashboard
# ──────────────────────────────────────────────
elif st.session_state.current_step == "results":
    from app.agents.gap_analyzer import analyze_gaps
    from app.agents.plan_generator import generate_learning_plan

    # Run gap analysis and plan generation if not already done
    if "gap_analysis" not in st.session_state:
        with st.spinner("Analyzing skill gaps..."):
            st.session_state.gap_analysis = analyze_gaps(
                st.session_state.parsed_resume,
                st.session_state.parsed_jd,
                st.session_state.get("assessment_results", []),
            )

    if "learning_plan" not in st.session_state:
        with st.spinner("Generating personalized learning plan... This may take a minute."):
            st.session_state.learning_plan = generate_learning_plan(
                st.session_state.parsed_resume,
                st.session_state.parsed_jd,
                st.session_state.gap_analysis,
            )

    gap_analysis: GapAnalysisResult = st.session_state.gap_analysis
    learning_plan: PersonalizedLearningPlan = st.session_state.learning_plan

    # Need the schema import for type hints used in display
    from app.models.schemas import GapAnalysisResult, PersonalizedLearningPlan, GapPriority

    st.subheader("Results and Personalized Learning Plan")

    # ── Top-level Metrics ──
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Overall Match", f"{gap_analysis.overall_match_score:.0f}%")
    with col2:
        st.metric("Skill Gaps Found", len(gap_analysis.gaps))
    with col3:
        st.metric("Total Learning Hours", f"{learning_plan.total_estimated_hours:.0f}h")
    with col4:
        st.metric("Estimated Weeks", f"{learning_plan.estimated_weeks:.1f}")

    st.caption(f"(Weeks estimated at 10 hours/week of study)")
    st.markdown(f"**Summary:** {gap_analysis.summary}")

    st.divider()

    # ── Radar Chart ──
    st.markdown("### Skill Comparison")

    import plotly.graph_objects as go

    # Build radar chart data
    assessed_results = st.session_state.get("assessment_results", [])
    assessed_map = {r.skill_name.lower(): r for r in assessed_results}
    resume_map = {s.name.lower(): s for s in st.session_state.parsed_resume.skills}

    skill_names = []
    required_levels = []
    current_levels = []

    for jd_skill in st.session_state.parsed_jd.skills:
        skill_names.append(jd_skill.name)
        required_levels.append(jd_skill.required_level.numeric)

        # Get current level (assessed > claimed > novice)
        assessed = assessed_map.get(jd_skill.name.lower())
        if assessed:
            current_levels.append(assessed.assessed_level.numeric)
        else:
            resume_skill = resume_map.get(jd_skill.name.lower())
            if resume_skill:
                current_levels.append(resume_skill.claimed_level.numeric)
            else:
                current_levels.append(1)

    if skill_names:
        fig = go.Figure()

        fig.add_trace(go.Scatterpolar(
            r=required_levels,
            theta=skill_names,
            fill="toself",
            name="Required Level",
            line=dict(color="#ef4444"),
            opacity=0.3,
        ))

        fig.add_trace(go.Scatterpolar(
            r=current_levels,
            theta=skill_names,
            fill="toself",
            name="Current Level",
            line=dict(color="#22c55e"),
            opacity=0.3,
        ))

        fig.update_layout(
            polar=dict(
                radialaxis=dict(
                    visible=True,
                    range=[0, 5],
                    tickvals=[1, 2, 3, 4, 5],
                    ticktext=["Novice", "Beginner", "Intermediate", "Advanced", "Expert"],
                ),
            ),
            showlegend=True,
            height=500,
            margin=dict(t=30, b=30),
        )

        st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # ── Strengths ──
    if gap_analysis.strengths:
        st.markdown("### Strengths")
        for strength in gap_analysis.strengths:
            st.markdown(f"[PASS] {strength}")

    st.divider()

    # ── Gap Analysis Detail ──
    st.markdown("### Skill Gap Analysis")

    if not gap_analysis.gaps:
        st.success("No skill gaps found. The candidate meets all requirements.")
    else:
        for gap in gap_analysis.gaps:
            priority_labels = {
                GapPriority.CRITICAL: "CRITICAL",
                GapPriority.HIGH: "HIGH",
                GapPriority.MEDIUM: "MEDIUM",
                GapPriority.LOW: "LOW",
            }
            priority_colors = {
                GapPriority.CRITICAL: "red",
                GapPriority.HIGH: "orange",
                GapPriority.MEDIUM: "blue",
                GapPriority.LOW: "green",
            }

            label = priority_labels.get(gap.priority, "UNKNOWN")
            color = priority_colors.get(gap.priority, "gray")

            st.markdown(
                f"**{gap.skill_name}** "
                f":{color}[{label}]"
            )

            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.caption("Current")
                st.markdown(f"**{gap.current_level.value.title()}**")
            with col2:
                st.caption("Required")
                st.markdown(f"**{gap.required_level.value.title()}**")
            with col3:
                st.caption("Gap Size")
                st.markdown(f"**{gap.gap_size} level(s)**")
            with col4:
                st.caption("Est. Hours")
                st.markdown(f"**{gap.estimated_hours:.0f}h**")

            if gap.adjacent_skills:
                st.caption(f"Your related skills that will help: {', '.join(gap.adjacent_skills)}")
            st.caption(f"Learnability: {gap.learnability_score:.0%}")
            st.markdown("---")

    st.divider()

    # ── Learning Plan ──
    st.markdown("### Personalized Learning Plan")

    # Quick wins and long-term goals
    col1, col2 = st.columns(2)
    with col1:
        if learning_plan.quick_wins:
            st.markdown("**Quick Wins (under 20 hours):**")
            for qw in learning_plan.quick_wins:
                st.markdown(f"- {qw}")
        else:
            st.markdown("**No quick wins identified.**")

    with col2:
        if learning_plan.long_term_goals:
            st.markdown("**Long-term Goals (over 60 hours):**")
            for lt in learning_plan.long_term_goals:
                st.markdown(f"- {lt}")
        else:
            st.markdown("**No long-term goals identified.**")

    st.divider()

    # Detailed learning paths
    for path in learning_plan.learning_paths:
        priority_labels = {
            GapPriority.CRITICAL: "CRITICAL",
            GapPriority.HIGH: "HIGH",
            GapPriority.MEDIUM: "MEDIUM",
            GapPriority.LOW: "LOW",
        }
        label = priority_labels.get(path.priority, "")

        with st.expander(
            f"{path.skill_name} -- {path.current_level.value.title()} to "
            f"{path.target_level.value.title()} | {path.total_estimated_hours:.0f}h | {label}",
            expanded=(path.priority in [GapPriority.CRITICAL, GapPriority.HIGH]),
        ):
            st.markdown(f"**Why learn this:** {path.why_learn}")

            if path.leverage_existing:
                st.markdown("**Your advantages:**")
                for adv in path.leverage_existing:
                    st.markdown(f"- {adv}")

            for i, milestone in enumerate(path.milestones, 1):
                st.markdown(f"#### Milestone {i}: {milestone.title}")
                st.markdown(f"{milestone.description}")
                st.caption(f"Target: {milestone.target_level.value.title()} | Estimated: {milestone.estimated_hours:.0f} hours")

                if milestone.resources:
                    st.markdown("**Resources:**")
                    for r in milestone.resources:
                        free_tag = "FREE" if r.is_free else "PAID"
                        if r.url:
                            st.markdown(
                                f"- [{r.title}]({r.url}) "
                                f"({r.resource_type}) [{free_tag}] ~{r.estimated_hours:.0f}h"
                            )
                        else:
                            st.markdown(
                                f"- {r.title} "
                                f"({r.resource_type}) [{free_tag}] ~{r.estimated_hours:.0f}h"
                            )

                if milestone.practice_project:
                    st.markdown(f"**Practice Project:** {milestone.practice_project}")

                st.markdown("")

    # ── Strengths Summary ──
    if learning_plan.strengths_summary:
        st.divider()
        st.markdown(f"### Strengths Summary")
        st.markdown(learning_plan.strengths_summary)