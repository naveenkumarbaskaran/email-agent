# email-agent-ai

AI-powered email triage and reply drafting, powered by [Claude](https://www.anthropic.com/claude) (`claude-sonnet-4-6`) via the Anthropic Python SDK.

## Features

- **Parse** `.eml` files or raw email text (RFC 2822, multipart, quoted threads)
- **Classify** emails by category (`work`, `support`, `sales`, `personal`, …) and priority (`high`, `medium`, `low`)
- **Draft** contextual, tone-aware replies
- **CLI** with rich terminal output
- **Agentic tool-use loop** — the agent calls `read_email`, `classify_email`, and `draft_reply` tools as needed

## Installation

```bash
pip install email-agent-ai
# or, from source:
pip install -e .
```

Set your Anthropic API key:

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

## CLI Usage

### Triage an email

```bash
email-agent triage path/to/message.eml --context "I am an SAP engineer"
```

### Draft a reply

```bash
email-agent draft path/to/message.eml --tone professional --context "I am a senior support engineer"
```

### Read from stdin

```bash
cat message.eml | email-agent triage -
echo "Hi, can we reschedule tomorrow's meeting?" | email-agent draft - --context "I am a project manager"
```

### Available tones

`professional` (default) · `friendly` · `concise` · `formal` · `casual`

## Python API

```python
from email_agent import EmailAgent

agent = EmailAgent()  # reads ANTHROPIC_API_KEY from environment

# Triage
result = agent.triage("inbox/support_request.eml", context="I am an SAP engineer")
print(result["triage_report"])

# Draft a reply
result = agent.draft(
    "inbox/meeting_invite.eml",
    context="I am a project manager at Acme Corp",
    tone="professional",
)
print(result["draft"])
```

### EmailAgent methods

| Method | Arguments | Returns |
|--------|-----------|--------|
| `triage(email_path, context="")` | path to `.eml` or raw text, optional context | `{"triage_report": str, "email_path": str}` |
| `draft(email_path, context="", tone="professional")` | path / text, context, tone | `{"draft": str, "email_path": str, "tone": str}` |

## EmailParser

You can use the parser independently:

```python
from email_agent import EmailParser

parser = EmailParser()

# From a .eml file
parsed = parser.parse_file("message.eml")
print(parsed["sender"])   # From: header
print(parsed["subject"])  # Subject: header
print(parsed["body"])     # Plain-text body
print(parsed["thread"])   # Quoted/forwarded thread (if any)

# From raw text
parsed = parser.parse_text(raw_email_string)
```

Returned dictionary keys: `sender`, `to`, `subject`, `date`, `body`, `html`, `thread`, `raw`, and `file_path` (only when using `parse_file`).

## How It Works

The `EmailAgent` uses Claude's [tool use](https://docs.anthropic.com/en/docs/tool-use) capability with a manual agentic loop:

1. The user sends a request ("triage this email" / "draft a reply").
2. Claude decides which tools to call (`read_email` → `classify_email` → `draft_reply`).
3. The agent executes each tool and feeds the results back to Claude.
4. The loop continues until Claude returns a final `end_turn` response.

```
User prompt
    │
    ▼
 EmailAgent._run()
    │
    ├─► Claude (tool_use: read_email)
    │       │ result → parsed email text
    ├─► Claude (tool_use: classify_email)
    │       │ result → {category, priority, summary}
    ├─► Claude (tool_use: draft_reply)   ← only for draft command
    │       │ result → reply text
    └─► Claude (end_turn) → final response
```

## Project Structure

```
email_agent/
    __init__.py    — package exports
    agent.py       — EmailAgent class + tool definitions + agentic loop
    parser.py      — EmailParser class (.eml / RFC 2822 parsing)
    cli.py         — Click CLI (triage + draft commands)
pyproject.toml
README.md
```

## Environment Variables

| Variable | Description |
|----------|-------------|
| `ANTHROPIC_API_KEY` | Your Anthropic API key (required) |

## Development

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Lint
ruff check email_agent/

# Type-check
mypy email_agent/

# Tests
pytest
```

## License

MIT
