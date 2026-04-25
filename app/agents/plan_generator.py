"""
Learning Plan Generator Agent -- Creates personalized learning paths.

KEY DESIGN: Uses Pagination/Lazy-Loading to generate detailed learning 
paths in small batches (e.g., 3 at a time) to prevent LLM token limits 
and avoid using generic hardcoded fallbacks.
"""

import json
import os
from langchain_core.messages import SystemMessage, HumanMessage
from app.utils.llm_client import call_with_retry
from app.models.schemas import (
    ParsedResume,
    ParsedJD,
    GapAnalysisResult,
    SkillGap,
    SkillLearningPath,
    LearningMilestone,
    LearningResource,
    PersonalizedLearningPlan,
    ProficiencyLevel,
    GapPriority,
)

# ──────────────────────────────────────────────
# Resource Database Loader
# ──────────────────────────────────────────────

def _load_resources_db() -> dict:
    """Load curated resources from JSON file."""
    db_path = os.path.join(
        os.path.dirname(__file__), "..", "data", "resources_db.json"
    )
    try:
        with open(db_path, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _get_curated_resources(
    skill_name: str,
    current_level: ProficiencyLevel,
    target_level: ProficiencyLevel,
) -> list[LearningResource]:
    """Get curated resources for a skill from the local database."""
    db = _load_resources_db()
    skill_key = skill_name.lower().strip().replace(" ", "_")

    skill_data = db.get(skill_key)
    if not skill_data:
        for key in db:
            if skill_key in key or key in skill_key:
                skill_data = db[key]
                break

    if not skill_data:
        skill_data = db.get("_default", {})

    level_order = [
        ProficiencyLevel.BEGINNER,
        ProficiencyLevel.INTERMEDIATE,
        ProficiencyLevel.ADVANCED,
        ProficiencyLevel.EXPERT,
    ]

    resources = []
    collecting = False

    for level in level_order:
        if level.numeric > current_level.numeric:
            collecting = True
        if collecting:
            level_resources = skill_data.get(level.value, [])
            for r in level_resources:
                resources.append(LearningResource(
                    title=r.get("title", ""),
                    url=r.get("url", ""),
                    resource_type=r.get("type", "course"),
                    is_free=r.get("free", True),
                    estimated_hours=r.get("hours", 0),
                    description=r.get("description", ""),
                ))
        if level == target_level:
            break

    return resources


# ──────────────────────────────────────────────
# Batched LLM call for a specific slice of skill gaps
# ──────────────────────────────────────────────

BATCH_PLAN_PROMPT = """You are a technical learning advisor creating a personalized learning strategy.

The candidate has the following skill gaps to address for the role of {target_role}:

{gaps_description}

CRITICAL OUTPUT CONSTRAINTS (TO PREVENT TOKEN LIMITS):
1. MAX MILESTONES: Limit each learning path to exactly 2 milestones.
2. CONCISENESS: Keep all descriptions and "why learn this" under 2 sentences. Be incredibly concise.

Generate a learning path for EVERY skill gap listed above. Respond with ONLY valid JSON matching this schema:
{{
  "paths": [
    {{
      "skill_name": "exact skill name from above",
      "why_learn": "1 sentence motivation",
      "leverage_existing": ["how existing skill X helps"],
      "milestones": [
        {{
          "title": "milestone title",
          "description": "what the learner achieves",
          "target_level": "beginner|intermediate|advanced|expert",
          "practice_project": "1 sentence hands-on project description"
        }}
      ]
    }}
  ]
}}

Rules:
- DO NOT INCLUDE URLs OR LEARNING RESOURCES. You provide the strategy; the system will attach the resources later.
- Leverage the candidate's existing skills where possible.
- No markdown, no extra text, ONLY JSON."""


def _generate_paths_with_llm(
    gaps_batch: list[SkillGap],
    target_role: str,
) -> dict:
    """
    Generate learning paths for the specific batch of skill gaps provided.
    """
    gaps_description = ""
    
    for i, gap in enumerate(gaps_batch, 1):
        adjacent_str = ", ".join(gap.adjacent_skills) if gap.adjacent_skills else "none identified"
        gaps_description += (
            f"{i}. {gap.skill_name}: "
            f"Current={gap.current_level.value}, Target={gap.required_level.value}, "
            f"Priority={gap.priority}, "
            f"Related skills candidate has: {adjacent_str}, "
            f"Estimated hours: {gap.estimated_hours}\n"
        )

    prompt = BATCH_PLAN_PROMPT.format(
        target_role=target_role,
        gaps_description=gaps_description,
    )

    messages = [
        SystemMessage(content=prompt),
        HumanMessage(content=f"Generate concise learning paths for ALL {len(gaps_batch)} skill gaps provided."),
    ]

    try:
        raw = call_with_retry(messages, llm_type="analysis")

        cleaned = raw.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        if cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

        return json.loads(cleaned)

    except Exception as e:
        print(f"LLM batch plan generation failed: {e}")
        return {"paths": []}


# ──────────────────────────────────────────────
# Build learning paths from LLM + curated data
# ──────────────────────────────────────────────

def _build_paths_from_llm_response(
    llm_data: dict,
    gaps_batch: list[SkillGap],
) -> list[SkillLearningPath]:
    """
    Build paths using LLM strategy, injecting all resource links from local DB.
    """
    llm_paths_map = {
        path_data.get("skill_name", "").lower().strip(): path_data 
        for path_data in llm_data.get("paths", [])
    }

    result = []

    for gap in gaps_batch:
        gap_name_lower = gap.skill_name.lower().strip()
        
        # Fuzzy matching to find the LLM's path for this skill
        llm_path = next((val for key, val in llm_paths_map.items() if gap_name_lower in key), None)

        if llm_path:
            milestones = []
            for m in llm_path.get("milestones", []):
                
                target_lvl_str = m.get("target_level", "intermediate")
                try:
                    target_level = ProficiencyLevel(target_lvl_str.lower())
                except ValueError:
                    target_level = ProficiencyLevel.INTERMEDIATE

                # Inject resources from local JSON DB
                curated_resources = _get_curated_resources(
                    gap.skill_name, 
                    gap.current_level, 
                    target_level
                )
                
                milestone_hours = sum(r.estimated_hours for r in curated_resources) or 15

                milestones.append(LearningMilestone(
                    title=m.get("title", ""),
                    description=m.get("description", ""),
                    target_level=target_level,
                    estimated_hours=milestone_hours,
                    resources=curated_resources, 
                    practice_project=m.get("practice_project", ""),
                ))

            why_learn = llm_path.get("why_learn", f"Bridging this gap is essential for {gap.skill_name}.")
            leverage = llm_path.get("leverage_existing", [])

            total_hours = sum(m.estimated_hours for m in milestones) or gap.estimated_hours

            result.append(SkillLearningPath(
                skill_name=gap.skill_name,
                current_level=gap.current_level,
                target_level=gap.required_level,
                priority=gap.priority,
                total_estimated_hours=round(total_hours, 1),
                milestones=milestones,
                why_learn=why_learn,
                leverage_existing=leverage,
            ))
        else:
            print(f"Warning: LLM skipped path for {gap.skill_name}")

    return result


# ──────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────

def generate_paths_batch(
    gaps_batch: list[SkillGap], 
    target_role: str
) -> list[SkillLearningPath]:
    """
    Takes a specific slice of gaps (e.g., exactly 3) and generates 
    their dynamic learning paths via the LLM.
    """
    if not gaps_batch:
        return []

    llm_data = _generate_paths_with_llm(gaps_batch, target_role)
    learning_paths = _build_paths_from_llm_response(llm_data, gaps_batch)
    
    return learning_paths


def generate_learning_plan_base(
    parsed_resume: ParsedResume,
    parsed_jd: ParsedJD,
    gap_analysis: GapAnalysisResult,
) -> PersonalizedLearningPlan:
    """
    Generates the base structure of the learning plan (metadata, strengths, etc.)
    without triggering the heavy LLM path generation. Paths are lazy-loaded.
    """
    # Use the hours directly from the gap analysis to give an accurate total immediately
    total_hours = gap_analysis.total_estimated_hours
    estimated_weeks = total_hours / 10.0 if total_hours > 0 else 0

    quick_wins = []
    long_term = []

    for gap in gap_analysis.gaps:
        label = (
            f"{gap.skill_name}: {gap.current_level.value.title()} to "
            f"{gap.required_level.value.title()} (~{gap.estimated_hours:.0f} hours)"
        )
        if gap.estimated_hours <= 20:
            quick_wins.append(label)
        elif gap.estimated_hours > 60:
            long_term.append(label)

    strengths_summary = ""
    if gap_analysis.strengths:
        strengths_summary = (
            f"Strong in {len(gap_analysis.strengths)} areas: "
            + "; ".join(gap_analysis.strengths[:5])
        )

    return PersonalizedLearningPlan(
        candidate_name=parsed_resume.candidate_name,
        target_role=parsed_jd.job_title,
        overall_match_score=gap_analysis.overall_match_score,
        total_estimated_hours=round(total_hours, 1),
        estimated_weeks=round(estimated_weeks, 1),
        learning_paths=[], # Left empty to be filled by UI pagination
        strengths_summary=strengths_summary,
        quick_wins=quick_wins,
        long_term_goals=long_term,
    )