"""
LLM client configuration.

Strategy:
- OpenRouter Nemotron 3 Super (free): parsing + analysis (20 RPM, 200 RPD)
- Groq GPT-OSS 120B: assessment chat (short prompts, fast responses)
- Fallback chain between both providers

Rate limit enforcement built in.
"""

import os
import time
import threading
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langchain_openai import ChatOpenAI

load_dotenv()


# ──────────────────────────────────────────────
# Rate Limiter
# ──────────────────────────────────────────────

class RateLimiter:
    """Thread-safe rate limiter that enforces minimum delay between calls."""

    def __init__(self, min_delay_seconds: float):
        self.min_delay = min_delay_seconds
        self.last_call = 0.0
        self.lock = threading.Lock()

    def wait(self):
        with self.lock:
            now = time.time()
            elapsed = now - self.last_call
            if elapsed < self.min_delay:
                sleep_time = self.min_delay - elapsed
                time.sleep(sleep_time)
            self.last_call = time.time()


# Groq: 30 RPM free tier -> 1 call per 2 seconds to be safe
_groq_limiter = RateLimiter(min_delay_seconds=3.0)

# OpenRouter: 20 RPM free tier -> 1 call per 4 seconds to be safe
_openrouter_limiter = RateLimiter(min_delay_seconds=4.0)


# ──────────────────────────────────────────────
# Base Constructors
# ──────────────────────────────────────────────

def get_groq_llm(
    model: str = "openai/gpt-oss-120b",
    temperature: float = 0.3,
    max_tokens: int = 4000,
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


def get_openrouter_llm(
    model: str = "openrouter/free",
    temperature: float = 0.3,
    max_tokens: int = 6000,
) -> ChatOpenAI:
    """
    Get an OpenRouter LLM instance.
    OpenRouter uses OpenAI-compatible API with a different base URL.
    """
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY not found in environment variables!")
    return ChatOpenAI(
        model=model,
        api_key=api_key,
        base_url="https://openrouter.ai/api/v1",
        temperature=temperature,
        max_tokens=max_tokens,
        default_headers={
            "HTTP-Referer": "http://localhost:8501",
            "X-Title": "Skill Assessment Agent",
        },
    )


# ──────────────────────────────────────────────
# Role-based LLM selection
# ──────────────────────────────────────────────

def get_parsing_llm() -> ChatOpenAI:
    """LLM for parsing tasks. Uses OpenRouter."""
    return get_openrouter_llm(
        temperature=0.1,
        max_tokens=4096,
    )


def get_assessment_llm() -> ChatGroq:
    """LLM for conversational assessment. Uses Groq for speed."""
    return get_groq_llm(
        model="openai/gpt-oss-120b",
        temperature=0.3,
        max_tokens=1024, # 1024 is perfect for short chat responses
    )


def get_analysis_llm() -> ChatOpenAI:
    """LLM for gap analysis and learning plan. Uses OpenRouter."""
    return get_openrouter_llm(
        temperature=0.3,
        max_tokens=8192,
    )

def get_groq_analysis_llm() -> ChatGroq:
    """High-token fallback for parsing/analysis tasks."""
    return get_groq_llm(
        model="openai/gpt-oss-120b",
        temperature=0.3,
        max_tokens=6000, # CRITICAL: Huge output limit needed for JSON parsing fallbacks
    )


# ──────────────────────────────────────────────
# Smart caller with retry and fallback
# ──────────────────────────────────────────────

def call_with_retry(messages, llm_type: str = "assessment", max_retries: int = 3):
    """
    Call an LLM with automatic retry and fallback chain.

    llm_type: "assessment" | "parsing" | "analysis"
    """
    fallback_chains = {
        "assessment": [
            ("groq", get_assessment_llm, _groq_limiter),
            ("openrouter", get_parsing_llm, _openrouter_limiter),
        ],
        "parsing": [
            ("openrouter", get_parsing_llm, _openrouter_limiter),
            ("groq", get_groq_analysis_llm, _groq_limiter), # <-- FIXED: Points to the 8000 token Groq model
        ],
        "analysis": [
            ("openrouter", get_analysis_llm, _openrouter_limiter),
            ("groq", get_groq_analysis_llm, _groq_limiter), # <-- FIXED: Points to the 8000 token Groq model
        ],
    }

    chain = fallback_chains.get(llm_type, fallback_chains["assessment"])
    last_error = None

    for provider, llm_factory, limiter in chain:
        for attempt in range(max_retries):
            try:
                # Enforce rate limit
                limiter.wait()

                llm = llm_factory()
                response = llm.invoke(messages)
                
                content = response.content
                
                # ---> THE FIX: Catch silent failures / empty strings
                if not content or not content.strip():
                    raise ValueError(f"{provider} returned an empty response.")
                    
                return content

            except Exception as e:
                last_error = e
                error_str = str(e).lower()

                # Rate limited -- wait and retry
                if any(x in error_str for x in ["rate_limit", "429", "resource_exhausted", "too many"]):
                    wait_time = (attempt + 1) * 5 # Reduced to 5/10/15 seconds so it fails over faster
                    print(
                        f"Rate limited on {provider}. "
                        f"Waiting {wait_time}s (attempt {attempt + 1}/{max_retries})..."
                    )
                    time.sleep(wait_time)
                    continue

                # Token limit -- skip to next provider immediately
                if any(x in error_str for x in ["too large", "token", "context_length"]):
                    print(f"Token limit on {provider}. Trying next provider...")
                    break

                # Other error -- retry once then next provider
                if attempt < max_retries - 1:
                    print(f"Error on {provider}: {e}. Retrying in 2s...")
                    time.sleep(2)
                    continue
                else:
                    break

    raise RuntimeError(f"All LLMs failed. Last error: {last_error}")


# ──────────────────────────────────────────────
# Backward compatibility
# ──────────────────────────────────────────────

def get_primary_llm():
    return get_assessment_llm()

def get_backup_llm():
    return get_parsing_llm()

def get_fast_llm():
    return get_assessment_llm()

def get_fallback_llm():
    return get_parsing_llm()