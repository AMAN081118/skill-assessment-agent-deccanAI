"""
Assessor Agent -- Conversational skill assessment engine.

Takes parsed resume + JD data, identifies skills to assess,
and conducts an adaptive Q&A session for each skill.
Uses Groq (GPT-OSS 120B) for fast chat responses.
"""

import json
from langchain_core.messages import SystemMessage, HumanMessage
from app.utils.llm_client import call_with_retry
from app.models.schemas import (
    ParsedJD,
    ParsedResume,
    JDSkill,
    ResumeSkill,
    ProficiencyLevel,
    SkillAssessmentResult,
    AssessmentResponse,
    AssessmentQuestion,
)
from app.models.scoring import (
    PROFICIENCY_RUBRICS,
    get_starting_difficulty,
    get_next_difficulty,
    determine_final_level,
)


# ──────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────

MAX_QUESTIONS_PER_SKILL = 3
MIN_QUESTIONS_PER_SKILL = 2


# ──────────────────────────────────────────────
# Skill Selection
# ──────────────────────────────────────────────

def select_skills_to_assess(
    parsed_resume: ParsedResume,
    parsed_jd: ParsedJD,
    max_skills: int = 5,
) -> list[dict]:
    """
    Select which skills to assess, prioritized by importance.

    Returns a list of dicts with:
    - jd_skill: the JDSkill object
    - resume_skill: matching ResumeSkill or None (if candidate claims it)
    - reason: why this skill was selected

    Priority order:
    1. Required skills where candidate claims proficiency (need to verify)
    2. Required skills missing from resume (need to check if they know it)
    3. Preferred skills where candidate claims proficiency
    """
    resume_skill_map = {}
    for rs in parsed_resume.skills:
        resume_skill_map[rs.name.lower().strip()] = rs
        for alias in rs.aliases:
            resume_skill_map[alias.lower().strip()] = rs

    skills_to_assess = []

    for jd_skill in parsed_jd.skills:
        jd_name = jd_skill.name.lower().strip()

        # Find matching resume skill
        matched_resume_skill = resume_skill_map.get(jd_name)

        # Also try partial matching
        if not matched_resume_skill:
            for key, rs in resume_skill_map.items():
                if jd_name in key or key in jd_name:
                    matched_resume_skill = rs
                    break

        if matched_resume_skill:
            reason = (
                f"Claimed as {matched_resume_skill.claimed_level.value} on resume, "
                f"JD requires {jd_skill.required_level.value} "
                f"({jd_skill.requirement_type.value})"
            )
        else:
            reason = (
                f"Not found on resume, "
                f"JD requires {jd_skill.required_level.value} "
                f"({jd_skill.requirement_type.value})"
            )

        # Calculate priority score
        priority = _calculate_assessment_priority(jd_skill, matched_resume_skill)

        skills_to_assess.append({
            "jd_skill": jd_skill,
            "resume_skill": matched_resume_skill,
            "reason": reason,
            "priority": priority,
        })

    # Sort by priority (highest first) and take top N
    skills_to_assess.sort(key=lambda x: x["priority"], reverse=True)
    return skills_to_assess[:max_skills]


def _calculate_assessment_priority(
    jd_skill: JDSkill,
    resume_skill: ResumeSkill | None,
) -> float:
    """
    Calculate how important it is to assess this skill.
    Higher score = more important to assess.
    """
    score = 0.0

    # Requirement type weight
    req_weights = {
        "required": 3.0,
        "preferred": 2.0,
        "nice_to_have": 1.0,
    }
    score += req_weights.get(jd_skill.requirement_type.value, 1.0)

    # Required level weight (higher required level = more important to verify)
    score += jd_skill.required_level.numeric * 0.5

    # Claimed on resume = needs verification
    if resume_skill:
        score += 1.5
        # Bigger gap between claimed and required = more important
        gap = abs(jd_skill.required_level.numeric - resume_skill.claimed_level.numeric)
        score += gap * 0.3
    else:
        # Not on resume but required = important to check
        if jd_skill.requirement_type.value == "required":
            score += 1.0

    return score


# ──────────────────────────────────────────────
# Question Generation
# ──────────────────────────────────────────────

QUESTION_GENERATION_PROMPT = """You are a technical interviewer assessing a candidate's proficiency in {skill_name}.

The candidate's background: {context}

Generate exactly ONE technical question at the {difficulty} level.

Difficulty guidelines:
- novice: Ask to define or explain a basic concept
- beginner: Ask about simple application or when to use something
- intermediate: Ask about debugging, design choices, or trade-offs
- advanced: Ask about architecture, optimization, or internal workings
- expert: Ask about system design, edge cases, or implementing from scratch

Rules:
- The question must be specific and answerable in 2-4 sentences
- Do not ask multi-part questions
- Do not include the answer
- Make it practical, not textbook trivia
- Tailor it to the {domain} domain

Respond with ONLY the question text. Nothing else."""


def generate_question(
    skill_name: str,
    difficulty: ProficiencyLevel,
    context: str = "",
    domain: str = "software engineering",
    previous_questions: list[str] = None,
) -> str:
    """
    Generate a single assessment question for a skill at a given difficulty.
    """
    prev_q_text = ""
    if previous_questions:
        prev_q_text = "\n\nDo NOT repeat these previously asked questions:\n"
        for i, q in enumerate(previous_questions, 1):
            prev_q_text += f"{i}. {q}\n"

    prompt = QUESTION_GENERATION_PROMPT.format(
        skill_name=skill_name,
        difficulty=difficulty.value,
        context=context or "No specific context provided",
        domain=domain,
    ) + prev_q_text

    messages = [
        SystemMessage(content=prompt),
        HumanMessage(content=f"Generate a {difficulty.value}-level question for {skill_name}."),
    ]

    try:
        from app.utils.llm_client import call_with_retry
        return call_with_retry(messages, llm_type="assessment").strip()
    except Exception:
        return f"Explain your experience with {skill_name} and how you have used it in your projects."



# ──────────────────────────────────────────────
# Answer Evaluation
# ──────────────────────────────────────────────

EVALUATION_PROMPT = """You are a technical interviewer evaluating a candidate's answer.

Skill being assessed: {skill_name}
Question difficulty: {difficulty}
Question asked: {question}
Candidate's answer: {answer}

Evaluate the answer and provide:
1. score: integer from 1 to 5
   - 1: Completely wrong or no understanding shown
   - 2: Vaguely correct but major gaps or misconceptions
   - 3: Mostly correct, demonstrates working knowledge at this level
   - 4: Correct with good depth, shows solid understanding
   - 5: Excellent, demonstrates mastery beyond this difficulty level

2. reasoning: Brief explanation (1-2 sentences) of why you gave this score

Respond with ONLY valid JSON:
{{"score": <int>, "reasoning": "<string>"}}"""


def evaluate_answer(
    skill_name: str,
    question: str,
    answer: str,
    difficulty: ProficiencyLevel,
) -> dict:
    """
    Evaluate a candidate's answer to an assessment question.
    Returns dict with 'score' (1-5) and 'reasoning'.
    """
    prompt = EVALUATION_PROMPT.format(
        skill_name=skill_name,
        difficulty=difficulty.value,
        question=question,
        answer=answer,
    )

    messages = [
        SystemMessage(content=prompt),
        HumanMessage(content="Evaluate this answer."),
    ]

    try:
        from app.utils.llm_client import call_with_retry
        raw = call_with_retry(messages, llm_type="assessment").strip()
    except Exception:
        return {"score": 3, "reasoning": "Could not evaluate - defaulting to neutral score."}

    try:
        cleaned = raw
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        if cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

        data = json.loads(cleaned)
        score = max(1, min(5, int(data.get("score", 3))))
        reasoning = data.get("reasoning", "No reasoning provided.")
        return {"score": score, "reasoning": reasoning}
    except (json.JSONDecodeError, ValueError):
        return {"score": 3, "reasoning": "Evaluation parsing failed - defaulting to neutral score."}



# ──────────────────────────────────────────────
# Assessment Session Manager
# ──────────────────────────────────────────────

class SkillAssessmentSession:
    """
    Manages the assessment session for a single skill.
    Tracks state across multiple questions.
    """

    def __init__(
        self,
        skill_name: str,
        claimed_level: ProficiencyLevel,
        jd_required_level: ProficiencyLevel,
        context: str = "",
    ):
        self.skill_name = skill_name
        self.claimed_level = claimed_level
        self.jd_required_level = jd_required_level
        self.context = context

        # State
        self.current_difficulty = get_starting_difficulty(claimed_level)
        self.questions_asked: list[str] = []
        self.responses: list[AssessmentResponse] = []
        self.is_complete = False
        self.current_question: str | None = None
        self.question_number = 0

    def get_next_question(self) -> AssessmentQuestion | None:
        """Generate the next question or return None if assessment is complete."""
        if self.is_complete or self.question_number >= MAX_QUESTIONS_PER_SKILL:
            self.is_complete = True
            return None

        self.question_number += 1

        question_text = generate_question(
            skill_name=self.skill_name,
            difficulty=self.current_difficulty,
            context=self.context,
            previous_questions=self.questions_asked,
        )

        self.current_question = question_text
        self.questions_asked.append(question_text)

        return AssessmentQuestion(
            skill_name=self.skill_name,
            question=question_text,
            difficulty=self.current_difficulty,
            question_number=self.question_number,
        )

    def submit_answer(self, answer: str) -> AssessmentResponse:
        """
        Submit an answer to the current question.
        Evaluates the answer, adjusts difficulty, and returns the response.
        """
        if not self.current_question:
            raise ValueError("No active question to answer.")

        # Evaluate
        eval_result = evaluate_answer(
            skill_name=self.skill_name,
            question=self.current_question,
            answer=answer,
            difficulty=self.current_difficulty,
        )

        response = AssessmentResponse(
            skill_name=self.skill_name,
            question=self.current_question,
            candidate_answer=answer,
            score=eval_result["score"],
            reasoning=eval_result["reasoning"],
            difficulty=self.current_difficulty,
        )
        self.responses.append(response)

        # Determine next difficulty
        if self.question_number >= MAX_QUESTIONS_PER_SKILL:
            self.is_complete = True
        elif self.question_number >= MIN_QUESTIONS_PER_SKILL:
            next_diff = get_next_difficulty(self.current_difficulty, eval_result["score"])
            if next_diff is None:
                self.is_complete = True
            elif next_diff == self.current_difficulty and eval_result["score"] >= 3:
                # Confirmed at this level, no need for more
                self.is_complete = True
            else:
                self.current_difficulty = next_diff
        else:
            next_diff = get_next_difficulty(self.current_difficulty, eval_result["score"])
            if next_diff is not None:
                self.current_difficulty = next_diff

        self.current_question = None
        return response

    def get_result(self) -> SkillAssessmentResult:
        """Get the final assessment result for this skill."""
        if not self.responses:
            return SkillAssessmentResult(
                skill_name=self.skill_name,
                claimed_level=self.claimed_level,
                assessed_level=ProficiencyLevel.NOVICE,
                confidence=0.0,
                questions_asked=0,
                responses=[],
                summary="No assessment conducted.",
            )

        # Determine final level
        response_dicts = [
            {"difficulty": r.difficulty, "score": r.score}
            for r in self.responses
        ]
        assessed_level = determine_final_level(response_dicts)

        # Calculate confidence based on consistency and number of questions
        confidence = self._calculate_confidence()

        # Generate summary
        summary = self._generate_summary(assessed_level)

        return SkillAssessmentResult(
            skill_name=self.skill_name,
            claimed_level=self.claimed_level,
            assessed_level=assessed_level,
            confidence=confidence,
            questions_asked=len(self.responses),
            responses=self.responses,
            summary=summary,
        )

    def _calculate_confidence(self) -> float:
        """
        Calculate confidence in the assessment result.
        Based on number of questions and score consistency.
        """
        if not self.responses:
            return 0.0

        # Base confidence from number of questions
        base = min(len(self.responses) / MAX_QUESTIONS_PER_SKILL, 1.0) * 0.6

        # Consistency bonus: if scores don't wildly fluctuate
        scores = [r.score for r in self.responses]
        if len(scores) >= 2:
            variance = sum((s - sum(scores) / len(scores)) ** 2 for s in scores) / len(scores)
            # Lower variance = higher consistency = higher confidence
            consistency = max(0, 1 - (variance / 4)) * 0.4
        else:
            consistency = 0.2

        return round(min(base + consistency, 1.0), 2)

    def _generate_summary(self, assessed_level: ProficiencyLevel) -> str:
        """Generate a brief text summary of the assessment."""
        avg_score = sum(r.score for r in self.responses) / len(self.responses)

        comparison = ""
        if assessed_level.numeric > self.claimed_level.numeric:
            comparison = "performed above their claimed level"
        elif assessed_level.numeric < self.claimed_level.numeric:
            comparison = "performed below their claimed level"
        else:
            comparison = "performed at their claimed level"

        return (
            f"Assessed at {assessed_level.value} level for {self.skill_name} "
            f"(claimed {self.claimed_level.value}). "
            f"Candidate {comparison} with an average score of {avg_score:.1f}/5 "
            f"across {len(self.responses)} questions."
        )


# ──────────────────────────────────────────────
# Full Assessment Orchestrator
# ──────────────────────────────────────────────

class AssessmentOrchestrator:
    """
    Manages the full assessment flow across multiple skills.
    Designed to work with Streamlit's session state for the chat UI.
    """

    def __init__(
        self,
        parsed_resume: ParsedResume,
        parsed_jd: ParsedJD,
        max_skills: int = 5,
    ):
        self.parsed_resume = parsed_resume
        self.parsed_jd = parsed_jd
        self.max_skills = max_skills

        # Select skills to assess
        self.skills_to_assess = select_skills_to_assess(
            parsed_resume, parsed_jd, max_skills
        )

        # Create sessions for each skill
        self.sessions: list[SkillAssessmentSession] = []
        for item in self.skills_to_assess:
            jd_skill: JDSkill = item["jd_skill"]
            resume_skill: ResumeSkill | None = item["resume_skill"]

            claimed = resume_skill.claimed_level if resume_skill else ProficiencyLevel.NOVICE
            context = resume_skill.context if resume_skill else ""

            session = SkillAssessmentSession(
                skill_name=jd_skill.name,
                claimed_level=claimed,
                jd_required_level=jd_skill.required_level,
                context=context,
            )
            self.sessions.append(session)

        # Tracking
        self.current_skill_index = 0
        self.is_complete = False
        self.results: list[SkillAssessmentResult] = []

    @property
    def current_session(self) -> SkillAssessmentSession | None:
        """Get the current active assessment session."""
        if self.current_skill_index >= len(self.sessions):
            return None
        return self.sessions[self.current_skill_index]

    @property
    def total_skills(self) -> int:
        return len(self.sessions)

    @property
    def current_skill_number(self) -> int:
        return self.current_skill_index + 1

    def get_next_question(self) -> AssessmentQuestion | None:
        """
        Get the next question in the assessment.
        Automatically advances to next skill when current is done.
        """
        while self.current_skill_index < len(self.sessions):
            session = self.sessions[self.current_skill_index]

            if session.is_complete:
                # Collect result and move to next skill
                self.results.append(session.get_result())
                self.current_skill_index += 1
                continue

            question = session.get_next_question()
            if question is None:
                # Skill assessment complete
                self.results.append(session.get_result())
                self.current_skill_index += 1
                continue

            return question

        # All skills assessed
        self.is_complete = True
        return None

    def submit_answer(self, answer: str) -> AssessmentResponse:
        """Submit answer to the current question."""
        session = self.current_session
        if session is None:
            raise ValueError("No active assessment session.")
        return session.submit_answer(answer)

    def get_all_results(self) -> list[SkillAssessmentResult]:
        """Get results for all assessed skills."""
        # Collect any remaining results
        for i in range(len(self.results), len(self.sessions)):
            self.results.append(self.sessions[i].get_result())
        return self.results

    def get_skill_overview(self) -> list[dict]:
        """
        Get an overview of skills being assessed with their selection reason.
        Useful for displaying to the user before assessment starts.
        """
        overview = []
        for i, item in enumerate(self.skills_to_assess):
            jd_skill = item["jd_skill"]
            resume_skill = item["resume_skill"]
            overview.append({
                "index": i + 1,
                "skill": jd_skill.name,
                "required_level": jd_skill.required_level.value,
                "claimed_level": resume_skill.claimed_level.value if resume_skill else "not listed",
                "requirement": jd_skill.requirement_type.value,
                "reason": item["reason"],
            })
        return overview