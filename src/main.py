"""Main CLI entry point for the newsletter outreach automation tool."""

import logging
import os
import sys
from pathlib import Path
from typing import Optional

import click
from dotenv import load_dotenv

from .drafter import EmailDrafter
from .email_finder import EmailFinder
from .gmail_client import GmailClient
from .parser import NewsletterParser

logger = logging.getLogger(__name__)


def setup_logging(verbose: bool = False, log_file: Optional[str] = None) -> None:
    """Configure logging for the application."""
    level = logging.DEBUG if verbose else logging.INFO
    format_str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    handlers = [logging.StreamHandler(sys.stdout)]
    if log_file:
        handlers.append(logging.FileHandler(log_file))

    logging.basicConfig(level=level, format=format_str, handlers=handlers)


def get_env(key: str, default: str = "") -> str:
    """Get environment variable with optional default."""
    return os.getenv(key, default)


def get_env_float(key: str, default: float) -> float:
    """Get environment variable as float."""
    value = os.getenv(key)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def get_env_int(key: str, default: int) -> int:
    """Get environment variable as int."""
    value = os.getenv(key)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


@click.command()
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose logging")
@click.option("--dry-run", is_flag=True, help="Don't create drafts, just show what would be done")
@click.option("--max-emails", "-n", default=10, help="Maximum number of emails to process")
def cli(verbose: bool, dry_run: bool, max_emails: int) -> None:
    """Process Axios Pro Rata newsletters and create outreach drafts."""
    # Load environment variables from .env file
    env_path = Path(__file__).parent.parent / ".env"
    if not env_path.exists():
        example_path = Path(__file__).parent.parent / ".env.example"
        if example_path.exists():
            click.echo(
                f"Error: .env file not found.\n"
                f"Copy .env.example to .env and fill in your credentials.",
                err=True,
            )
        else:
            click.echo("Error: .env file not found.", err=True)
        sys.exit(1)

    load_dotenv(env_path)

    # Validate required environment variables
    if not get_env("GROK_API_KEY"):
        click.echo("Error: GROK_API_KEY is not set in .env file", err=True)
        sys.exit(1)

    setup_logging(
        verbose=verbose,
        log_file=get_env("LOG_FILE") or None,
    )

    if dry_run:
        click.echo("=== DRY RUN MODE - No drafts will be created ===\n")

    gmail = GmailClient(
        credentials_file=get_env("GMAIL_CREDENTIALS_FILE", "credentials/credentials.json"),
        token_file=get_env("GMAIL_TOKEN_FILE", "credentials/token.json"),
    )

    parser = NewsletterParser(
        api_key=get_env("GROK_API_KEY"),
        model=get_env("GROK_MODEL", "grok-3"),
        base_url=get_env("GROK_BASE_URL", "https://api.x.ai/v1"),
    )

    if not get_env("BOUNCEBAN_API_KEY"):
        click.echo("Error: BOUNCEBAN_API_KEY is not set in .env file", err=True)
        sys.exit(1)

    email_finder = EmailFinder(
        api_key=get_env("BOUNCEBAN_API_KEY"),
        timeout=get_env_int("BOUNCEBAN_TIMEOUT", 30),
        rate_limit_delay=get_env_float("BOUNCEBAN_RATE_LIMIT_DELAY", 1.0),
    )

    drafter = EmailDrafter(
        parser=parser,
        subject_template=get_env(
            "EMAIL_SUBJECT_TEMPLATE",
            "Congrats on the {funding_amount} raise, {founder_first_name}!",
        ),
        sender_name=get_env("EMAIL_SENDER_NAME", "Your Name"),
    )

    click.echo("Fetching Axios Pro Rata emails...")
    emails = gmail.fetch_axios_emails(
        sender_filter=get_env("GMAIL_SENDER_FILTER", "axios.com"),
        processed_label=get_env("GMAIL_PROCESSED_LABEL", "Axios-Processed"),
        max_results=max_emails,
    )

    if not emails:
        click.echo("No unprocessed emails found.")
        return

    click.echo(f"Found {len(emails)} unprocessed email(s)\n")

    total_fundings = 0
    total_drafts = 0

    for email in emails:
        click.echo(f"Processing: {email['subject']}")
        logger.debug(f"Email date: {email['date']}")

        click.echo("  Extracting funding information...")
        fundings = parser.parse_newsletter(email)

        if not fundings:
            click.echo("  No funding announcements found.")
            continue

        click.echo(f"  Found {len(fundings)} funding announcement(s)")
        total_fundings += len(fundings)

        for funding in fundings:
            click.echo(f"\n  Company: {funding.company_name}")
            click.echo(f"  Funding: {funding.funding_amount}")
            click.echo(f"  Founders: {', '.join(funding.founder_names)}")

            if not funding.company_domain:
                click.echo("  ⚠ No domain found, skipping email discovery")
                continue

            click.echo(f"  Domain: {funding.company_domain}")

            for founder_name in funding.founder_names:
                click.echo(f"  Searching for email: {founder_name}...")
                result = email_finder.find_email_from_full_name(
                    founder_name, funding.company_domain
                )

                if not result:
                    click.echo(f"    ✗ No valid email found for {founder_name}")
                    continue

                if result.is_catch_all:
                    click.echo(f"    ⚠ Catch-all domain, using: {result.email}")
                else:
                    click.echo(f"    ✓ Found: {result.email}")

                draft = drafter.create_draft(funding, result.email)

                if dry_run:
                    click.echo("\n" + drafter.preview_draft(draft))
                else:
                    click.echo("    Creating Gmail draft...")
                    gmail.create_draft(
                        to=draft.to,
                        subject=draft.subject,
                        body=draft.body,
                    )
                    click.echo(f"    ✓ Draft created for {draft.to}")

                total_drafts += 1
                break

        if not dry_run:
            gmail.mark_as_processed(email["id"], email["label_id"])
            click.echo(f"\n  ✓ Email marked as processed")

    click.echo("\n" + "=" * 40)
    click.echo(f"Summary:")
    click.echo(f"  Emails processed: {len(emails)}")
    click.echo(f"  Fundings found: {total_fundings}")
    click.echo(f"  Drafts {'would be ' if dry_run else ''}created: {total_drafts}")

    parser.close()


if __name__ == "__main__":
    cli()
