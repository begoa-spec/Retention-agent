"""
Retention Action Agent — Strands Agents SDK core.

This agent looks at a client's churn-risk signals, decides whether a
retention action is warranted, drafts the action, and either:
  - auto-sends it (when confidence is high), or
  - flags it for human review (when confidence is low or the
    situation is judgment-heavy).

Every decision the agent makes is written to Supabase via the
record_decision tool, which is also what the dashboard reads from.
"""

from datetime import datetime, timezone
from strands import Agent, tool
from strands.models import BedrockModel

# ---------------------------------------------------------------------
# Confidence threshold — the one "settings" knob the UI exposes.
# Below this, the agent always escalates to a human, no matter how
# sure it sounds in its own reasoning.
# ---------------------------------------------------------------------
CONFIDENCE_THRESHOLD = 0.75


# ---------------------------------------------------------------------
# Tools — these are the concrete actions the agent can take. The LLM
# decides *when* to call them; the Python code decides *what happens*
# once it does.
# ---------------------------------------------------------------------

@tool
def get_client_context(client_id: str) -> dict:
    """Fetch a client's churn-risk signals and recent interaction history.

    Args:
        client_id: The Supabase client record id.

    Returns:
        A dict with risk_score, last_contact_days_ago, recent_notes,
        and payment_status.
    """
    # TODO: replace with a real Supabase query, e.g.:
    # from supabase import create_client
    # supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    # row = supabase.table("clients").select("*").eq("id", client_id).single().execute()
    # return row.data
    return {
        "client_id": client_id,
        "risk_score": 0.82,
        "last_contact_days_ago": 21,
        "recent_notes": "Client went quiet after last invoice. No reply to two check-ins.",
        "payment_status": "current",
    }


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
    status = "auto_sent" if confidence >= CONFIDENCE_THRESHOLD else "needs_review"

    record = {
        "client_id": client_id,
        "action": action,
        "message_draft": message_draft,
        "confidence": confidence,
        "reasoning": reasoning,
        "status": status,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    # TODO: replace with a real Supabase insert, e.g.:
    # supabase.table("agent_decisions").insert(record).execute()

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
    model = BedrockModel(
        model_id="anthropic.claude-3-5-sonnet-20241022-v2:0",
        temperature=0.3,
    )
    return Agent(
        model=model,
        system_prompt=SYSTEM_PROMPT,
        tools=[get_client_context, record_decision],
    )


def run_for_client(client_id: str) -> str:
    agent = build_agent()
    result = agent(f"Review client {client_id} and decide on a retention action.")
    return str(result)


if __name__ == "__main__":
    print(run_for_client("demo-client-001"))