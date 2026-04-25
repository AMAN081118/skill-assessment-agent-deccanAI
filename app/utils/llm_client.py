"""
LLM client configuration.
Smart routing with rate limit awareness and retry logic.

Strategy:
- Groq GPT-OSS 120B: conversational assessment (short prompts, fast)
- Gemini 2.5 Flash: parsing (large input, structured output)
- Gemini 2.5 Flash-Lite: learning plan generation (high RPD quota)
- Gemini 2.5 Pro: fallback for complex reasoning

Key insight: Groq cached tokens don't count toward rate limits,
so we benefit from consistent system prompts.
"""

import os
import time
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langchain_google_genai import ChatGoogleGenerativeAI

load_dotenv()

# ──────────────────────────────────────────────
# Rate limit tracking
# ──────────────────────────────────────────────

_last_groq_call = 0.0
_last_gemini_call = 0.0
GROQ_MIN_DELAY = 3.0       # seconds between Groq calls (stay under 30 RPM)
GEMINI_MIN_DELAY = 7.0     # seconds between Gemini calls (stay under 10 RPM)


def _wait_for_groq():
    """Enforce minimum delay between Groq API calls."""
    global _last_groq_call
    now = time.time()
    elapsed = now - _last_groq_call
    if elapsed < GROQ_MIN_DELAY:
        time.sleep(GROQ_MIN_DELAY - elapsed)
    _last_groq_call = time.time()


def _wait_for_gemini():
    """Enforce minimum delay between Gemini API calls."""
    global _last_gemini_call
    now = time.time()
    elapsed = now - _last_gemini_call
    if elapsed < GEMINI_MIN_DELAY:
        time.sleep(GEMINI_MIN_DELAY - elapsed)
    _last_gemini_call = time.time()


# ──────────────────────────────────────────────
# Base constructors
# ──────────────────────────────────────────────

def get_groq_llm(
    model: str = "openai/gpt-oss-120b",
    temperature: float = 0.3,
    max_tokens: int = 2048,
) -> ChatGroq:
    """Get a Groq LLM instance."""
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY not found in environment variables!")
    return ChatGroq(
        model=model,
        api_key=api_key,
        temperature=temperature,
        max_tokens=max_tokens,
    )


def get_gemini_llm(
    model: str = "gemini-2.5-flash",
    temperature: float = 0.3,
    max_tokens: int = 8192,
) -> ChatGoogleGenerativeAI:
    """Get a Google Gemini LLM instance."""
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("GOOGLE_API_KEY not found in environment variables!")
    return ChatGoogleGenerativeAI(
        model=model,
        google_api_key=api_key,
        temperature=temperature,
        max_output_tokens=max_tokens,
    )


# ──────────────────────────────────────────────
# Role-based LLM selection
# ──────────────────────────────────────────────

def get_parsing_llm() -> ChatGoogleGenerativeAI:
    """
    LLM for parsing tasks (resume + JD extraction).
    Uses Gemini 2.5 Flash -- good balance of quality and RPD.
    """
    return get_gemini_llm(
        model="gemini-2.5-flash",
        temperature=0.1,
        max_tokens=8192,
    )


def get_assessment_llm() -> ChatGroq:
    """
    LLM for conversational assessment.
    Uses Groq GPT-OSS 120B -- fast responses for chat.
    Short prompts keep within 6K TPM limit.
    """
    return get_groq_llm(
        model="openai/gpt-oss-120b",
        temperature=0.3,
        max_tokens=1024,  # keep output short to save TPM
    )


def get_analysis_llm() -> ChatGoogleGenerativeAI:
    """
    LLM for learning plan generation.
    Uses Gemini 2.5 Flash-Lite -- highest RPD (1000/day) on free tier.
    """
    return get_gemini_llm(
        model="gemini-2.5-flash-lite",
        temperature=0.3,
        max_tokens=8192,
    )


def get_fallback_llm() -> ChatGoogleGenerativeAI:
    """
    Fallback LLM for when other models fail.
    Uses Gemini 2.5 Pro -- 100 RPD but strongest reasoning.
    """
    return get_gemini_llm(
        model="gemini-2.5-pro",
        temperature=0.3,
        max_tokens=8192,
    )


# ──────────────────────────────────────────────
# Smart caller with retry and fallback
# ──────────────────────────────────────────────

def call_with_retry(messages, llm_type: str = "assessment", max_retries: int = 3):
    """
    Call an LLM with automatic retry and fallback chain.

    llm_type: "assessment" | "parsing" | "analysis"

    Fallback chain:
    - assessment: Groq -> Gemini Flash -> Gemini Pro
    - parsing: Gemini Flash -> Gemini Flash-Lite -> Gemini Pro
    - analysis: Gemini Flash-Lite -> Gemini Flash -> Gemini Pro
    """
    fallback_chains = {
        "assessment": [
            ("groq", get_assessment_llm),
            ("gemini", get_parsing_llm),
            ("gemini", get_fallback_llm),
        ],
        "parsing": [
            ("gemini", get_parsing_llm),
            ("gemini", get_analysis_llm),
            ("gemini", get_fallback_llm),
        ],
        "analysis": [
            ("gemini", get_analysis_llm),
            ("gemini", get_parsing_llm),
            ("gemini", get_fallback_llm),
        ],
    }

    chain = fallback_chains.get(llm_type, fallback_chains["assessment"])

    last_error = None

    for provider, llm_factory in chain:
        for attempt in range(max_retries):
            try:
                # Enforce rate limits
                if provider == "groq":
                    _wait_for_groq()
                else:
                    _wait_for_gemini()

                llm = llm_factory()
                response = llm.invoke(messages)
                return response.content

            except Exception as e:
                last_error = e
                error_str = str(e).lower()

                # If rate limited, wait and retry
                if "rate_limit" in error_str or "429" in error_str or "resource_exhausted" in error_str:
                    wait_time = (attempt + 1) * 10  # 10s, 20s, 30s
                    print(
                        f"Rate limited on {provider}. "
                        f"Waiting {wait_time}s before retry {attempt + 1}/{max_retries}..."
                    )
                    time.sleep(wait_time)
                    continue

                # If token limit exceeded, try next model in chain
                if "too large" in error_str or "token" in error_str:
                    print(f"Token limit on {provider}. Trying next model...")
                    break

                # Other errors -- retry once then move to next
                if attempt == 0:
                    print(f"Error on {provider}: {e}. Retrying...")
                    time.sleep(2)
                    continue
                else:
                    break

    raise RuntimeError(f"All LLMs failed. Last error: {last_error}")


# ──────────────────────────────────────────────
# Backward compatibility
# ──────────────────────────────────────────────

def get_primary_llm() -> ChatGroq:
    return get_assessment_llm()

def get_backup_llm() -> ChatGoogleGenerativeAI:
    return get_parsing_llm()

def get_fast_llm() -> ChatGroq:
    return get_assessment_llm()