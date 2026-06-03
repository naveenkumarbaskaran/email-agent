"""Command-line interface for email-agent-ai.

Commands:
    triage <email>  — classify and prioritise an email
    draft  <email>  — classify and draft a reply

Examples:
    email-agent triage inbox/message.eml --context "I am an SAP engineer"
    email-agent draft  inbox/message.eml --tone friendly --context "I work in customer support"
    echo "Hi, can we reschedule?" | email-agent triage -
"""

from __future__ import annotations

import sys

import click
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

from .agent import EmailAgent

console = Console()


# ---------------------------------------------------------------------------
# CLI group
# ---------------------------------------------------------------------------


@click.group()
@click.version_option(package_name="email-agent-ai")
def cli() -> None:
    """email-agent-ai — AI-powered email triage and reply drafting."""


# ---------------------------------------------------------------------------
# triage command
# ---------------------------------------------------------------------------


@cli.command("triage")
@click.argument("email_path")
@click.option(
    "--context",
    "-c",
    default="",
    show_default=False,
    help="Context about you, e.g. your role or background.",
)
@click.option(
    "--api-key",
    envvar="ANTHROPIC_API_KEY",
    default=None,
    help="Anthropic API key (defaults to ANTHROPIC_API_KEY env var).",
)
def triage_cmd(email_path: str, context: str, api_key: str | None) -> None:
    """Classify and prioritise an email.

    EMAIL_PATH can be a path to a .eml file or '-' to read from stdin.
    """
    email_input = _resolve_input(email_path)

    with console.status("[bold green]Triaging email…", spinner="dots"):
        agent = EmailAgent(api_key=api_key)
        try:
            result = agent.triage(email_input, context=context)
        except Exception as exc:
            console.print(f"[bold red]Error:[/bold red] {exc}")
            sys.exit(1)

    console.print()
    console.print(
        Panel(
            Markdown(result["triage_report"]),
            title="[bold cyan]Email Triage Report[/bold cyan]",
            border_style="cyan",
            expand=False,
        )
    )


# ---------------------------------------------------------------------------
# draft command
# ---------------------------------------------------------------------------


@cli.command("draft")
@click.argument("email_path")
@click.option(
    "--context",
    "-c",
    default="",
    show_default=False,
    help="Context about you, e.g. your role or background.",
)
@click.option(
    "--tone",
    "-t",
    default="professional",
    show_default=True,
    type=click.Choice(
        ["professional", "friendly", "concise", "formal", "casual"],
        case_sensitive=False,
    ),
    help="Tone of the reply.",
)
@click.option(
    "--api-key",
    envvar="ANTHROPIC_API_KEY",
    default=None,
    help="Anthropic API key (defaults to ANTHROPIC_API_KEY env var).",
)
def draft_cmd(
    email_path: str, context: str, tone: str, api_key: str | None
) -> None:
    """Draft a contextual reply to an email.

    EMAIL_PATH can be a path to a .eml file or '-' to read from stdin.
    """
    email_input = _resolve_input(email_path)

    with console.status("[bold green]Drafting reply…", spinner="dots"):
        agent = EmailAgent(api_key=api_key)
        try:
            result = agent.draft(email_input, context=context, tone=tone)
        except Exception as exc:
            console.print(f"[bold red]Error:[/bold red] {exc}")
            sys.exit(1)

    console.print()

    # Meta table
    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_row("[bold]Email[/bold]", result["email_path"])
    table.add_row("[bold]Tone[/bold]", result["tone"])
    console.print(table)
    console.print()

    console.print(
        Panel(
            result["draft"],
            title="[bold green]Draft Reply[/bold green]",
            border_style="green",
            expand=False,
        )
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_input(email_path: str) -> str:
    """Return a file path or inline text depending on the argument.

    If email_path is '-', read the email body from stdin.
    Otherwise return the path as-is (the agent handles file vs text logic).
    """
    if email_path == "-":
        console.print("[dim]Reading email from stdin…[/dim]")
        return sys.stdin.read()
    return email_path


def main() -> None:
    """Entry point registered in pyproject.toml."""
    cli()


if __name__ == "__main__":
    main()
