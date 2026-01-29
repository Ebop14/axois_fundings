"""Web-based founder name extraction via URL scraping and Grok analysis."""

import logging
import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urljoin, urlparse

import httpx

logger = logging.getLogger(__name__)


@dataclass
class FounderSearchResult:
    """Result of founder search attempt."""

    company_name: str
    founder_names: list[str]
    source_url: Optional[str]
    confidence: str  # "high", "medium", "low"
    scraped_content: Optional[str] = None  # Combined scraped content for enrichment


class FounderFinder:
    """Find founder names by scraping company websites and news articles."""

    # TODO: Add rate limiting for web requests to avoid being blocked
    # - Add delay between requests (similar to EmailFinder._rate_limit)
    # - Consider exponential backoff on 429/503 responses
    # - Add retry logic with jitter

    # Common about page paths to try
    ABOUT_PATHS = [
        "/about",
        "/about-us",
        "/team",
        "/about/team",
        "/company",
        "/company/about",
        "/leadership",
        "/our-team",
    ]

    # User agent to avoid bot detection
    USER_AGENT = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )

    def __init__(
        self,
        grok_api_key: str,
        grok_model: str = "grok-3",
        grok_base_url: str = "https://api.x.ai/v1",
        timeout: int = 15,
    ):
        self.grok_api_key = grok_api_key
        self.grok_model = grok_model
        self.grok_base_url = grok_base_url
        self._client = httpx.Client(
            timeout=timeout,
            headers={"User-Agent": self.USER_AGENT},
            follow_redirects=True,
        )
        self._grok_client = httpx.Client(timeout=60.0)

    def find_founders(
        self,
        company_name: str,
        company_domain: Optional[str] = None,
        article_urls: Optional[list[str]] = None,
    ) -> FounderSearchResult:
        """
        Find founder names for a company.

        Strategy:
        1. Scrape any provided article URLs (likely contain founder mentions)
        2. If domain provided, try company website about/team pages
        3. Use Grok to extract founder names from scraped content
        """
        all_content = []
        source_url = None

        # First, try article URLs (often contain "founded by X" language)
        if article_urls:
            for url in article_urls[:3]:  # Limit to first 3 URLs
                logger.debug(f"Fetching article URL: {url}")
                html = self._fetch_url(url)
                if html:
                    text = self._extract_text(html)
                    if text and len(text) > 100:
                        all_content.append(text)
                        if not source_url:
                            source_url = url

        # Then try company website
        if company_domain:
            base_url = f"https://{company_domain}"

            # Try common about/team pages
            for path in self.ABOUT_PATHS:
                url = urljoin(base_url, path)
                logger.debug(f"Trying company page: {url}")
                html = self._fetch_url(url)
                if html:
                    text = self._extract_text(html)
                    if text and len(text) > 100:
                        all_content.append(text)
                        if not source_url:
                            source_url = url
                        break  # Found a good about page

            # Also try homepage if no about page found
            if not all_content:
                logger.debug(f"Trying homepage: {base_url}")
                html = self._fetch_url(base_url)
                if html:
                    text = self._extract_text(html)
                    if text:
                        all_content.append(text)
                        source_url = base_url

        if not all_content:
            logger.warning(f"Could not fetch any content for {company_name}")
            return FounderSearchResult(
                company_name=company_name,
                founder_names=[],
                source_url=None,
                confidence="low",
                scraped_content=None,
            )

        # Use Grok to extract founder names from combined content
        combined_content = "\n\n---\n\n".join(all_content)
        founders = self._extract_founders_with_grok(company_name, combined_content)

        confidence = "high" if len(founders) > 0 else "low"
        if founders and len(all_content) == 1:
            confidence = "medium"

        return FounderSearchResult(
            company_name=company_name,
            founder_names=founders,
            source_url=source_url,
            confidence=confidence,
            scraped_content=combined_content,  # Return for email enrichment
        )

    def _fetch_url(self, url: str) -> Optional[str]:
        """Fetch HTML content from a URL."""
        try:
            response = self._client.get(url)
            response.raise_for_status()

            # Only process HTML responses
            content_type = response.headers.get("content-type", "")
            if "text/html" not in content_type.lower():
                return None

            return response.text

        except httpx.HTTPStatusError as e:
            logger.debug(f"HTTP error for {url}: {e.response.status_code}")
            return None
        except httpx.RequestError as e:
            logger.debug(f"Request error for {url}: {e}")
            return None
        except Exception as e:
            logger.debug(f"Error fetching {url}: {e}")
            return None

    def _extract_text(self, html: str) -> str:
        """Extract readable text from HTML."""
        # Remove script and style elements
        text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<noscript[^>]*>.*?</noscript>", "", text, flags=re.DOTALL | re.IGNORECASE)

        # Remove HTML tags
        text = re.sub(r"<[^>]+>", " ", text)

        # Decode common entities
        text = re.sub(r"&nbsp;", " ", text)
        text = re.sub(r"&amp;", "&", text)
        text = re.sub(r"&lt;", "<", text)
        text = re.sub(r"&gt;", ">", text)
        text = re.sub(r"&quot;", '"', text)
        text = re.sub(r"&#39;", "'", text)

        # Normalize whitespace
        text = re.sub(r"\s+", " ", text)

        return text.strip()[:12000]  # Limit content size

    def _extract_founders_with_grok(
        self, company_name: str, content: str
    ) -> list[str]:
        """Use Grok to extract founder names from scraped content."""
        prompt = f"""Analyze this content about {company_name} and extract the names of founders, co-founders, or CEOs.

Look for:
- Explicit mentions like "founded by", "co-founded by", "CEO", "Founder"
- Leadership team sections
- About page bios mentioning founding roles

Content:
{content[:8000]}

Return ONLY a JSON array of full names, e.g.: ["John Smith", "Jane Doe"]
If no founders/CEOs are found, return an empty array: []
Return ONLY the JSON array, no other text."""

        try:
            response = self._grok_client.post(
                f"{self.grok_base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.grok_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.grok_model,
                    "messages": [
                        {
                            "role": "system",
                            "content": "You extract founder and CEO names from company information. Return only valid JSON arrays.",
                        },
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.1,
                },
            )
            response.raise_for_status()
            data = response.json()
            result = data["choices"][0]["message"]["content"].strip()

            # Clean up response
            if result.startswith("```"):
                result = re.sub(r"^```json?\n?", "", result)
                result = re.sub(r"\n?```$", "", result)

            import json
            founders = json.loads(result)

            if isinstance(founders, list):
                # Filter to valid-looking names (at least first and last name)
                valid_founders = [
                    name for name in founders
                    if isinstance(name, str) and len(name.split()) >= 2
                ]
                return valid_founders[:5]  # Limit to 5 founders

            return []

        except Exception as e:
            logger.error(f"Grok extraction error: {e}")
            return []

    def extract_urls_from_html(self, html: str, base_domain: str = "axios.com") -> list[str]:
        """Extract relevant URLs from newsletter HTML content."""
        urls = []

        # Find all href links
        href_pattern = r'href=["\']([^"\']+)["\']'
        matches = re.findall(href_pattern, html, re.IGNORECASE)

        for url in matches:
            # Skip common non-article URLs
            if any(skip in url.lower() for skip in [
                "unsubscribe", "mailto:", "javascript:", "#",
                "twitter.com", "facebook.com", "linkedin.com/sharing",
                "privacy", "terms", "contact", "careers",
            ]):
                continue

            # Parse the URL
            try:
                parsed = urlparse(url)
                # Keep absolute URLs that aren't from the newsletter sender
                if parsed.scheme in ("http", "https"):
                    if base_domain not in parsed.netloc:
                        urls.append(url)
            except Exception:
                continue

        # Deduplicate while preserving order
        seen = set()
        unique_urls = []
        for url in urls:
            if url not in seen:
                seen.add(url)
                unique_urls.append(url)

        return unique_urls[:10]  # Return first 10 unique URLs

    def close(self) -> None:
        """Close HTTP clients."""
        self._client.close()
        self._grok_client.close()
