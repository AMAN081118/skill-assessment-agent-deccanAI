from fpdf import FPDF


class PDF(FPDF):
    def header(self):
        self.set_font("Arial", "B", 12)
        self.cell(0, 10, "Skill Assessment Report", ln=True)
        self.ln(2)


def clean_text(text: str, max_len=500):
    if not text:
        return ""

    text = str(text)[:max_len]
    text = text.encode("latin-1", "replace").decode("latin-1")
    text = text.replace("\n", " ").replace("\r", " ")

    result = ""
    chunk = ""

    for ch in text:
        chunk += ch
        if len(chunk) >= 80:
            result += chunk + " "
            chunk = ""

    result += chunk
    return result


def generate_pdf(learning_plan, gap_analysis, assessment_results=None):
    pdf = PDF()
    pdf.set_auto_page_break(auto=True, margin=10)
    pdf.add_page()

    pdf.set_font("Arial", size=11)

    # Basic Info
    pdf.cell(0, 8, f"Candidate: {learning_plan.candidate_name}", ln=True)
    pdf.cell(0, 8, f"Target Role: {learning_plan.target_role}", ln=True)
    pdf.cell(0, 8, f"Match: {int(learning_plan.overall_match_score)}%", ln=True)
    pdf.ln(5)

    # Summary
    pdf.set_font("Arial", "B", 12)
    pdf.cell(0, 8, "Summary", ln=True)
    pdf.set_font("Arial", size=11)
    pdf.multi_cell(0, 6, clean_text(gap_analysis.summary))

    # Gaps
    if gap_analysis.gaps:
        pdf.ln(4)
        pdf.set_font("Arial", "B", 12)
        pdf.cell(0, 8, "Gap Analysis", ln=True)

        pdf.set_font("Arial", size=11)
        for g in gap_analysis.gaps:
            pdf.multi_cell(
                0,
                6,
                f"{g.skill_name} [{g.priority.name}] - "
                f"{g.current_level.value} → {g.required_level.value} "
                f"(~{int(g.estimated_hours)} hrs)"
            )
            pdf.ln(1)

    # Assessments
    if assessment_results:
        pdf.ln(4)
        pdf.set_font("Arial", "B", 12)
        pdf.cell(0, 8, "Assessment", ln=True)

        pdf.set_font("Arial", size=10)

        for a in assessment_results:
            pdf.set_font("Arial", "B", 11)
            pdf.cell(0, 6, a.skill_name, ln=True)

            pdf.set_font("Arial", size=10)
            pdf.cell(0, 5, f"Confidence: {int(a.confidence*100)}%", ln=True)

            for r in a.responses:
                pdf.multi_cell(0, 5, f"Q: {clean_text(r.question)}")
                pdf.multi_cell(0, 5, f"A: {clean_text(r.candidate_answer)}")
                pdf.cell(0, 5, f"Score: {r.score}/5", ln=True)
                pdf.ln(2)

    return pdf.output(dest="S").encode("latin-1")