"""
Scoring rubrics and logic for skill assessment.
This is the 'brain' that makes the assessment objective and explainable.
"""

from app.models.schemas import ProficiencyLevel, GapPriority, SkillRequirementLevel


# ──────────────────────────────────────────────
# Proficiency Rubrics
# ──────────────────────────────────────────────

PROFICIENCY_RUBRICS: dict[ProficiencyLevel, dict] = {
    ProficiencyLevel.NOVICE: {
        "score": 1,
        "label": "Novice",
        "description": "Has heard of the technology but cannot explain core concepts.",
        "indicators": [
            "Cannot define basic terminology",
            "No hands-on experience",
            "Would need full training to be productive",
        ],
        "question_types": ["Define X", "What is X used for?", "Name basic concepts"],
    },
    ProficiencyLevel.BEGINNER: {
        "score": 2,
        "label": "Beginner",
        "description": "Understands basics, has done tutorials or small projects.",
        "indicators": [
            "Can explain basic concepts",
            "Has completed tutorials or coursework",
            "Limited real-world application",
        ],
        "question_types": ["Explain how X works", "When would you use X vs Y?", "Simple scenario questions"],
    },
    ProficiencyLevel.INTERMEDIATE: {
        "score": 3,
        "label": "Intermediate",
        "description": "Can apply skill in standard situations with some independence.",
        "indicators": [
            "Has built real projects",
            "Can debug common issues",
            "Understands best practices",
        ],
        "question_types": ["Debug this scenario", "Design a solution for...", "What are the trade-offs?"],
    },
    ProficiencyLevel.ADVANCED: {
        "score": 4,
        "label": "Advanced",
        "description": "Deep understanding. Handles complex scenarios confidently.",
        "indicators": [
            "Can architect solutions",
            "Understands internals/edge cases",
            "Can mentor others",
        ],
        "question_types": [
            "How would you architect...",
            "What happens under the hood when...",
            "Optimize this for...",
        ],
    },
    ProficiencyLevel.EXPERT: {
        "score": 5,
        "label": "Expert",
        "description": "Industry-level expertise. Can innovate and teach.",
        "indicators": [
            "Contributes to the ecosystem",
            "Knows internals deeply",
            "Can design novel solutions to hard problems",
        ],
        "question_types": [
            "Design a system that handles...",
            "What are the limitations of X and how would you work around them?",
            "How would you implement X from scratch?",
        ],
    },
}


# ──────────────────────────────────────────────
# Adaptive Assessment Logic
# ──────────────────────────────────────────────

def get_starting_difficulty(claimed_level: ProficiencyLevel) -> ProficiencyLevel:
    """
    Start assessment at one level below claimed level.
    This gives the candidate a warm-up and avoids embarrassment.
    """
    order = [
        ProficiencyLevel.NOVICE,
        ProficiencyLevel.BEGINNER,
        ProficiencyLevel.INTERMEDIATE,
        ProficiencyLevel.ADVANCED,
        ProficiencyLevel.EXPERT,
    ]
    idx = order.index(claimed_level)
    start_idx = max(0, idx - 1)
    return order[start_idx]


def get_next_difficulty(
    current_difficulty: ProficiencyLevel,
    answer_score: int,
) -> ProficiencyLevel | None:
    """
    Adaptive difficulty adjustment based on answer quality.

    Returns next difficulty level or None if assessment is complete.

    Logic:
    - Score >= 4: Move up one level
    - Score 3: Stay at same level (ask one more)
    - Score <= 2: Move down one level or stop
    """
    order = [
        ProficiencyLevel.NOVICE,
        ProficiencyLevel.BEGINNER,
        ProficiencyLevel.INTERMEDIATE,
        ProficiencyLevel.ADVANCED,
        ProficiencyLevel.EXPERT,
    ]
    idx = order.index(current_difficulty)

    if answer_score >= 4:
        # Good answer — try harder question
        if idx < len(order) - 1:
            return order[idx + 1]
        return None  # Already at Expert, done
    elif answer_score == 3:
        # Decent answer — stay at this level for confirmation
        return current_difficulty
    else:
        # Poor answer — try easier or stop
        if idx > 0:
            return order[idx - 1]
        return None  # Already at Novice, done


def determine_final_level(
    responses: list[dict],
) -> ProficiencyLevel:
    """
    Determine final proficiency level from assessment responses.

    Each response dict has: {difficulty: ProficiencyLevel, score: int}

    Logic:
    - Find the highest difficulty where score >= 3
    - If no score >= 3, result is Novice
    """
    order = [
        ProficiencyLevel.NOVICE,
        ProficiencyLevel.BEGINNER,
        ProficiencyLevel.INTERMEDIATE,
        ProficiencyLevel.ADVANCED,
        ProficiencyLevel.EXPERT,
    ]

    highest_passed = None

    for resp in responses:
        if resp["score"] >= 3:
            level = resp["difficulty"]
            if highest_passed is None or order.index(level) > order.index(highest_passed):
                highest_passed = level

    return highest_passed or ProficiencyLevel.NOVICE


# ──────────────────────────────────────────────
# Gap Priority Calculation
# ──────────────────────────────────────────────

def calculate_gap_priority(
    gap_size: int,
    requirement_type: SkillRequirementLevel,
) -> GapPriority:
    """
    Calculate gap priority based on gap size and whether the skill is required.

    Gap size = required_level.numeric - current_level.numeric
    """
    if requirement_type == SkillRequirementLevel.REQUIRED:
        if gap_size >= 3:
            return GapPriority.CRITICAL
        elif gap_size >= 2:
            return GapPriority.HIGH
        elif gap_size >= 1:
            return GapPriority.MEDIUM
        else:
            return GapPriority.LOW
    elif requirement_type == SkillRequirementLevel.PREFERRED:
        if gap_size >= 3:
            return GapPriority.HIGH
        elif gap_size >= 2:
            return GapPriority.MEDIUM
        else:
            return GapPriority.LOW
    else:
        return GapPriority.LOW


# ──────────────────────────────────────────────
# Time Estimation
# ──────────────────────────────────────────────

# Base hours to go from level N to level N+1
BASE_HOURS_PER_LEVEL = {
    (ProficiencyLevel.NOVICE, ProficiencyLevel.BEGINNER): 20,
    (ProficiencyLevel.BEGINNER, ProficiencyLevel.INTERMEDIATE): 40,
    (ProficiencyLevel.INTERMEDIATE, ProficiencyLevel.ADVANCED): 80,
    (ProficiencyLevel.ADVANCED, ProficiencyLevel.EXPERT): 160,
}


def estimate_learning_hours(
    current_level: ProficiencyLevel,
    target_level: ProficiencyLevel,
    learnability_score: float = 0.5,
) -> float:
    """
    Estimate hours to go from current_level to target_level.

    learnability_score (0-1) reduces the time:
    - 0.0 = no adjacent skills, full time needed
    - 1.0 = very adjacent, 50% time reduction
    """
    order = [
        ProficiencyLevel.NOVICE,
        ProficiencyLevel.BEGINNER,
        ProficiencyLevel.INTERMEDIATE,
        ProficiencyLevel.ADVANCED,
        ProficiencyLevel.EXPERT,
    ]

    current_idx = order.index(current_level)
    target_idx = order.index(target_level)

    if target_idx <= current_idx:
        return 0.0

    total_hours = 0.0
    for i in range(current_idx, target_idx):
        level_pair = (order[i], order[i + 1])
        total_hours += BASE_HOURS_PER_LEVEL.get(level_pair, 40)

    # Apply learnability discount (up to 50% reduction)
    discount = learnability_score * 0.5
    total_hours *= (1 - discount)

    return round(total_hours, 1)