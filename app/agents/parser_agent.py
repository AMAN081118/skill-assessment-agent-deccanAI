"""
Parser Agent -- Extracts structured skill data from Resume and Job Description.
Uses Gemini for parsing with automatic retry and fallback.
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
    SkillCategory,
    SkillRequirementLevel,
)


# ──────────────────────────────────────────────
# Compact System Prompts
# ──────────────────────────────────────────────

TARGETED_RESUME_PARSER_PROMPT = """You are an expert technical recruiter. 
Analyze the candidate's resume ONLY for the specific skills requested below.

TARGET SKILLS TO FIND:
{target_skills}

For each target skill found, infer proficiency:
- novice: just mentioned/familiar, no real usage
- beginner: used in 1 small project or academic, <1 year
- intermediate: used in 2+ projects or professionally, 1-2 years
- advanced: 3+ years, lead/deep work
- expert: 5+ years, recognized expertise

Rules:
1. If a target skill is NOT found on the resume, DO NOT include it in the JSON output.
2. Ignore any skills on the resume that are not in the target list.
3. Respond with ONLY valid JSON. No markdown. No explanation.
"""


JD_PARSER_PROMPT = """You are an expert job description analyzer. Extract structured data from the JD.

For each skill, determine:
- requirement_type: "required" (must have), "preferred" (good to have), "nice_to_have" (bonus)
- required_level: infer from seniority + context (Intern/Junior=beginner, Mid=intermediate, Senior=advanced, Lead=expert)

Categories: programming_language, framework, database, devops, cloud, ai_ml, soft_skill, tool, methodology, other

Respond with ONLY valid JSON. No markdown. No explanation."""


RESUME_SCHEMA = """{
  "candidate_name": "str",
  "total_experience_years": number|null,
  "current_role": "str",
  "education": ["str"],
  "summary": "1-2 sentence summary",
  "skills": [
    {
      "name": "Normalized Name",
      "category": "programming_language|framework|database|devops|cloud|ai_ml|tool|methodology|other",
      "claimed_level": "novice|beginner|intermediate|advanced|expert",
      "years_experience": number|null,
      "context": "brief usage context"
    }
  ]
}"""

JD_SCHEMA = """{
  "job_title": "str",
  "company": "str",
  "seniority_level": "Intern|Junior|Mid|Senior|Lead",
  "summary": "1-2 sentence summary",
  "skills": [
    {
      "name": "Normalized Name",
      "category": "programming_language|framework|database|devops|cloud|ai_ml|tool|methodology|other",
      "required_level": "novice|beginner|intermediate|advanced|expert",
      "requirement_type": "required|preferred|nice_to_have"
    }
  ]
}"""


# ──────────────────────────────────────────────
# JSON Cleaning and Repair
# ──────────────────────────────────────────────

def _clean_json_response(raw: str) -> str:
    """Clean LLM response to extract valid JSON with truncation repair."""
    text = raw.strip()

    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    start = text.find("{")
    if start == -1:
        return text

    brace_count = 0
    end = -1
    in_string = False
    escape_next = False

    for i in range(start, len(text)):
        char = text[i]
        if escape_next:
            escape_next = False
            continue
        if char == '\\':
            escape_next = True
            continue
        if char == '"' and not escape_next:
            in_string = not in_string
            continue
        if in_string:
            continue
        if char == '{':
            brace_count += 1
        elif char == '}':
            brace_count -= 1
            if brace_count == 0:
                end = i
                break

    if end != -1:
        return text[start:end + 1]

    return _repair_truncated_json(text[start:])


def _repair_truncated_json(truncated: str) -> str:
    """Repair truncated JSON."""
    text = truncated.rstrip()
    for i in range(len(text) - 1, max(0, len(text) - 500), -1):
        candidate = text[:i]
        repaired = _close_json(candidate)
        try:
            json.loads(repaired)
            return repaired
        except json.JSONDecodeError:
            continue
    return truncated


def _close_json(text: str) -> str:
    """Close open JSON structures."""
    result = text.rstrip().rstrip(',')

    quote_count = 0
    escape_next = False
    for char in result:
        if escape_next:
            escape_next = False
            continue
        if char == '\\':
            escape_next = True
            continue
        if char == '"':
            quote_count += 1
    if quote_count % 2 != 0:
        result += '"'

    open_braces = 0
    open_brackets = 0
    in_string = False
    escape_next = False
    for char in result:
        if escape_next:
            escape_next = False
            continue
        if char == '\\':
            escape_next = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if char == '{':
            open_braces += 1
        elif char == '}':
            open_braces -= 1
        elif char == '[':
            open_brackets += 1
        elif char == ']':
            open_brackets -= 1

    result = result.rstrip().rstrip(',')
    result += ']' * open_brackets
    result += '}' * open_braces
    return result


# ──────────────────────────────────────────────
# Safe Enum Parsing
# ──────────────────────────────────────────────

def _safe_proficiency(value: str) -> ProficiencyLevel:
    try:
        return ProficiencyLevel(value.lower().strip())
    except (ValueError, AttributeError):
        return ProficiencyLevel.INTERMEDIATE


def _safe_category(value: str) -> SkillCategory:
    try:
        return SkillCategory(value.lower().strip())
    except (ValueError, AttributeError):
        return SkillCategory.OTHER


def _safe_requirement(value: str) -> SkillRequirementLevel:
    try:
        return SkillRequirementLevel(value.lower().strip())
    except (ValueError, AttributeError):
        return SkillRequirementLevel.REQUIRED


# ──────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────

def parse_resume_targeted(resume_text: str, target_skills: list[str]) -> ParsedResume:
    """Parse resume text looking ONLY for specific target skills."""
    from app.utils.cache import get_resume_cache_key, load_from_cache, save_to_cache
    
    # Optional: You might want to include the target_skills in the cache key now
    cache_key = get_resume_cache_key(resume_text + "".join(target_skills))
    cached = load_from_cache(cache_key)

    if cached:
        print(f"Using cached targeted resume parse: {cache_key}")
        # ... (keep existing cache loading logic) ...
        return ParsedResume(**cached)

    skills_str = ", ".join(target_skills)
    
    user_prompt = f"""Extract information from this resume for the target skills.

RESUME:
---
{resume_text}
---

Return JSON matching this schema:
{RESUME_SCHEMA}"""

    # Format the system prompt with the specific skills
    system_content = TARGETED_RESUME_PARSER_PROMPT.format(target_skills=skills_str)

    messages = [
        SystemMessage(content=system_content),
        HumanMessage(content=user_prompt),
    ]

    raw_response = call_with_retry(messages, llm_type="parsing")
    cleaned = _clean_json_response(raw_response)

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse JSON: {e}\nRaw: {raw_response[:500]}")

    save_to_cache(cache_key, data)

    skills = []
    for s in data.get("skills", []):
        skills.append(ResumeSkill(
            name=s.get("name", "Unknown"),
            category=_safe_category(s.get("category", "other")),
            aliases=s.get("aliases", []),
            claimed_level=_safe_proficiency(s.get("claimed_level", "intermediate")),
            years_experience=s.get("years_experience"),
            context=s.get("context", ""),
        ))

    return ParsedResume(
        candidate_name=data.get("candidate_name", "Unknown"),
        total_experience_years=data.get("total_experience_years"),
        current_role=data.get("current_role", ""),
        skills=skills,
        education=data.get("education", []),
        summary=data.get("summary", ""),
    )


def parse_jd(jd_text: str) -> ParsedJD:
    """Parse raw JD text into structured ParsedJD. Uses cache if available."""
    from app.utils.cache import get_jd_cache_key, load_from_cache, save_to_cache

    cache_key = get_jd_cache_key(jd_text)
    cached = load_from_cache(cache_key)

    if cached:
        print(f"Using cached JD parse: {cache_key}")
        skills = []
        for s in cached.get("skills", []):
            skills.append(JDSkill(
                name=s.get("name", "Unknown"),
                category=_safe_category(s.get("category", "other")),
                aliases=s.get("aliases", []),
                required_level=_safe_proficiency(s.get("required_level", "intermediate")),
                requirement_type=_safe_requirement(s.get("requirement_type", "required")),
            ))
        return ParsedJD(
            job_title=cached.get("job_title", ""),
            company=cached.get("company", ""),
            seniority_level=cached.get("seniority_level", ""),
            skills=skills,
            summary=cached.get("summary", ""),
        )

    user_prompt = f"""Extract all information from this job description.

JOB DESCRIPTION:
---
{jd_text}
---

Return JSON matching this schema:
{JD_SCHEMA}

Extract EVERY skill requirement. Be thorough."""

    messages = [
        SystemMessage(content=JD_PARSER_PROMPT),
        HumanMessage(content=user_prompt),
    ]

    raw_response = call_with_retry(messages, llm_type="parsing")
    cleaned = _clean_json_response(raw_response)

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse JSON: {e}\nRaw: {raw_response[:500]}")

    # Save to cache
    save_to_cache(cache_key, data)

    skills = []
    for s in data.get("skills", []):
        skills.append(JDSkill(
            name=s.get("name", "Unknown"),
            category=_safe_category(s.get("category", "other")),
            aliases=s.get("aliases", []),
            required_level=_safe_proficiency(s.get("required_level", "intermediate")),
            requirement_type=_safe_requirement(s.get("requirement_type", "required")),
        ))

    return ParsedJD(
        job_title=data.get("job_title", ""),
        company=data.get("company", ""),
        seniority_level=data.get("seniority_level", ""),
        skills=skills,
        summary=data.get("summary", ""),
    )


def parse_both(resume_text: str, jd_text: str) -> tuple[ParsedResume, ParsedJD]:
    """Parse JD first, then use its skills to do a targeted parse of the resume."""
    
    # 1. Parse JD (Extracts all requirements)
    parsed_jd = parse_jd(jd_text)
    
    # 2. Extract just the names of the required skills
    jd_skill_names = [skill.name for skill in parsed_jd.skills]
    
    # 3. Parse Resume looking ONLY for the JD skills
    parsed_resume = parse_resume_targeted(resume_text, target_skills=jd_skill_names)
    
    return parsed_resume, parsed_jd