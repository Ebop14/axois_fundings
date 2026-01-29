"""Main CLI entry point for the newsletter outreach automation tool."""

import logging
import sys
from pathlib import Path
from typing import Optional

import click
import yaml

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


def load_config(config_path: str = "config/config.yaml") -> dict:
    """Load configuration from YAML file."""
    path = Path(config_path)
    if not path.exists():
        example_path = Path("config/config.example.yaml")
        if example_path.exists():
            raise FileNotFoundError(
                f"Config file not found: {config_path}\n"
                f"Copy {example_path} to {config_path} and fill in your credentials."
            )
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(path) as f:
        return yaml.safe_load(f)


@click.command()
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose logging")
@click.option("--dry-run", is_flag=True, help="Don't create drafts, just show what would be done")
@click.option("--config", "-c", default="config/config.yaml", help="Path to config file")
@click.option("--max-emails", "-n", default=10, help="Maximum number of emails to process")
def cli(verbose: bool, dry_run: bool, config: str, max_emails: int) -> None:
    """Process Axios Pro Rata newsletters and create outreach drafts."""
    try:
        cfg = load_config(config)
    except FileNotFoundError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    setup_logging(
        verbose=verbose,
        log_file=cfg.get("logging", {}).get("file"),
    )

    if dry_run:
        click.echo("=== DRY RUN MODE - No drafts will be created ===\n")

    gmail_cfg = cfg.get("gmail", {})
    gmail = GmailClient(
        credentials_file=gmail_cfg.get("credentials_file", "credentials/credentials.json"),
        token_file=gmail_cfg.get("token_file", "credentials/token.json"),
    )

    grok_cfg = cfg.get("grok", {})
    parser = NewsletterParser(
        api_key=grok_cfg.get("api_key", ""),
        model=grok_cfg.get("model", "grok-3"),
        base_url=grok_cfg.get("base_url", "https://api.x.ai/v1"),
    )

    smtp_cfg = cfg.get("smtp", {})
    email_finder = EmailFinder(
        timeout=smtp_cfg.get("timeout", 10),
        rate_limit_delay=smtp_cfg.get("rate_limit_delay", 2.0),
        from_email=smtp_cfg.get("from_email", "verify@example.com"),
    )

    email_cfg = cfg.get("email", {})
    drafter = EmailDrafter(
        parser=parser,
        subject_template=email_cfg.get(
            "subject_template",
            "Congrats on the {funding_amount} raise, {founder_first_name}!",
        ),
        sender_name=email_cfg.get("sender_name", "Your Name"),
    )

    click.echo("Fetching Axios Pro Rata emails...")
    emails = gmail.fetch_axios_emails(
        sender_filter=gmail_cfg.get("sender_filter", "axios.com"),
        processed_label=gmail_cfg.get("processed_label", "Axios-Processed"),
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
