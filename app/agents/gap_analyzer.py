"""
Gap Analyzer Agent -- Compares assessed skill levels against JD requirements.

Takes assessment results + parsed JD/resume and produces:
- Skill gap identification with priority ranking
- Adjacent skill detection (what existing skills help learn new ones)
- Learnability scoring
- Overall match percentage
"""

import json
from app.models.schemas import (
    ParsedJD,
    ParsedResume,
    JDSkill,
    ResumeSkill,
    ProficiencyLevel,
    SkillAssessmentResult,
    SkillGap,
    GapAnalysisResult,
    GapPriority,
    SkillRequirementLevel,
)
from app.models.scoring import (
    calculate_gap_priority,
    estimate_learning_hours,
)


# ──────────────────────────────────────────────
# Skill Adjacency Loader
# ──────────────────────────────────────────────

def _load_skill_taxonomy() -> dict:
    """Load the skill taxonomy from the JSON file."""
    import os
    taxonomy_path = os.path.join(
        os.path.dirname(__file__), "..", "data", "skill_taxonomy.json"
    )
    try:
        with open(taxonomy_path, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"categories": {}}


def _build_adjacency_map(taxonomy: dict) -> dict[str, list[str]]:
    """
    Build a flat map of skill_name -> list of adjacent skills
    from the nested taxonomy structure.
    """
    adjacency = {}
    for category, skills in taxonomy.get("categories", {}).items():
        for skill_name, skill_data in skills.items():
            adjacent = skill_data.get("adjacent", [])
            adjacency[skill_name.lower()] = [s.lower() for s in adjacent]

            # Also map aliases
            for alias in skill_data.get("aliases", []):
                adjacency[alias.lower()] = [s.lower() for s in adjacent]

    return adjacency


def _find_adjacent_skills(
    target_skill: str,
    candidate_skills: list[str],
    adjacency_map: dict[str, list[str]],
) -> list[str]:
    """
    Find which of the candidate's existing skills are adjacent to the target skill.
    """
    target_lower = target_skill.lower().strip()
    candidate_lower = [s.lower().strip() for s in candidate_skills]

    adjacent = []

    # Check if any candidate skill is in the target's adjacency list
    target_neighbors = adjacency_map.get(target_lower, [])
    for cs in candidate_lower:
        if cs in target_neighbors:
            adjacent.append(cs)

    # Also check reverse: if the target is in any candidate skill's adjacency list
    for cs in candidate_lower:
        cs_neighbors = adjacency_map.get(cs, [])
        if target_lower in cs_neighbors and cs not in adjacent:
            adjacent.append(cs)

    return adjacent


def _calculate_learnability(
    target_skill: str,
    candidate_skills: list[str],
    adjacency_map: dict[str, list[str]],
) -> float:
    """
    Calculate how easily a candidate can learn the target skill
    based on their existing skills.

    Returns 0.0 (hard, no related skills) to 1.0 (easy, many related skills).
    """
    adjacent = _find_adjacent_skills(target_skill, candidate_skills, adjacency_map)

    if not adjacent:
        return 0.1  # Baseline -- anyone can learn anything

    # More adjacent skills = easier to learn, with diminishing returns
    # 1 adjacent: 0.4, 2: 0.6, 3: 0.75, 4+: 0.85
    count = len(adjacent)
    if count == 1:
        return 0.4
    elif count == 2:
        return 0.6
    elif count == 3:
        return 0.75
    else:
        return 0.85


# ──────────────────────────────────────────────
# Core Gap Analysis
# ──────────────────────────────────────────────

def analyze_gaps(
    parsed_resume: ParsedResume,
    parsed_jd: ParsedJD,
    assessment_results: list[SkillAssessmentResult],
) -> GapAnalysisResult:
    """
    Perform full gap analysis comparing assessed levels against JD requirements.

    Logic:
    1. For assessed skills: use assessed_level (ground truth from assessment)
    2. For non-assessed skills on resume: use claimed_level (best we have)
    3. For skills not on resume at all: assume novice
    4. Compare each against JD required_level to find gaps
    """
    taxonomy = _load_skill_taxonomy()
    adjacency_map = _build_adjacency_map(taxonomy)

    # Build lookup maps
    # Assessed skills: skill_name -> assessed_level
    assessed_map = {}
    for result in assessment_results:
        assessed_map[result.skill_name.lower().strip()] = result

    # Resume skills: skill_name -> claimed_level
    resume_map = {}
    for rs in parsed_resume.skills:
        resume_map[rs.name.lower().strip()] = rs
        for alias in rs.aliases:
            resume_map[alias.lower().strip()] = rs

    # All candidate skill names (for adjacency lookup)
    all_candidate_skills = [s.name for s in parsed_resume.skills]

    # Analyze each JD skill
    gaps = []
    strengths = []
    total_required_score = 0
    total_current_score = 0

    for jd_skill in parsed_jd.skills:
        jd_name_lower = jd_skill.name.lower().strip()

        # Determine current level
        current_level = ProficiencyLevel.NOVICE  # default if not found anywhere

        # Check assessed results first (highest confidence)
        assessed_result = assessed_map.get(jd_name_lower)
        if assessed_result:
            current_level = assessed_result.assessed_level
        else:
            # Check resume claims
            resume_skill = resume_map.get(jd_name_lower)
            if not resume_skill:
                # Try partial matching
                for key, rs in resume_map.items():
                    if jd_name_lower in key or key in jd_name_lower:
                        resume_skill = rs
                        break
            if resume_skill:
                current_level = resume_skill.claimed_level

        # Calculate gap
        gap_size = jd_skill.required_level.numeric - current_level.numeric

        # Track for overall score
        total_required_score += jd_skill.required_level.numeric
        total_current_score += min(current_level.numeric, jd_skill.required_level.numeric)

        if gap_size <= 0:
            # No gap -- this is a strength
            strengths.append(
                f"{jd_skill.name}: {current_level.value.title()} "
                f"(meets/exceeds {jd_skill.required_level.value.title()} requirement)"
            )
            continue

        # There is a gap -- analyze it
        adjacent = _find_adjacent_skills(
            jd_skill.name, all_candidate_skills, adjacency_map
        )
        learnability = _calculate_learnability(
            jd_skill.name, all_candidate_skills, adjacency_map
        )
        priority = calculate_gap_priority(gap_size, jd_skill.requirement_type)
        hours = estimate_learning_hours(current_level, jd_skill.required_level, learnability)

        skill_gap = SkillGap(
            skill_name=jd_skill.name,
            required_level=jd_skill.required_level,
            current_level=current_level,
            gap_size=gap_size,
            priority=priority,
            requirement_type=jd_skill.requirement_type,
            adjacent_skills=[s.title() for s in adjacent],
            learnability_score=learnability,
            estimated_hours=hours,
        )
        gaps.append(skill_gap)

    # Sort gaps by priority
    priority_order = {
        GapPriority.CRITICAL: 0,
        GapPriority.HIGH: 1,
        GapPriority.MEDIUM: 2,
        GapPriority.LOW: 3,
    }
    gaps.sort(key=lambda g: (priority_order.get(g.priority, 99), -g.gap_size))

    # Calculate overall match score
    if total_required_score > 0:
        overall_match = (total_current_score / total_required_score) * 100
    else:
        overall_match = 0.0

    total_hours = sum(g.estimated_hours for g in gaps)

    # Generate summary
    summary = _generate_gap_summary(overall_match, gaps, strengths)

    return GapAnalysisResult(
        overall_match_score=round(overall_match, 1),
        gaps=gaps,
        strengths=strengths,
        total_estimated_hours=round(total_hours, 1),
        summary=summary,
    )


def _generate_gap_summary(
    match_score: float,
    gaps: list[SkillGap],
    strengths: list[str],
) -> str:
    """Generate a human-readable summary of the gap analysis."""
    critical_count = sum(1 for g in gaps if g.priority == GapPriority.CRITICAL)
    high_count = sum(1 for g in gaps if g.priority == GapPriority.HIGH)

    parts = [f"Overall match: {match_score:.0f}%."]

    if not gaps:
        parts.append("No skill gaps detected. The candidate meets or exceeds all requirements.")
    else:
        parts.append(f"Found {len(gaps)} skill gap(s)")
        if critical_count > 0:
            parts.append(f"including {critical_count} critical")
        if high_count > 0:
            parts.append(f"and {high_count} high priority")
        parts[-1] += "."

    if strengths:
        parts.append(f"The candidate excels in {len(strengths)} area(s).")

    return " ".join(parts)