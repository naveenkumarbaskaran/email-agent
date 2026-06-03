"""EmailAgent: uses Claude (claude-sonnet-4-6) with tool use to triage and draft email replies."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import anthropic

from .parser import EmailParser

MODEL = "claude-sonnet-4-6"

# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

READ_EMAIL_TOOL: dict[str, Any] = {
    "name": "read_email",
    "description": (
        "Read the raw content of an email. "
        "Pass a file path to a .eml file or a plain-text email body. "
        "Returns the parsed email fields: sender, subject, date, body, and any thread history."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": (
                    "Absolute or relative path to a .eml file, OR "
                    "the literal email text to parse (if no file path is given)."
                ),
            }
        },
        "required": ["path"],
    },
}

CLASSIFY_EMAIL_TOOL: dict[str, Any] = {
    "name": "classify_email",
    "description": (
        "Classify an email by category and priority. "
        "Returns a JSON object with keys: category (string), priority (high|medium|low), "
        "and summary (one-sentence summary of the email)."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "content": {
                "type": "string",
                "description": "The full email text (subject + body) to classify.",
            }
        },
        "required": ["content"],
    },
}

DRAFT_REPLY_TOOL: dict[str, Any] = {
    "name": "draft_reply",
    "description": (
        "Draft a reply to an email given the original email content and contextual information "
        "about the recipient. Returns the full text of a ready-to-send reply."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "original": {
                "type": "string",
                "description": "The original email text (subject + body).",
            },
            "context": {
                "type": "string",
                "description": (
                    "Contextual information about the person drafting the reply, e.g. "
                    "their role, organisation, or relevant background."
                ),
            },
            "tone": {
                "type": "string",
                "description": "Desired tone of the reply, e.g. 'professional', 'friendly', 'concise'.",
                "default": "professional",
            },
        },
        "required": ["original", "context"],
    },
}

TOOLS: list[dict[str, Any]] = [
    READ_EMAIL_TOOL,
    CLASSIFY_EMAIL_TOOL,
    DRAFT_REPLY_TOOL,
]


# ---------------------------------------------------------------------------
# Tool execution helpers
# ---------------------------------------------------------------------------


def _execute_read_email(path: str) -> str:
    """Read and parse an email from a file path or inline text."""
    parser = EmailParser()
    p = Path(path)
    if p.exists() and p.suffix.lower() == ".eml":
        parsed = parser.parse_file(str(p))
    else:
        # treat `path` as raw email text
        parsed = parser.parse_text(path)

    lines = [
        f"From: {parsed.get('sender', 'Unknown')}",
        f"Subject: {parsed.get('subject', '(no subject)')}",
        f"Date: {parsed.get('date', 'Unknown')}",
        "",
        parsed.get("body", ""),
    ]
    if parsed.get("thread"):
        lines += ["", "--- Thread history ---", parsed["thread"]]
    return "\n".join(lines)


def _execute_classify_email(content: str, client: anthropic.Anthropic) -> str:
    """Classify an email using a focused Claude call."""
    classify_prompt = (
        "You are an email classification assistant. "
        "Given the following email, respond ONLY with a JSON object containing:\n"
        "  - category: a short label such as 'work', 'personal', 'sales', "
        "'support', 'newsletter', 'urgent', 'finance', 'hr', 'security', 'other'\n"
        "  - priority: one of 'high', 'medium', 'low'\n"
        "  - summary: a single sentence summarising the email\n\n"
        f"Email:\n{content}\n\n"
        "Respond with valid JSON only, no markdown fences."
    )
    resp = client.messages.create(
        model=MODEL,
        max_tokens=256,
        messages=[{"role": "user", "content": classify_prompt}],
    )
    raw = ""
    for block in resp.content:
        if block.type == "text":
            raw = block.text.strip()
            break
    # Validate JSON is parseable before returning
    try:
        json.loads(raw)
    except json.JSONDecodeError:
        raw = json.dumps(
            {"category": "other", "priority": "medium", "summary": raw[:200]}
        )
    return raw


def _execute_draft_reply(
    original: str,
    context: str,
    tone: str,
    client: anthropic.Anthropic,
) -> str:
    """Draft a contextual reply using Claude."""
    draft_prompt = (
        f"You are drafting an email reply on behalf of someone with the following context:\n"
        f"{context}\n\n"
        f"Tone: {tone}\n\n"
        f"Original email:\n{original}\n\n"
        "Write a complete, ready-to-send reply. Include a greeting and sign-off. "
        "Do NOT include a subject line or email headers — just the body text."
    )
    resp = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": draft_prompt}],
    )
    for block in resp.content:
        if block.type == "text":
            return block.text.strip()
    return "(no reply generated)"


# ---------------------------------------------------------------------------
# EmailAgent
# ---------------------------------------------------------------------------


class EmailAgent:
    """An AI agent for email triage and reply drafting.

    Uses Claude via the Anthropic SDK with a manual tool-use loop.
    Three tools are available:
        - read_email   : parse a .eml file or raw text
        - classify_email: categorise + prioritise an email
        - draft_reply  : write a contextual reply
    """

    def __init__(self, api_key: str | None = None) -> None:
        self._client = anthropic.Anthropic(
            api_key=api_key or os.environ.get("ANTHROPIC_API_KEY")
        )

    # ------------------------------------------------------------------
    # Internal: tool dispatcher
    # ------------------------------------------------------------------

    def _dispatch_tool(self, name: str, tool_input: dict[str, Any]) -> str:
        if name == "read_email":
            return _execute_read_email(tool_input["path"])
        elif name == "classify_email":
            return _execute_classify_email(tool_input["content"], self._client)
        elif name == "draft_reply":
            return _execute_draft_reply(
                original=tool_input["original"],
                context=tool_input.get("context", ""),
                tone=tool_input.get("tone", "professional"),
                client=self._client,
            )
        else:
            return f"Unknown tool: {name}"

    # ------------------------------------------------------------------
    # Internal: agentic loop
    # ------------------------------------------------------------------

    def _run(self, user_message: str) -> str:
        """Run the agentic loop and return the final text response."""
        messages: list[dict[str, Any]] = [
            {"role": "user", "content": user_message}
        ]

        system = (
            "You are an expert email assistant. "
            "You have three tools available: read_email, classify_email, and draft_reply. "
            "Use them in sequence as needed to fulfil the user's request. "
            "Always start by reading the email if a file path or raw text is given, "
            "then classify it, and draft a reply when requested."
        )

        while True:
            response = self._client.messages.create(
                model=MODEL,
                max_tokens=2048,
                system=system,
                tools=TOOLS,
                messages=messages,
            )

            # Append assistant turn
            messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason == "end_turn":
                # Extract the final text
                for block in response.content:
                    if block.type == "text":
                        return block.text.strip()
                return "(no text response)"

            if response.stop_reason != "tool_use":
                # Unexpected stop reason — return whatever text we have
                for block in response.content:
                    if block.type == "text":
                        return block.text.strip()
                return f"Stopped with reason: {response.stop_reason}"

            # Execute all requested tool calls
            tool_results: list[dict[str, Any]] = []
            for block in response.content:
                if block.type == "tool_use":
                    result_text = self._dispatch_tool(block.name, block.input)
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result_text,
                        }
                    )

            if tool_results:
                messages.append({"role": "user", "content": tool_results})

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def triage(self, email_path: str, context: str = "") -> dict[str, Any]:
        """Read an email, classify it, and return a triage report.

        Args:
            email_path: Path to a .eml file or raw email text.
            context: Optional context about the recipient (role, background).

        Returns:
            A dict with keys: sender, subject, category, priority, summary, raw.
        """
        ctx_note = f" Context about me: {context}" if context else ""
        prompt = (
            f"Please triage the following email.{ctx_note}\n\n"
            f"Step 1 — Read the email using the read_email tool with path: {email_path}\n"
            "Step 2 — Classify the email using classify_email.\n"
            "Step 3 — Present the triage results in a clear, structured format."
        )
        final_text = self._run(prompt)
        return {"triage_report": final_text, "email_path": email_path}

    def draft(self, email_path: str, context: str = "", tone: str = "professional") -> dict[str, Any]:
        """Read an email, classify it, and draft a contextual reply.

        Args:
            email_path: Path to a .eml file or raw email text.
            context: Context about the person writing the reply.
            tone: Desired tone — e.g. 'professional', 'friendly', 'concise'.

        Returns:
            A dict with keys: draft, triage_report, email_path.
        """
        ctx_note = f" Context about me: {context}" if context else ""
        prompt = (
            f"Please read, triage, and draft a reply to the following email.{ctx_note}\n\n"
            f"Step 1 — Read the email using the read_email tool with path: {email_path}\n"
            "Step 2 — Classify the email using classify_email.\n"
            f"Step 3 — Draft a {tone} reply using the draft_reply tool, "
            "passing the full email text as 'original' and my context as 'context'.\n"
            "Step 4 — Present the final draft clearly."
        )
        final_text = self._run(prompt)
        return {"draft": final_text, "email_path": email_path, "tone": tone}
