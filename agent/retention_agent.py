"""
Retention Action Agent — Strands Agents SDK core.

This agent looks at a client's churn-risk signals, decides whether a
retention action is warranted, drafts the action, and either:
  - auto-sends it (when confidence is high), or
  - flags it for human review (when confidence is low or the
    situation is judgment-heavy).

Every decision the agent makes is written to Supabase via the
record_decision tool, which is also what the dashboard reads from.

Includes basic production safeguards:
  - fails fast with a clear error if required env vars are missing
  - a daily call cap to protect your API spend
  - a duplicate-decision guard so the same client isn't re-reviewed
    (and re-billed) within a short window for no reason
"""

import os
import sys
from datetime import datetime, timezone, date, timedelta
from strands import Agent, tool
from strands.models.litellm import LiteLLMModel
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

# ---------------------------------------------------------------------
# Fail fast on missing config, instead of a confusing error later.
# ---------------------------------------------------------------------
REQUIRED_ENV = ["GROQ_API_KEY", "SUPABASE_URL", "SUPABASE_KEY"]
missing = [key for key in REQUIRED_ENV if not os.getenv(key)]
if missing:
    sys.exit(
        f"Missing required environment variable(s): {', '.join(missing)}\n"
        f"Add them to your .env file before running this."
    )

supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

# ---------------------------------------------------------------------
# Confidence threshold — read live from Supabase so the dashboard's
# Settings page actually controls behavior, not just a display value.
# Falls back to 0.75 if the settings table is empty or unreachable.
# ---------------------------------------------------------------------
DEFAULT_CONFIDENCE_THRESHOLD = 0.75


def get_confidence_threshold() -> float:
    try:
        result = supabase.table("settings").select("confidence_threshold").limit(1).execute()
        if result.data:
            return result.data[0]["confidence_threshold"]
    except Exception:
        pass
    return DEFAULT_CONFIDENCE_THRESHOLD

# ---------------------------------------------------------------------
# Spend guard — protects your API budget from runaway usage. Adjust
# this cap based on your budget: at roughly $0.01-0.02 per call, 100
# calls/day is well under $2/day even on the high end.
# ---------------------------------------------------------------------
MAX_DAILY_CALLS = 100

# Don't re-review the same client more than once within this window,
# to avoid redundant API spend when nothing's likely changed.
DUPLICATE_GUARD_HOURS = 12


def _check_and_increment_daily_usage() -> None:
    today = date.today().isoformat()
    existing = (
        supabase.table("agent_usage").select("*").eq("call_date", today).execute()
    )

    if existing.data:
        row = existing.data[0]
        if row["call_count"] >= MAX_DAILY_CALLS:
            raise RuntimeError(
                f"Daily call limit reached ({MAX_DAILY_CALLS}). "
                f"Refusing to call the model again today to protect your budget."
            )
        supabase.table("agent_usage").update(
            {"call_count": row["call_count"] + 1}
        ).eq("id", row["id"]).execute()
    else:
        supabase.table("agent_usage").insert(
            {"call_date": today, "call_count": 1}
        ).execute()


def _recently_reviewed(client_id: str) -> bool:
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=DUPLICATE_GUARD_HOURS)).isoformat()
    recent = (
        supabase.table("agent_decisions")
        .select("id")
        .eq("client_id", client_id)
        .gte("created_at", cutoff)
        .execute()
    )
    return len(recent.data) > 0


# ---------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------

@tool
def get_client_context(client_id: str) -> dict:
    """Fetch a client's churn-risk signals and recent interaction history.

    Args:
        client_id: The Supabase client record id (UUID).

    Returns:
        A dict with risk_score, last_contact_days_ago, recent_notes,
        and payment_status.
    """
    result = supabase.table("clients").select("*").eq("id", client_id).single().execute()
    return result.data


@tool
def record_decision(
    client_id: str,
    action: str,
    message_draft: str,
    confidence: float,
    reasoning: str,
) -> dict:
    """Record the agent's final decision for a client.

    Call this exactly once, after you've gathered context and decided
    what to do. This is how your decision reaches the dashboard.

    Args:
        client_id: The client this decision is about.
        action: One of "send_message", "schedule_call", "no_action".
        message_draft: The drafted retention message (empty string if
            action is "no_action").
        confidence: Your confidence in this decision, 0.0 to 1.0.
        reasoning: A short (1-2 sentence) explanation a human could
            skim to understand why you decided this.

    Returns:
        The final routed decision, including whether it was auto-sent
        or escalated for review.
    """
    threshold = get_confidence_threshold()
    status = "auto_sent" if confidence >= threshold else "needs_review"

    record = {
        "client_id": client_id,
        "action": action,
        "message_draft": message_draft,
        "confidence": confidence,
        "reasoning": reasoning,
        "status": status,
    }

    supabase.table("agent_decisions").insert(record).execute()

    return record


# ---------------------------------------------------------------------
# The agent itself
# ---------------------------------------------------------------------

SYSTEM_PROMPT = """You are a retention action agent for a freelance
consultant's client book. For each client you're asked about:

1. Call get_client_context to understand their situation.
2. Decide if a retention action is warranted right now, and if so what
   kind (a check-in message, a call, or no action if things look fine).
3. If action is warranted, draft it in the consultant's voice: warm,
   direct, no corporate filler.
4. Call record_decision exactly once with your action, draft, an honest
   confidence score, and your reasoning.

Be conservative with confidence. Only score above 0.75 when the
situation is unambiguous (e.g. a routine check-in with no sensitive
context). Anything involving a complaint, a payment dispute, or mixed
signals should score low — a human should make that call, not you.
"""


def build_agent() -> Agent:
    model = LiteLLMModel(
        client_args={"api_key": os.getenv("GROQ_API_KEY")},
        model_id="groq/openai/gpt-oss-120b",
        params={"temperature": 0.3, "max_tokens": 1024},
    )
    return Agent(
        model=model,
        system_prompt=SYSTEM_PROMPT,
        tools=[get_client_context, record_decision],
    )


def run_for_client(client_id: str) -> str:
    if _recently_reviewed(client_id):
        return (
            f"Skipped: client {client_id} was already reviewed within the last "
            f"{DUPLICATE_GUARD_HOURS} hours. No new decision needed."
        )

    _check_and_increment_daily_usage()

    agent = build_agent()
    result = agent(f"Review client {client_id} and decide on a retention action.")
    return str(result)


if __name__ == "__main__":
    # Replace with a real client UUID copied from your Supabase
    # Table Editor (clients table).
    test_client_id = "14cb549a-e1c0-423f-b886-5e5f1fac4bf1"
    print(run_for_client(test_client_id))