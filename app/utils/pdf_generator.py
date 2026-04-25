"""
PDF generator for the personalized learning plan report.
Uses fpdf2 to create a clean, professional PDF.
"""

from fpdf import FPDF
from app.models.schemas import (
    PersonalizedLearningPlan,
    GapAnalysisResult,
    SkillAssessmentResult,
    GapPriority,
    ProficiencyLevel,
)


class LearningPlanPDF(FPDF):
    """Custom PDF class with header/footer for the learning plan report."""

    def __init__(self, candidate_name: str = "", target_role: str = ""):
        super().__init__()
        self.candidate_name = candidate_name
        self.target_role = target_role

    def header(self):
        self.set_font("Helvetica", "B", 10)
        self.set_text_color(100, 100, 100)
        self.cell(0, 8, "Skill Assessment & Learning Plan Report", align="L")
        self.cell(0, 8, self.candidate_name, align="R", new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(200, 200, 200)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(150, 150, 150)
        self.cell(0, 10, f"Page {self.page_no()}/{{nb}}", align="C")

    def section_title(self, title: str):
        self.set_font("Helvetica", "B", 14)
        self.set_text_color(30, 30, 30)
        self.ln(4)
        self.cell(0, 10, title, new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(50, 120, 200)
        self.set_line_width(0.5)
        self.line(10, self.get_y(), 80, self.get_y())
        self.ln(4)

    def sub_title(self, title: str):
        self.set_font("Helvetica", "B", 11)
        self.set_text_color(50, 50, 50)
        self.cell(0, 8, title, new_x="LMARGIN", new_y="NEXT")
        self.ln(1)

    def body_text(self, text: str):
        self.set_font("Helvetica", "", 10)
        self.set_text_color(60, 60, 60)
        self.multi_cell(0, 5.5, text)
        self.ln(2)

    def key_value(self, key: str, value: str):
        self.set_font("Helvetica", "B", 10)
        self.set_text_color(60, 60, 60)
        self.cell(55, 6, f"{key}:")
        self.set_font("Helvetica", "", 10)
        self.cell(0, 6, value, new_x="LMARGIN", new_y="NEXT")

    def priority_badge(self, priority: GapPriority) -> str:
        mapping = {
            GapPriority.CRITICAL: "CRITICAL",
            GapPriority.HIGH: "HIGH",
            GapPriority.MEDIUM: "MEDIUM",
            GapPriority.LOW: "LOW",
        }
        return mapping.get(priority, "UNKNOWN")

    def level_text(self, level: ProficiencyLevel) -> str:
        return level.value.title()


def generate_pdf(
    learning_plan: PersonalizedLearningPlan,
    gap_analysis: GapAnalysisResult,
    assessment_results: list[SkillAssessmentResult] = None,
) -> bytes:
    """
    Generate a PDF report of the complete assessment and learning plan.
    Returns the PDF as bytes.
    """
    pdf = LearningPlanPDF(
        candidate_name=learning_plan.candidate_name,
        target_role=learning_plan.target_role,
    )
    pdf.alias_nb_pages()
    pdf.set_auto_page_break(auto=True, margin=20)

    # ── Page 1: Executive Summary ──
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 22)
    pdf.set_text_color(30, 30, 30)
    pdf.cell(0, 15, "Skill Assessment Report", new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("Helvetica", "", 12)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(
        0, 8,
        f"Personalized Learning Plan for {learning_plan.target_role}",
        new_x="LMARGIN", new_y="NEXT",
    )
    pdf.ln(8)

    # Key Metrics
    pdf.section_title("Executive Summary")

    pdf.key_value("Candidate", learning_plan.candidate_name)
    pdf.key_value("Target Role", learning_plan.target_role)
    pdf.key_value("Overall Match", f"{learning_plan.overall_match_score:.0f}%")
    pdf.key_value("Skill Gaps Found", str(len(gap_analysis.gaps)))
    pdf.key_value("Total Learning Hours", f"{learning_plan.total_estimated_hours:.0f} hours")
    pdf.key_value(
        "Estimated Timeline",
        f"{learning_plan.estimated_weeks:.1f} weeks (at 10 hrs/week)",
    )
    pdf.ln(4)

    pdf.body_text(gap_analysis.summary)

    # Strengths
    if gap_analysis.strengths:
        pdf.section_title("Strengths")
        for strength in gap_analysis.strengths:
            pdf.body_text(f"  +  {strength}")

    # Quick Wins
    if learning_plan.quick_wins:
        pdf.section_title("Quick Wins (Under 20 Hours)")
        for qw in learning_plan.quick_wins:
            pdf.body_text(f"  >  {qw}")

    # ── Assessment Results ──
    if assessment_results:
        pdf.add_page()
        pdf.section_title("Assessment Results")

        for result in assessment_results:
            claimed = pdf.level_text(result.claimed_level)
            assessed = pdf.level_text(result.assessed_level)

            indicator = ""
            if result.assessed_level.numeric >= result.claimed_level.numeric:
                indicator = "[PASS]"
            elif result.assessed_level.numeric == result.claimed_level.numeric - 1:
                indicator = "[CLOSE]"
            else:
                indicator = "[GAP]"

            pdf.sub_title(f"{result.skill_name} {indicator}")
            pdf.key_value("Claimed Level", claimed)
            pdf.key_value("Assessed Level", assessed)
            pdf.key_value("Confidence", f"{result.confidence:.0%}")
            pdf.key_value("Questions Asked", str(result.questions_asked))

            if result.summary:
                pdf.body_text(result.summary)

            # Show Q&A details
            for resp in result.responses:
                pdf.set_font("Helvetica", "I", 9)
                pdf.set_text_color(80, 80, 80)
                pdf.multi_cell(0, 5, f"Q [{resp.difficulty.value.title()}]: {resp.question}")
                pdf.set_font("Helvetica", "", 9)
                pdf.multi_cell(0, 5, f"A: {resp.candidate_answer[:200]}")
                pdf.set_text_color(50, 120, 50)
                pdf.cell(0, 5, f"Score: {resp.score}/5 -- {resp.reasoning}", new_x="LMARGIN", new_y="NEXT")
                pdf.set_text_color(60, 60, 60)
                pdf.ln(3)

            pdf.ln(4)

    # ── Gap Analysis Detail ──
    if gap_analysis.gaps:
        pdf.add_page()
        pdf.section_title("Gap Analysis")

        for gap in gap_analysis.gaps:
            priority = pdf.priority_badge(gap.priority)
            pdf.sub_title(f"{gap.skill_name} [{priority}]")
            pdf.key_value("Current Level", pdf.level_text(gap.current_level))
            pdf.key_value("Required Level", pdf.level_text(gap.required_level))
            pdf.key_value("Gap Size", f"{gap.gap_size} level(s)")
            pdf.key_value("Estimated Hours", f"{gap.estimated_hours:.0f}")
            pdf.key_value("Learnability", f"{gap.learnability_score:.0%}")

            if gap.adjacent_skills:
                pdf.key_value("Related Skills You Have", ", ".join(gap.adjacent_skills))

            pdf.ln(4)

    # ── Learning Paths ──
    for path in learning_plan.learning_paths:
        pdf.add_page()
        priority = pdf.priority_badge(path.priority)
        pdf.section_title(f"Learning Path: {path.skill_name}")

        pdf.key_value(
            "Journey",
            f"{pdf.level_text(path.current_level)} --> {pdf.level_text(path.target_level)}",
        )
        pdf.key_value("Priority", priority)
        pdf.key_value("Total Hours", f"{path.total_estimated_hours:.0f}")
        pdf.ln(2)

        if path.why_learn:
            pdf.sub_title("Why Learn This")
            pdf.body_text(path.why_learn)

        if path.leverage_existing:
            pdf.sub_title("Your Advantages")
            for adv in path.leverage_existing:
                pdf.body_text(f"  >  {adv}")

        for i, milestone in enumerate(path.milestones, 1):
            pdf.ln(2)
            pdf.sub_title(f"Milestone {i}: {milestone.title}")
            pdf.body_text(milestone.description)
            pdf.key_value("Target Level", pdf.level_text(milestone.target_level))
            pdf.key_value("Estimated Hours", f"{milestone.estimated_hours:.0f}")

            if milestone.resources:
                pdf.set_font("Helvetica", "B", 10)
                pdf.set_text_color(60, 60, 60)
                pdf.cell(0, 6, "Resources:", new_x="LMARGIN", new_y="NEXT")

                for r in milestone.resources:
                    pdf.set_font("Helvetica", "", 9)
                    free_tag = "FREE" if r.is_free else "PAID"
                    line = f"  - {r.title} ({r.resource_type}) [{free_tag}]"
                    if r.estimated_hours:
                        line += f" ~{r.estimated_hours:.0f}h"
                    pdf.cell(0, 5.5, line, new_x="LMARGIN", new_y="NEXT")

                    if r.url:
                        pdf.set_text_color(50, 100, 200)
                        pdf.set_font("Helvetica", "U", 8)
                        pdf.cell(0, 4.5, f"    {r.url}", link=r.url, new_x="LMARGIN", new_y="NEXT")
                        pdf.set_text_color(60, 60, 60)

            if milestone.practice_project:
                pdf.ln(2)
                pdf.set_font("Helvetica", "B", 9)
                pdf.cell(0, 5.5, "Practice Project:", new_x="LMARGIN", new_y="NEXT")
                pdf.set_font("Helvetica", "", 9)
                pdf.multi_cell(0, 5, f"  {milestone.practice_project}")

    # ── Final Page ──
    pdf.add_page()
    pdf.section_title("Next Steps")

    pdf.body_text("1. Start with the Quick Wins to build momentum and confidence.")
    pdf.body_text("2. Tackle CRITICAL and HIGH priority gaps first.")
    pdf.body_text("3. Dedicate consistent daily time (even 1-2 hours) rather than marathon sessions.")
    pdf.body_text("4. Build projects at each milestone to solidify your learning.")
    pdf.body_text("5. Re-assess after completing each learning path to track progress.")
    pdf.ln(6)

    if learning_plan.strengths_summary:
        pdf.section_title("Remember Your Strengths")
        pdf.body_text(learning_plan.strengths_summary)

    pdf.ln(10)
    pdf.set_font("Helvetica", "I", 9)
    pdf.set_text_color(150, 150, 150)
    pdf.cell(
        0, 6,
        "Generated by AI Skill Assessment Agent",
        align="C",
    )

    return pdf.output()