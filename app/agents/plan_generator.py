"""
Learning Plan Generator Agent -- Creates personalized learning paths.

KEY DESIGN: Generates the entire learning plan in a SINGLE LLM call
to minimize API requests and stay within free tier rate limits.
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
# SINGLE BATCHED LLM call for all skill gaps
# ──────────────────────────────────────────────

BATCH_PLAN_PROMPT = """You are a technical learning advisor creating a personalized learning plan.

The candidate has the following skill gaps to address for the role of {target_role}:

{gaps_description}

CRITICAL OUTPUT CONSTRAINTS (TO PREVENT TOKEN LIMITS):
1. MAX PATHS: Only generate detailed learning paths for the TOP 3 highest-priority skill gaps. Ignore the rest.
2. MAX MILESTONES: Limit each learning path to exactly 2 milestones.
3. MAX RESOURCES: Limit each milestone to exactly 2 highly relevant resources.
4. CONCISENESS: Keep all descriptions, "why learn this", and summaries under 2 sentences. Be incredibly concise.

For those top 3 skill gaps, generate a learning path. Respond with ONLY valid JSON matching this schema:
{{
  "paths": [
    {{
      "skill_name": "exact skill name from above",
      "why_learn": "1 sentence motivation",
      "leverage_existing": ["how existing skill X helps", "how existing skill Y helps"],
      "milestones": [
        {{
          "title": "milestone title",
          "description": "what the learner achieves",
          "target_level": "beginner|intermediate|advanced|expert",
          "estimated_hours": number,
          "resources": [
            {{
              "title": "resource name",
              "url": "https://...",
              "resource_type": "course|article|video|project|documentation",
              "is_free": true,
              "estimated_hours": number,
              "description": "brief description"
            }}
          ],
          "practice_project": "hands-on project description"
        }}
      ]
    }}
  ]
}}

Rules:
- 1-2 milestones per skill MAXIMUM
- 1-2 resources per milestone MAXIMUM
- Prefer free resources (official docs, YouTube, GitHub repos, free courses)
- Include practical projects at each milestone
- Time estimates should be realistic
- Leverage the candidate's existing skills where possible
- No markdown, no extra text, ONLY JSON"""


def _generate_all_paths_with_llm(
    gaps: list[SkillGap],
    target_role: str,
) -> dict:
    """
    Generate learning paths for ALL skill gaps in a single LLM call.
    This is the key optimization -- 1 API call instead of N.
    """
    gaps_description = ""
    
    # Sort gaps by priority (assuming Priority Enum: CRITICAL is highest)
    # We pass all of them so the LLM has context, but it will only process the top 3
    sorted_gaps = sorted(gaps, key=lambda g: g.priority.value if hasattr(g.priority, 'value') else 0)
    
    for i, gap in enumerate(sorted_gaps, 1):
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
        HumanMessage(content=f"Generate concise learning paths for the top 3 most critical skill gaps out of the {len(gaps)} provided."),
    ]

    try:
        raw = call_with_retry(messages, llm_type="analysis")

        # Clean markdown
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
    gaps: list[SkillGap],
) -> list[SkillLearningPath]:
    """
    Build SkillLearningPath objects from the batched LLM response,
    enriched with curated resources.
    """
    # Index LLM paths by skill name
    llm_paths_map = {}
    for path_data in llm_data.get("paths", []):
        name = path_data.get("skill_name", "").lower().strip()
        llm_paths_map[name] = path_data

    result = []

    for gap in gaps:
        gap_name_lower = gap.skill_name.lower().strip()

        # Find matching LLM path
        llm_path = llm_paths_map.get(gap_name_lower)
        if not llm_path:
            # Try partial match
            for key, val in llm_paths_map.items():
                if gap_name_lower in key or key in gap_name_lower:
                    llm_path = val
                    break

        # Get curated resources as supplement
        curated = _get_curated_resources(
            gap.skill_name, gap.current_level, gap.required_level
        )

        if llm_path:
            milestones = []
            for m in llm_path.get("milestones", []):
                resources = []
                for r in m.get("resources", []):
                    resources.append(LearningResource(
                        title=r.get("title", ""),
                        url=r.get("url", ""),
                        resource_type=r.get("resource_type", "course"),
                        is_free=r.get("is_free", True),
                        estimated_hours=r.get("estimated_hours", 0),
                        description=r.get("description", ""),
                    ))

                target_lvl = m.get("target_level", "intermediate")
                try:
                    target_level = ProficiencyLevel(target_lvl.lower())
                except ValueError:
                    target_level = ProficiencyLevel.INTERMEDIATE

                milestones.append(LearningMilestone(
                    title=m.get("title", ""),
                    description=m.get("description", ""),
                    target_level=target_level,
                    estimated_hours=m.get("estimated_hours", 0),
                    resources=resources,
                    practice_project=m.get("practice_project", ""),
                ))

            why_learn = llm_path.get(
                "why_learn",
                f"Bridging this gap in {gap.skill_name} is essential for the target role."
            )
            leverage = llm_path.get("leverage_existing", [])

        else:
            # Fallback: build from curated resources (Saves LLM tokens!)
            milestones = _create_fallback_milestones(gap, curated)
            why_learn = f"Bridging this gap in {gap.skill_name} is essential for the target role."
            leverage = []

        total_hours = sum(m.estimated_hours for m in milestones)
        if total_hours == 0:
            total_hours = gap.estimated_hours

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

    return result


def _create_fallback_milestones(
    skill_gap: SkillGap,
    curated_resources: list[LearningResource],
) -> list[LearningMilestone]:
    """Create basic milestones when LLM generation fails or is skipped to save tokens."""
    level_order = [
        ProficiencyLevel.NOVICE,
        ProficiencyLevel.BEGINNER,
        ProficiencyLevel.INTERMEDIATE,
        ProficiencyLevel.ADVANCED,
        ProficiencyLevel.EXPERT,
    ]

    current_idx = level_order.index(skill_gap.current_level)
    target_idx = level_order.index(skill_gap.required_level)

    milestones = []
    resource_idx = 0

    for i in range(current_idx + 1, target_idx + 1):
        level = level_order[i]

        milestone_resources = []
        while resource_idx < len(curated_resources) and len(milestone_resources) < 3:
            milestone_resources.append(curated_resources[resource_idx])
            resource_idx += 1

        hours = sum(r.estimated_hours for r in milestone_resources) or 15

        milestones.append(LearningMilestone(
            title=f"Reach {level.value.title()} in {skill_gap.skill_name}",
            description=f"Build {level.value} proficiency through structured learning and practice.",
            target_level=level,
            estimated_hours=hours,
            resources=milestone_resources,
            practice_project=f"Build a project that demonstrates {level.value}-level {skill_gap.skill_name} skills.",
        ))

    return milestones


# ──────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────

def generate_learning_plan(
    parsed_resume: ParsedResume,
    parsed_jd: ParsedJD,
    gap_analysis: GapAnalysisResult,
) -> PersonalizedLearningPlan:
    """
    Generate a complete personalized learning plan.
    Makes a SINGLE LLM call for all skill gaps.
    """
    if gap_analysis.gaps:
        # ONE call for all gaps
        llm_data = _generate_all_paths_with_llm(
            gap_analysis.gaps,
            parsed_jd.job_title,
        )
        learning_paths = _build_paths_from_llm_response(llm_data, gap_analysis.gaps)
    else:
        learning_paths = []

    total_hours = sum(p.total_estimated_hours for p in learning_paths)
    estimated_weeks = total_hours / 10.0 if total_hours > 0 else 0

    quick_wins = []
    long_term = []

    for path in learning_paths:
        label = (
            f"{path.skill_name}: {path.current_level.value.title()} to "
            f"{path.target_level.value.title()} (~{path.total_estimated_hours:.0f} hours)"
        )
        if path.total_estimated_hours <= 20:
            quick_wins.append(label)
        elif path.total_estimated_hours > 60:
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
        learning_paths=learning_paths,
        strengths_summary=strengths_summary,
        quick_wins=quick_wins,
        long_term_goals=long_term,
    )