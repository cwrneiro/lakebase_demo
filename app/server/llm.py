"""Foundation Model API client for the 'explain this score' panel.

Gated behind the `ENABLE_LLM_EXPLAIN` env var so deployments without a serving
endpoint stay healthy. Uses the OpenAI-compatible `/serving-endpoints` route.
"""

from __future__ import annotations

import os

from openai import OpenAI

from server.config import get_oauth_token, get_workspace_host


def is_llm_enabled() -> bool:
    """Return True iff the explain panel feature flag is on."""
    return os.environ.get("ENABLE_LLM_EXPLAIN", "false").lower() == "true"


def get_serving_endpoint() -> str:
    """Return the configured Foundation Model endpoint name."""
    # Both env var names are documented in this repo (resources/app.yml ships
    # SERVING_ENDPOINT; the brief also references ENDPOINT_NAME-style configs).
    return os.environ.get("SERVING_ENDPOINT", "databricks-claude-sonnet-4-5")


def get_llm_client() -> OpenAI:
    """Return an OpenAI client pointed at Databricks `/serving-endpoints`."""
    host = get_workspace_host()
    token = get_oauth_token()
    if not token:
        raise RuntimeError("Could not obtain an OAuth token for Foundation Model API")
    return OpenAI(api_key=token, base_url=f"{host}/serving-endpoints")


def explain_score(user_context: dict) -> str:
    """Generate a 2-3 sentence rationale for a user's churn-risk score."""
    client = get_llm_client()
    endpoint = get_serving_endpoint()

    system_prompt = (
        "You are an analyst supporting customer-success operators triaging "
        "churn risk for a B2C subscription product. Given a user's score "
        "breakdown, write 2-3 plain-English sentences explaining the most "
        "likely drivers of their risk score and what an operator should "
        "consider before acting. Avoid hedging language; be concrete."
    )

    user_prompt = (
        "User score breakdown (raw signals):\n"
        f"{_format_context(user_context)}\n\n"
        "Write the rationale now."
    )

    response = client.chat.completions.create(
        model=endpoint,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=300,
        temperature=0.4,
    )
    content = response.choices[0].message.content or ""
    return content.strip()


def _format_context(ctx: dict) -> str:
    """Render the score context as `key: value` lines for the prompt."""
    lines = []
    for key, value in ctx.items():
        if value is None:
            continue
        lines.append(f"- {key}: {value}")
    return "\n".join(lines) if lines else "(no signals available)"
