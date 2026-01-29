"""Email drafting with templates and personalization."""

import logging
from dataclasses import dataclass
from typing import Optional

from .parser import FundingInfo, NewsletterParser

logger = logging.getLogger(__name__)

DEFAULT_TEMPLATE = """Hi {founder_first_name},

{opening_line}

{body}

Best,
{sender_name}"""

DEFAULT_BODY = """I wanted to reach out because we help companies like {company_name} scale their operations after raising. Our platform has helped similar startups reduce operational overhead by 40% while they focus on growth.

Would you be open to a quick 15-minute call this week to explore if we might be a fit?"""


@dataclass
class DraftEmail:
    """A prepared email draft ready to be created in Gmail."""

    to: str
    subject: str
    body: str
    funding_info: FundingInfo


class EmailDrafter:
    """Generate personalized outreach emails for funding announcements."""

    def __init__(
        self,
        parser: Optional[NewsletterParser] = None,
        subject_template: str = "Congrats on the {funding_amount} raise, {founder_first_name}!",
        email_template: str = DEFAULT_TEMPLATE,
        body_template: str = DEFAULT_BODY,
        sender_name: str = "Your Name",
    ):
        self.parser = parser
        self.subject_template = subject_template
        self.email_template = email_template
        self.body_template = body_template
        self.sender_name = sender_name

    def create_draft(
        self,
        funding_info: FundingInfo,
        to_email: str,
        custom_opening: Optional[str] = None,
    ) -> DraftEmail:
        """Create a personalized email draft for a funding announcement."""
        founder_first_name = funding_info.founder_first_name

        if custom_opening:
            opening_line = custom_opening
        elif self.parser:
            opening_line = self.parser.generate_opening_line(funding_info)
        else:
            opening_line = f"Congratulations on raising {funding_info.funding_amount}!"

        subject = self.subject_template.format(
            funding_amount=funding_info.funding_amount,
            founder_first_name=founder_first_name,
            company_name=funding_info.company_name,
        )

        body_content = self.body_template.format(
            company_name=funding_info.company_name,
            funding_amount=funding_info.funding_amount,
            founder_first_name=founder_first_name,
        )

        full_body = self.email_template.format(
            founder_first_name=founder_first_name,
            opening_line=opening_line,
            body=body_content,
            sender_name=self.sender_name,
        )

        return DraftEmail(
            to=to_email,
            subject=subject,
            body=full_body,
            funding_info=funding_info,
        )

    def create_drafts_batch(
        self,
        funding_infos: list[tuple[FundingInfo, str]],
    ) -> list[DraftEmail]:
        """Create drafts for multiple funding announcements.

        Args:
            funding_infos: List of (FundingInfo, email_address) tuples
        """
        drafts = []
        for funding_info, email in funding_infos:
            try:
                draft = self.create_draft(funding_info, email)
                drafts.append(draft)
                logger.info(f"Created draft for {email}")
            except Exception as e:
                logger.error(f"Failed to create draft for {email}: {e}")

        return drafts

    def preview_draft(self, draft: DraftEmail) -> str:
        """Format a draft for preview/display."""
        return f"""
{'='*60}
TO: {draft.to}
SUBJECT: {draft.subject}
{'='*60}
{draft.body}
{'='*60}
Company: {draft.funding_info.company_name}
Funding: {draft.funding_info.funding_amount}
Founders: {', '.join(draft.funding_info.founder_names)}
{'='*60}
"""
