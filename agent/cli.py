"""Typer CLI: ingest-url, ingest-file, chat, inspect."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import typer

from agent import inspect_cmd, paths
from agent.chat.respond import respond
from agent.chat.session import start_session


app = typer.Typer(
    add_completion=False,
    help="Company memory agent: ingest, remember, and answer.",
    no_args_is_help=True,
)


def _ensure_memory() -> None:
    paths.ensure_scaffold()


@app.command("ingest-url")
def ingest_url_cmd(url: str = typer.Argument(..., help="Homepage URL to crawl")) -> None:
    """Fetch a homepage, crawl top subpages, and ingest into memory."""
    _ensure_memory()
    from agent.ingest.url import ingest_url

    typer.echo(f"Ingesting URL: {url}")
    report = ingest_url(url)
    fetched = len(report.get("fetched", []))
    gap = len(report.get("gap_closure", []))
    typer.echo(
        f"Done. Fetched {fetched} pages ({gap} via gap-closure). "
        f"Memory at: {paths.memory_root()}"
    )


@app.command("ingest-file")
def ingest_file_cmd(path: Path = typer.Argument(..., help="File path (.pdf .docx .txt .md)")) -> None:
    """Ingest a local file (PDF / DOCX / TXT / MD) into memory."""
    _ensure_memory()
    from agent.ingest.files import ingest_file

    typer.echo(f"Ingesting file: {path}")
    result = ingest_file(str(path))
    typer.echo(f"Done. {result}")


@app.command("chat")
def chat_cmd(
    script: Optional[Path] = typer.Option(
        None,
        "--script",
        help=(
            "Non-interactive mode: read user turns from this file (one per "
            "non-empty line). Use '-' for stdin."
        ),
    ),
) -> None:
    """Start a chat session. Resets working/ memory; knowledge/ persists."""
    _ensure_memory()
    session = start_session()
    typer.echo(f"[chat] new session {session.session_id}; working/ reset.\n")

    if script is None:
        _run_interactive(session)
        return

    if str(script) == "-":
        lines = [ln.rstrip("\n") for ln in sys.stdin.readlines()]
    else:
        lines = script.read_text(encoding="utf-8").splitlines()

    for line in lines:
        msg = line.strip()
        if not msg or msg.startswith("#"):
            continue
        typer.echo(f"user> {msg}")
        reply = respond(msg, session=session)
        typer.echo(f"assistant> {reply}\n")


def _run_interactive(session) -> None:
    typer.echo("Type a question. Ctrl-D or 'quit' to exit.\n")
    while True:
        try:
            msg = input("user> ").strip()
        except (EOFError, KeyboardInterrupt):
            typer.echo("")
            break
        if not msg:
            continue
        if msg.lower() in {"quit", "exit"}:
            break
        try:
            reply = respond(msg, session=session)
        except Exception as e:
            typer.echo(f"[error] {e}")
            continue
        typer.echo(f"assistant> {reply}\n")


@app.command("inspect")
def inspect_cli(
    domain: Optional[str] = typer.Option(None, "--domain", help="Print a specific domain file"),
    changelog: bool = typer.Option(False, "--changelog", help="Print the last changelog entries"),
    working: bool = typer.Option(False, "--working", help="Print working-memory state"),
    all_domains: bool = typer.Option(False, "--all-domains", help="Dump every domain file"),
    tail: int = typer.Option(20, "--tail", help="Number of changelog lines with --changelog"),
) -> None:
    """Pretty-print JSON state for demo / debug."""
    _ensure_memory()
    any_flag = False

    if domain:
        typer.echo(inspect_cmd.inspect_domain(domain))
        any_flag = True
    if changelog:
        typer.echo(inspect_cmd.inspect_changelog(tail))
        any_flag = True
    if working:
        typer.echo(inspect_cmd.inspect_working())
        any_flag = True
    if all_domains:
        typer.echo(inspect_cmd.inspect_all_domains())
        any_flag = True

    if not any_flag:
        typer.echo(inspect_cmd.inspect_tree())
