"""Newsletter parser using Grok-3 API for extracting funding information."""

import json
import logging
import re
from dataclasses import dataclass
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


@dataclass
class FundingInfo:
    """Extracted funding information from newsletter."""

    company_name: str
    funding_amount: str
    investors: list[str]
    founder_names: list[str]
    company_domain: Optional[str]
    description: Optional[str]
    raw_text: str

    @property
    def founder_first_name(self) -> str:
        """Get the first name of the first founder."""
        if self.founder_names:
            return self.founder_names[0].split()[0]
        return ""


class NewsletterParser:
    """Parse Axios Pro Rata newsletters using Grok-3."""

    def __init__(
        self,
        api_key: str,
        model: str = "grok-3",
        base_url: str = "https://api.x.ai/v1",
    ):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self.client = httpx.Client(timeout=60.0)

    def parse_newsletter(self, email_content: dict) -> list[FundingInfo]:
        """Extract funding information from newsletter email."""
        content = email_content.get("body_html") or email_content.get("body_text", "")

        if not content:
            logger.warning("No content found in email")
            return []

        content = self._clean_html(content)

        prompt = self._build_extraction_prompt(content)
        response = self._call_grok(prompt)

        if not response:
            return []

        return self._parse_response(response, content)

    def _clean_html(self, html: str) -> str:
        """Remove HTML tags and clean up content."""
        text = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL)
        text = re.sub(r"<script[^>]*>.*?</script>", "", text, flags=re.DOTALL)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"&nbsp;", " ", text)
        text = re.sub(r"&amp;", "&", text)
        text = re.sub(r"&lt;", "<", text)
        text = re.sub(r"&gt;", ">", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def _build_extraction_prompt(self, content: str) -> str:
        """Build the prompt for Grok-3 extraction."""
        return f"""Analyze this Axios Pro Rata newsletter and extract ALL funding announcements.

For each company that raised funding, extract:
1. company_name: The company's name
2. funding_amount: The funding amount (e.g., "$50 million", "$10M Series A")
3. investors: List of investor names
4. founder_names: List of founder/CEO names mentioned
5. company_domain: The company's website domain (infer from company name if not explicit)
6. description: Brief description of what the company does

Return a JSON array of objects. If no funding announcements found, return an empty array [].

Example output:
[
  {{
    "company_name": "TechStartup",
    "funding_amount": "$25 million Series B",
    "investors": ["Sequoia Capital", "Andreessen Horowitz"],
    "founder_names": ["John Smith", "Jane Doe"],
    "company_domain": "techstartup.com",
    "description": "AI-powered analytics platform"
  }}
]

Newsletter content:
{content[:8000]}

Return ONLY the JSON array, no other text."""

    def _call_grok(self, prompt: str) -> Optional[str]:
        """Call Grok-3 API with the extraction prompt."""
        try:
            response = self.client.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "messages": [
                        {
                            "role": "system",
                            "content": "You are a precise data extraction assistant. Extract structured information from newsletters and return valid JSON only.",
                        },
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.1,
                },
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]

        except httpx.HTTPStatusError as e:
            logger.error(f"Grok API HTTP error: {e.response.status_code} - {e.response.text}")
            return None
        except Exception as e:
            logger.error(f"Grok API error: {e}")
            return None

    def _parse_response(self, response: str, raw_text: str) -> list[FundingInfo]:
        """Parse Grok-3 response into FundingInfo objects."""
        response = response.strip()
        if response.startswith("```"):
            response = re.sub(r"^```json?\n?", "", response)
            response = re.sub(r"\n?```$", "", response)

        try:
            data = json.loads(response)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Grok response as JSON: {e}")
            logger.debug(f"Response was: {response[:500]}")
            return []

        if not isinstance(data, list):
            data = [data]

        results = []
        for item in data:
            try:
                info = FundingInfo(
                    company_name=item.get("company_name", ""),
                    funding_amount=item.get("funding_amount", ""),
                    investors=item.get("investors", []),
                    founder_names=item.get("founder_names", []),
                    company_domain=item.get("company_domain"),
                    description=item.get("description"),
                    raw_text=raw_text[:500],
                )
                if info.company_name and info.founder_names:
                    results.append(info)
                else:
                    logger.warning(
                        f"Skipping incomplete funding info: {item}"
                    )
            except Exception as e:
                logger.error(f"Error creating FundingInfo: {e}")

        logger.info(f"Extracted {len(results)} funding announcements")
        return results

    def generate_opening_line(self, funding_info: FundingInfo) -> str:
        """Generate a personalized opening line using Grok-3."""
        prompt = f"""Write a brief, personalized opening line for a sales email to {funding_info.founder_names[0]},
founder of {funding_info.company_name} who just raised {funding_info.funding_amount}.

Company description: {funding_info.description or 'N/A'}
Investors: {', '.join(funding_info.investors) if funding_info.investors else 'N/A'}

The opening should:
- Congratulate them on the funding
- Show you understand what their company does
- Be concise (1-2 sentences max)
- Sound natural, not salesy

Return ONLY the opening line, no quotes or other text."""

        response = self._call_grok(prompt)
        if response:
            return response.strip().strip('"')
        return f"Congratulations on raising {funding_info.funding_amount}!"

    def close(self) -> None:
        """Close the HTTP client."""
        self.client.close()
