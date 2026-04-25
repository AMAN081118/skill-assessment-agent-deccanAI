"""
Shared helper functions used across the application.
"""

from app.models.schemas import ProficiencyLevel


def level_to_emoji(level: ProficiencyLevel) -> str:
    """Map proficiency level to a visual emoji indicator."""
    mapping = {
        ProficiencyLevel.NOVICE: "⬜",
        ProficiencyLevel.BEGINNER: "🟨",
        ProficiencyLevel.INTERMEDIATE: "🟧",
        ProficiencyLevel.ADVANCED: "🟩",
        ProficiencyLevel.EXPERT: "🟦",
    }
    return mapping.get(level, "⬜")


def level_to_color(level: ProficiencyLevel) -> str:
    """Map proficiency level to a hex color for charts."""
    mapping = {
        ProficiencyLevel.NOVICE: "#ef4444",
        ProficiencyLevel.BEGINNER: "#f97316",
        ProficiencyLevel.INTERMEDIATE: "#eab308",
        ProficiencyLevel.ADVANCED: "#22c55e",
        ProficiencyLevel.EXPERT: "#3b82f6",
    }
    return mapping.get(level, "#6b7280")


def gap_priority_to_emoji(priority: str) -> str:
    """Map gap priority to emoji."""
    mapping = {
        "critical": "🔴",
        "high": "🟠",
        "medium": "🟡",
        "low": "🟢",
    }
    return mapping.get(priority, "⚪")


def truncate_text(text: str, max_length: int = 500) -> str:
    """Truncate text to max_length with ellipsis."""
    if len(text) <= max_length:
        return text
    return text[:max_length].rsplit(" ", 1)[0] + "..."