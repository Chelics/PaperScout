import os
import re
import sys
from datetime import date
from hashlib import sha1
from pathlib import Path

import click
from dotenv import load_dotenv

load_dotenv()

_AUTO_BIB = "__auto__"
_AUTO_OUT = "__auto_out__"


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    val = raw.strip().lower()
    if val in {"1", "true", "yes", "y", "on"}:
        return True
    if val in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def _format_cost_summary(stats: dict) -> str:
    iterations = int(stats.get("iterations", 0) or 0)
    input_tokens = int(stats.get("input_tokens", 0) or 0)
    output_tokens = int(stats.get("output_tokens", 0) or 0)

    parts = [
        f"{iterations} iterations",
        f"{input_tokens:,} input + {output_tokens:,} output tokens",
    ]

    return "[done] " + " | ".join(parts)


def _slugify_topic(topic: str) -> str:
    raw = topic.strip().lower()
    raw = re.sub(r"\s+", "-", raw)
    raw = re.sub(r"[^a-z0-9-]+", "-", raw)
    raw = re.sub(r"-{2,}", "-", raw).strip("-")
    if not raw:
        h = sha1(topic.encode("utf-8")).hexdigest()[:8]
        return f"topic-{h}"
    return raw[:60]


def _default_report_path(topic: str) -> Path:
    slug = _slugify_topic(topic)
    return Path("reports") / f"{date.today().isoformat()}_{slug}.md"


def _ensure_unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    for i in range(2, 1000):
        cand = parent / f"{stem}_{i}{suffix}"
        if not cand.exists():
            return cand
    return parent / f"{stem}_{sha1(str(path).encode('utf-8')).hexdigest()[:8]}{suffix}"


def _resolve_output_path(output: str, topic: str) -> Path:
    if output == _AUTO_OUT:
        return _ensure_unique_path(_default_report_path(topic)).expanduser().resolve()
    return Path(output).expanduser().resolve()


@click.group()
def cli():
    """PaperScout - Search and analyze academic papers from arXiv."""
    pass


@cli.command()
@click.argument("topic")
@click.option(
    "--limit",
    default=10,
    type=click.IntRange(1, 50),
    show_default=True,
    help="Number of papers to include in the report.",
)
@click.option(
    "--output",
    default=_AUTO_OUT,
    type=click.Path(),
    show_default="reports/<date>_<topic>.md",
    help="Output file path for the Markdown report.",
)
@click.option(
    "--bibtex",
    is_flag=False,
    flag_value=_AUTO_BIB,
    default=None,
    metavar="PATH",
    help="Also write a BibTeX file. Omit PATH to use <output>.bib.",
)
@click.option(
    "--max-iterations",
    default=_env_int("PAPERSCOUT_MAX_ITERATIONS", 15),
    type=click.IntRange(1, 100),
    show_default=True,
    help="Maximum agent iterations before failing.",
)
@click.option(
    "--cost-summary/--no-cost-summary",
    default=_env_bool("PAPERSCOUT_COST_SUMMARY", True),
    show_default=True,
    help="Print token summary when finished.",
)
@click.option(
    "--report-mode",
    type=click.Choice(["strict", "light"], case_sensitive=False),
    default=os.environ.get("PAPERSCOUT_REPORT_MODE", "strict"),
    show_default=True,
    help="Report style: strict follows the report skill format; light is shorter and more flexible.",
)
@click.option(
    "--mode",
    type=click.Choice(["survey", "trending"], case_sensitive=False),
    default=os.environ.get("PAPERSCOUT_MODE", "survey"),
    show_default=True,
    help="Search profile: survey emphasizes coverage and foundational work; trending emphasizes recency.",
)
@click.option(
    "--domain",
    default=os.environ.get("PAPERSCOUT_DOMAIN", ""),
    show_default=True,
    help="Domain category for organizing papers and notes (e.g., CV, NLP, ML).",
)
@click.option(
    "--verbose",
    is_flag=True,
    help="Show agent tool calls as they happen.",
)
def search(
    topic: str,
    limit: int,
    output: str,
    bibtex: str | None,
    max_iterations: int,
    cost_summary: bool,
    report_mode: str,
    mode: str,
    domain: str,
    verbose: bool,
):
    """Search arXiv for papers on TOPIC and generate a Markdown report."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        click.echo(
            "Error: ANTHROPIC_API_KEY is not set.\n"
            "Add it to a .env file in the current directory:\n"
            "  ANTHROPIC_API_KEY=your_key_here\n"
            "  ANTHROPIC_MODEL=claude-sonnet-4-6\n"
            "  ANTHROPIC_BASE_URL=https://api.anthropic.com",
            err=True,
        )
        sys.exit(1)

    click.echo(f"Searching arXiv for: {topic!r} (limit={limit})", err=True)

    output_path_obj: Path | None = None
    bib_path_obj: Path | None = None
    try:
        from .agent import run_agent
        from .report import normalize_report_markdown, write_bibtex, write_report

        report, papers, stats = run_agent(
            topic=topic,
            limit=limit,
            verbose=verbose,
            max_iterations=max_iterations,
            report_mode=report_mode,
            mode=mode,
            domain=domain,
        )
        report = normalize_report_markdown(report, report_mode=report_mode)

        output_path_obj = _resolve_output_path(output, topic)
        output_path_obj.parent.mkdir(parents=True, exist_ok=True)
        write_report(report, str(output_path_obj))
        click.echo(f"Report written to: {output_path_obj}", err=True)

        if bibtex is not None:
            bib_path_obj = output_path_obj.with_suffix(".bib") if bibtex == _AUTO_BIB else Path(bibtex).expanduser().resolve()
            bib_path_obj.parent.mkdir(parents=True, exist_ok=True)
            write_bibtex(papers, str(bib_path_obj))
            click.echo(f"BibTeX written to: {bib_path_obj}", err=True)

        if cost_summary:
            click.echo(_format_cost_summary(stats), err=True)

    except PermissionError:
        target = bib_path_obj or output_path_obj or Path(output).expanduser()
        click.echo(f"Error: Cannot write to '{target}'. Check file permissions.", err=True)
        sys.exit(1)
    except RuntimeError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        # Handle Anthropic API errors by inspecting the class name to avoid
        # hard dependency on anthropic exception types at import time
        err_type = type(e).__name__
        if err_type == "AuthenticationError":
            click.echo("Error: Invalid API key. Check ANTHROPIC_API_KEY in your .env file.", err=True)
        elif err_type == "RateLimitError":
            click.echo("Error: Rate limit reached. Wait a moment and try again.", err=True)
        elif err_type == "APIStatusError":
            click.echo(f"Error: Anthropic API error ({getattr(e, 'status_code', '?')}): {e}", err=True)
        else:
            click.echo(f"Unexpected error ({err_type}): {e}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    cli()
