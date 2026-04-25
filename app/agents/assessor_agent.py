"""
Assessor Agent -- Conversational skill assessment engine.
Uses pre-generated question banks for speed and efficiency.
"""

import json
from langchain_core.messages import SystemMessage, HumanMessage
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
    resume_skill_map = {}
    for rs in parsed_resume.skills:
        resume_skill_map[rs.name.lower().strip()] = rs
        for alias in rs.aliases:
            resume_skill_map[alias.lower().strip()] = rs

    skills_to_assess = []

    for jd_skill in parsed_jd.skills:
        jd_name = jd_skill.name.lower().strip()
        matched_resume_skill = resume_skill_map.get(jd_name)

        if not matched_resume_skill:
            for key, rs in resume_skill_map.items():
                if jd_name in key or key in jd_name:
                    matched_resume_skill = rs
                    break

        if matched_resume_skill:
            reason = (
                f"Claimed as {matched_resume_skill.claimed_level.value} on resume, "
                f"JD requires {jd_skill.required_level.value}"
            )
        else:
            reason = f"Not found on resume, JD requires {jd_skill.required_level.value}"

        priority = _calculate_assessment_priority(jd_skill, matched_resume_skill)
        
        skills_to_assess.append({
            "jd_skill": jd_skill,
            "resume_skill": matched_resume_skill,
            "reason": reason,
            "priority": priority,
        })

    skills_to_assess.sort(key=lambda x: x["priority"], reverse=True)
    return skills_to_assess[:max_skills]


def _calculate_assessment_priority(jd_skill: JDSkill, resume_skill: ResumeSkill | None) -> float:
    req_weights = {
        "required": 3.0,
        "preferred": 2.0,
        "nice_to_have": 1.0
    }
    score = req_weights.get(jd_skill.requirement_type.value, 1.0)
    score += jd_skill.required_level.numeric * 0.5
    
    if resume_skill:
        score += 1.5
        gap = abs(jd_skill.required_level.numeric - resume_skill.claimed_level.numeric)
        score += gap * 0.3
    elif jd_skill.requirement_type.value == "required":
        score += 1.0
        
    return score


# ──────────────────────────────────────────────
# Question Generation (Batched)
# ──────────────────────────────────────────────

QUESTION_BANK_PROMPT = """You are a technical interviewer assessing a candidate's proficiency in {skill_name}.
The candidate's background: {context}

Generate a bank of 5 technical questions tailored to the {domain} domain.
Provide exactly:
- 2 Beginner questions (simple application, when to use)
- 2 Intermediate questions (debugging, design choices, trade-offs)
- 1 Advanced question (architecture, internal workings, optimization)

Rules:
- Questions must be specific and answerable in 2-4 sentences.
- Do not ask multi-part questions.
- Do not include answers.
- Make them practical, not textbook trivia.

Respond with ONLY valid JSON matching this schema exactly:
{{
  "beginner": ["string", "string"],
  "intermediate": ["string", "string"],
  "advanced": ["string"]
}}"""

def generate_question_bank(
    skill_name: str, 
    context: str = "", 
    domain: str = "software engineering"
) -> dict[str, list[str]]:
    
    prompt = QUESTION_BANK_PROMPT.format(
        skill_name=skill_name, 
        context=context or "None", 
        domain=domain
    )
    
    messages = [
        SystemMessage(content=prompt), 
        HumanMessage(content=f"Generate the question bank for {skill_name}. Return ONLY JSON.")
    ]
    
    default_bank = {
        "beginner": [
            f"Explain the basic concepts of {skill_name}.", 
            f"What is a simple task where you applied {skill_name}?"
        ],
        "intermediate": [
            f"Walk me through debugging an issue with {skill_name}.", 
            f"What are the trade-offs of {skill_name}?"
        ],
        "advanced": [
            f"How would you architect a scalable system using {skill_name}?"
        ]
    }

    try:
        from app.utils.llm_client import call_with_retry
        raw = call_with_retry(messages, llm_type="assessment").strip()
        
        if raw.startswith("```json"): 
            raw = raw[7:]
        elif raw.startswith("```"): 
            raw = raw[3:]
        if raw.endswith("```"): 
            raw = raw[:-3]
        
        bank = json.loads(raw.strip())
        
        return {
            "beginner": (bank.get("beginner", []) + default_bank["beginner"])[:2],
            "intermediate": (bank.get("intermediate", []) + default_bank["intermediate"])[:2],
            "advanced": (bank.get("advanced", []) + default_bank["advanced"])[:2]
        }
    except Exception as e:
        print(f"Bank generation failed for {skill_name}: {e}")
        return default_bank


# ──────────────────────────────────────────────
# Answer Evaluation
# ──────────────────────────────────────────────

EVALUATION_PROMPT = """Evaluate this answer for {skill_name}.
Question difficulty: {difficulty}
Question: {question}
Answer: {answer}

Provide:
1. score: integer 1 to 5 (1=Wrong, 3=Mostly correct, 5=Mastery)
2. reasoning: 1-2 sentence explanation

Respond with ONLY valid JSON: {{"score": <int>, "reasoning": "<string>"}}"""

def evaluate_answer(
    skill_name: str, 
    question: str, 
    answer: str, 
    difficulty: ProficiencyLevel
) -> dict:
    
    prompt = EVALUATION_PROMPT.format(
        skill_name=skill_name, 
        difficulty=difficulty.value, 
        question=question, 
        answer=answer
    )
    
    messages = [
        SystemMessage(content=prompt), 
        HumanMessage(content="Evaluate this answer.")
    ]
    
    try:
        from app.utils.llm_client import call_with_retry
        raw = call_with_retry(messages, llm_type="assessment").strip()
        
        if raw.startswith("```json"): 
            raw = raw[7:]
        if raw.startswith("```"): 
            raw = raw[3:]
        if raw.endswith("```"): 
            raw = raw[:-3]
        
        data = json.loads(raw.strip())
        
        return {
            "score": max(1, min(5, int(data.get("score", 3)))), 
            "reasoning": data.get("reasoning", "No reasoning provided.")
        }
    except Exception:
        return {
            "score": 3, 
            "reasoning": "Evaluation parsing failed - defaulting to neutral score."
        }


# ──────────────────────────────────────────────
# Session Manager
# ──────────────────────────────────────────────

class SkillAssessmentSession:
    def __init__(
        self, 
        skill_name: str, 
        claimed_level: ProficiencyLevel, 
        jd_required_level: ProficiencyLevel, 
        context: str = ""
    ):
        self.skill_name = skill_name
        self.claimed_level = claimed_level
        self.jd_required_level = jd_required_level
        self.context = context
        
        self.current_difficulty = get_starting_difficulty(claimed_level)
        self.responses: list[AssessmentResponse] = []
        self.is_complete = False
        self.current_question: str | None = None
        self.question_number = 0
        self.question_bank = generate_question_bank(skill_name, context)

    def _map_difficulty_to_bank_key(self, difficulty: ProficiencyLevel) -> str:
        if difficulty in (ProficiencyLevel.NOVICE, ProficiencyLevel.BEGINNER): 
            return "beginner"
        elif difficulty == ProficiencyLevel.INTERMEDIATE: 
            return "intermediate"
        else: 
            return "advanced"

    def get_next_question(self) -> AssessmentQuestion | None:
        if self.is_complete or self.question_number >= MAX_QUESTIONS_PER_SKILL:
            self.is_complete = True
            return None

        self.question_number += 1
        bank_key = self._map_difficulty_to_bank_key(self.current_difficulty)
        
        if self.question_bank[bank_key]:
            question_text = self.question_bank[bank_key].pop(0)
        else:
            question_text = f"Could you provide another example of your work with {self.skill_name}?"

        self.current_question = question_text
        
        return AssessmentQuestion(
            skill_name=self.skill_name, 
            question=question_text, 
            difficulty=self.current_difficulty, 
            question_number=self.question_number
        )

    def submit_answer(self, answer: str) -> AssessmentResponse:
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
        if not self.responses:
            return SkillAssessmentResult(
                skill_name=self.skill_name, 
                claimed_level=self.claimed_level, 
                assessed_level=ProficiencyLevel.NOVICE, 
                confidence=0.0, 
                questions_asked=0, 
                responses=[], 
                summary="No assessment conducted."
            )
        
        response_dicts = [{"difficulty": r.difficulty, "score": r.score} for r in self.responses]
        assessed_level = determine_final_level(response_dicts)
        
        base_conf = min(len(self.responses) / MAX_QUESTIONS_PER_SKILL, 1.0) * 0.6
        scores = [r.score for r in self.responses]
        
        if len(scores) >= 2:
            variance = sum((s - sum(scores) / len(scores)) ** 2 for s in scores) / len(scores)
            consistency = max(0, 1 - (variance / 4)) * 0.4
        else:
            consistency = 0.2
            
        confidence = round(min(base_conf + consistency, 1.0), 2)

        return SkillAssessmentResult(
            skill_name=self.skill_name, 
            claimed_level=self.claimed_level, 
            assessed_level=assessed_level, 
            confidence=confidence,
            questions_asked=len(self.responses), 
            responses=self.responses,
            summary=f"Assessed at {assessed_level.value} level for {self.skill_name}."
        )


# ──────────────────────────────────────────────
# Orchestrator
# ──────────────────────────────────────────────

class AssessmentOrchestrator:
    def __init__(
        self, 
        parsed_resume: ParsedResume, 
        parsed_jd: ParsedJD, 
        max_skills: int = 5
    ):
        self.parsed_resume = parsed_resume
        self.parsed_jd = parsed_jd
        self.max_skills = max_skills
        
        self.skills_to_assess = select_skills_to_assess(parsed_resume, parsed_jd, max_skills)
        
        self.sessions: list[SkillAssessmentSession] = []
        for item in self.skills_to_assess:
            claimed = item["resume_skill"].claimed_level if item["resume_skill"] else ProficiencyLevel.NOVICE
            context = item["resume_skill"].context if item["resume_skill"] else ""
            
            self.sessions.append(
                SkillAssessmentSession(
                    skill_name=item["jd_skill"].name, 
                    claimed_level=claimed, 
                    jd_required_level=item["jd_skill"].required_level, 
                    context=context
                )
            )

        self.current_skill_index = 0
        self.is_complete = False
        self.results: list[SkillAssessmentResult] = []

    @property
    def current_session(self) -> SkillAssessmentSession | None:
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
        while self.current_skill_index < len(self.sessions):
            session = self.sessions[self.current_skill_index]
            
            if session.is_complete:
                self.results.append(session.get_result())
                self.current_skill_index += 1
                continue

            question = session.get_next_question()
            if question is None:
                self.results.append(session.get_result())
                self.current_skill_index += 1
                continue
                
            return question

        self.is_complete = True
        return None

    def submit_answer(self, answer: str) -> AssessmentResponse:
        if not self.current_session:
            raise ValueError("No active assessment session.")
        return self.current_session.submit_answer(answer)

    def get_all_results(self) -> list[SkillAssessmentResult]:
        for i in range(len(self.results), len(self.sessions)):
            self.results.append(self.sessions[i].get_result())
        return self.results

    def get_skill_overview(self) -> list[dict]:
        overview = []
        for i, item in enumerate(self.skills_to_assess):
            overview.append({
                "index": i + 1, 
                "skill": item["jd_skill"].name, 
                "required_level": item["jd_skill"].required_level.value,
                "claimed_level": item["resume_skill"].claimed_level.value if item["resume_skill"] else "not listed",
                "requirement": item["jd_skill"].requirement_type.value, 
                "reason": item["reason"],
            })
        return overview