"""
Pydantic schemas for the Skill Assessment Agent.
These are the data contracts between all agents.
"""

from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum


# ──────────────────────────────────────────────
# Enums
# ──────────────────────────────────────────────

class ProficiencyLevel(str, Enum):
    """5-level proficiency scale used throughout the system."""
    NOVICE = "novice"
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
    EXPERT = "expert"

    @property
    def numeric(self) -> int:
        """Convert to numeric score (1-5)."""
        mapping = {
            "novice": 1,
            "beginner": 2,
            "intermediate": 3,
            "advanced": 4,
            "expert": 5,
        }
        return mapping[self.value]


class SkillCategory(str, Enum):
    """Skill domain categories."""
    PROGRAMMING_LANGUAGE = "programming_language"
    FRAMEWORK = "framework"
    DATABASE = "database"
    DEVOPS = "devops"
    CLOUD = "cloud"
    AI_ML = "ai_ml"
    SOFT_SKILL = "soft_skill"
    TOOL = "tool"
    METHODOLOGY = "methodology"
    OTHER = "other"


class GapPriority(str, Enum):
    """Priority level for a skill gap."""
    CRITICAL = "critical"       # Required skill, large gap
    HIGH = "high"               # Required skill, moderate gap
    MEDIUM = "medium"           # Nice-to-have or small gap
    LOW = "low"                 # Minor gap, or very nice-to-have


class SkillRequirementLevel(str, Enum):
    """How the JD classifies a skill requirement."""
    REQUIRED = "required"
    PREFERRED = "preferred"
    NICE_TO_HAVE = "nice_to_have"


# ──────────────────────────────────────────────
# Skill-related schemas
# ──────────────────────────────────────────────

class Skill(BaseModel):
    """A single skill extracted from resume or JD."""
    name: str = Field(..., description="Normalized skill name, e.g., 'Python', 'Kubernetes'")
    category: SkillCategory = Field(default=SkillCategory.OTHER, description="Skill domain")
    aliases: list[str] = Field(default_factory=list, description="Alternative names, e.g., ['k8s'] for Kubernetes")


class JDSkill(Skill):
    """A skill as listed in a Job Description, with required proficiency."""
    required_level: ProficiencyLevel = Field(
        default=ProficiencyLevel.INTERMEDIATE,
        description="Minimum proficiency the JD expects",
    )
    requirement_type: SkillRequirementLevel = Field(
        default=SkillRequirementLevel.REQUIRED,
        description="Is this required, preferred, or nice-to-have?",
    )


class ResumeSkill(Skill):
    """A skill as claimed on a resume, with the claimed proficiency."""
    claimed_level: ProficiencyLevel = Field(
        default=ProficiencyLevel.INTERMEDIATE,
        description="Proficiency level inferred from the resume",
    )
    years_experience: Optional[float] = Field(
        default=None,
        description="Years of experience mentioned for this skill",
    )
    context: str = Field(
        default="",
        description="Brief context from resume (e.g., 'used in production at Company X')",
    )


# ──────────────────────────────────────────────
# Parsing outputs
# ──────────────────────────────────────────────

class ParsedJD(BaseModel):
    """Structured output from parsing a Job Description."""
    job_title: str = Field(default="", description="Job title from the JD")
    company: str = Field(default="", description="Company name if mentioned")
    seniority_level: str = Field(default="", description="e.g., Junior, Mid, Senior, Lead")
    skills: list[JDSkill] = Field(default_factory=list, description="All skills extracted from JD")
    summary: str = Field(default="", description="Brief summary of the role")


class ParsedResume(BaseModel):
    """Structured output from parsing a Resume."""
    candidate_name: str = Field(default="", description="Candidate's name")
    total_experience_years: Optional[float] = Field(default=None, description="Total years of experience")
    current_role: str = Field(default="", description="Current or most recent role")
    skills: list[ResumeSkill] = Field(default_factory=list, description="All skills found on resume")
    education: list[str] = Field(default_factory=list, description="Degrees and certifications")
    summary: str = Field(default="", description="Brief professional summary")


# ──────────────────────────────────────────────
# Assessment schemas
# ──────────────────────────────────────────────

class AssessmentQuestion(BaseModel):
    """A single assessment question for a skill."""
    skill_name: str
    question: str
    difficulty: ProficiencyLevel
    question_number: int = Field(default=1, description="Which question in the sequence (1-3)")


class AssessmentResponse(BaseModel):
    """Candidate's response + evaluation for one question."""
    skill_name: str
    question: str
    candidate_answer: str
    score: int = Field(..., ge=1, le=5, description="Score from 1-5")
    reasoning: str = Field(default="", description="Why this score was given")
    difficulty: ProficiencyLevel


class SkillAssessmentResult(BaseModel):
    """Final assessment result for a single skill."""
    skill_name: str
    claimed_level: ProficiencyLevel
    assessed_level: ProficiencyLevel
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="How confident we are in the assessment")
    questions_asked: int = Field(default=0)
    responses: list[AssessmentResponse] = Field(default_factory=list)
    summary: str = Field(default="", description="Brief summary of the assessment")


# ──────────────────────────────────────────────
# Gap analysis schemas
# ──────────────────────────────────────────────

class SkillGap(BaseModel):
    """A single identified skill gap."""
    skill_name: str
    required_level: ProficiencyLevel
    current_level: ProficiencyLevel
    gap_size: int = Field(default=0, description="Numeric gap (required - current)")
    priority: GapPriority = Field(default=GapPriority.MEDIUM)
    requirement_type: SkillRequirementLevel = Field(default=SkillRequirementLevel.REQUIRED)
    adjacent_skills: list[str] = Field(
        default_factory=list,
        description="Skills the candidate already has that are related",
    )
    learnability_score: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="How easily this skill can be learned given existing skills (0=hard, 1=easy)",
    )
    estimated_hours: float = Field(
        default=0.0,
        description="Estimated hours to bridge the gap",
    )


class GapAnalysisResult(BaseModel):
    """Complete gap analysis output."""
    overall_match_score: float = Field(
        default=0.0, ge=0.0, le=100.0,
        description="Overall fit percentage (0-100)",
    )
    gaps: list[SkillGap] = Field(default_factory=list)
    strengths: list[str] = Field(
        default_factory=list,
        description="Skills where candidate meets or exceeds requirements",
    )
    total_estimated_hours: float = Field(default=0.0)
    summary: str = Field(default="")


# ──────────────────────────────────────────────
# Learning plan schemas
# ──────────────────────────────────────────────

class LearningResource(BaseModel):
    """A single learning resource."""
    title: str
    url: str = Field(default="")
    resource_type: str = Field(default="course", description="e.g., course, article, video, project, documentation")
    is_free: bool = Field(default=True)
    estimated_hours: float = Field(default=0.0)
    description: str = Field(default="")


class LearningMilestone(BaseModel):
    """A milestone within a skill learning path."""
    title: str
    description: str = Field(default="")
    target_level: ProficiencyLevel
    estimated_hours: float = Field(default=0.0)
    resources: list[LearningResource] = Field(default_factory=list)
    practice_project: str = Field(default="", description="A hands-on project suggestion")


class SkillLearningPath(BaseModel):
    """Complete learning path for one skill gap."""
    skill_name: str
    current_level: ProficiencyLevel
    target_level: ProficiencyLevel
    priority: GapPriority
    total_estimated_hours: float = Field(default=0.0)
    milestones: list[LearningMilestone] = Field(default_factory=list)
    why_learn: str = Field(default="", description="Motivation — why this skill matters for the target role")
    leverage_existing: list[str] = Field(
        default_factory=list,
        description="Existing skills that will help learn this",
    )


class PersonalizedLearningPlan(BaseModel):
    """The final output — a complete personalized learning plan."""
    candidate_name: str = Field(default="")
    target_role: str = Field(default="")
    overall_match_score: float = Field(default=0.0)
    total_estimated_hours: float = Field(default=0.0)
    estimated_weeks: float = Field(default=0.0, description="At ~10 hrs/week")
    learning_paths: list[SkillLearningPath] = Field(default_factory=list)
    strengths_summary: str = Field(default="")
    quick_wins: list[str] = Field(
        default_factory=list,
        description="Skills that can be acquired in < 1 week",
    )
    long_term_goals: list[str] = Field(
        default_factory=list,
        description="Skills that will take > 4 weeks",
    )