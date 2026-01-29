"""Email discovery via permutation generation and BounceBan API verification."""

import logging
import time
from dataclasses import dataclass
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


@dataclass
class EmailVerificationResult:
    """Result of email verification attempt."""

    email: str
    is_valid: bool
    is_catch_all: bool
    score: Optional[int]
    message: str


class EmailFinder:
    """Find and verify founder email addresses using BounceBan API."""

    BASE_URL = "https://api.bounceban.com"

    def __init__(
        self,
        api_key: str,
        timeout: int = 30,
        rate_limit_delay: float = 1.0,
    ):
        self.api_key = api_key
        self.timeout = timeout
        self.rate_limit_delay = rate_limit_delay
        self._last_request_time = 0
        self._client = httpx.Client(
            base_url=self.BASE_URL,
            headers={"Authorization": api_key},
            timeout=timeout,
        )

    def generate_permutations(
        self, first_name: str, last_name: str, domain: str
    ) -> list[str]:
        """Generate common email permutations from name and domain."""
        first = first_name.lower().strip()
        last = last_name.lower().strip()

        if not first or not last or not domain:
            return []

        first_initial = first[0]

        permutations = [
            f"{first}@{domain}",
            f"{first}.{last}@{domain}",
            f"{first_initial}{last}@{domain}",
            f"{first_initial}.{last}@{domain}",
            f"{last}@{domain}",
            f"{first}{last}@{domain}",
            f"{last}{first}@{domain}",
            f"{last}.{first}@{domain}",
            f"{first}_{last}@{domain}",
            f"{first}-{last}@{domain}",
        ]

        return permutations

    def _rate_limit(self) -> None:
        """Enforce rate limiting between API requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.rate_limit_delay:
            time.sleep(self.rate_limit_delay - elapsed)
        self._last_request_time = time.time()

    def verify_email(self, email: str) -> EmailVerificationResult:
        """Verify if an email address exists via BounceBan API."""
        self._rate_limit()

        try:
            # Start verification
            response = self._client.get(
                "/v1/verify/single",
                params={"email": email},
            )
            response.raise_for_status()
            data = response.json()

            # If status is pending, poll for result
            if data.get("status") == "pending":
                task_id = data.get("id")
                return self._poll_for_result(email, task_id)

            return self._parse_response(email, data)

        except httpx.HTTPStatusError as e:
            logger.error(f"BounceBan API error for {email}: {e.response.status_code}")
            return EmailVerificationResult(
                email=email,
                is_valid=False,
                is_catch_all=False,
                score=None,
                message=f"API error: {e.response.status_code}",
            )
        except httpx.RequestError as e:
            logger.error(f"BounceBan request error for {email}: {e}")
            return EmailVerificationResult(
                email=email,
                is_valid=False,
                is_catch_all=False,
                score=None,
                message=f"Request error: {e}",
            )
        except Exception as e:
            logger.error(f"Unexpected error verifying {email}: {e}")
            return EmailVerificationResult(
                email=email,
                is_valid=False,
                is_catch_all=False,
                score=None,
                message=str(e),
            )

    def _poll_for_result(
        self, email: str, task_id: str, max_attempts: int = 10
    ) -> EmailVerificationResult:
        """Poll for verification result using task ID."""
        for attempt in range(max_attempts):
            time.sleep(2)  # Wait between polls

            try:
                response = self._client.get(
                    "/v1/verify/single/status",
                    params={"id": task_id},
                )
                response.raise_for_status()
                data = response.json()

                if data.get("status") != "pending":
                    return self._parse_response(email, data)

            except Exception as e:
                logger.debug(f"Poll attempt {attempt + 1} failed: {e}")
                continue

        return EmailVerificationResult(
            email=email,
            is_valid=False,
            is_catch_all=False,
            score=None,
            message="Verification timed out",
        )

    def _parse_response(self, email: str, data: dict) -> EmailVerificationResult:
        """Parse BounceBan API response into EmailVerificationResult."""
        result = data.get("result", "unknown")
        score = data.get("score")
        is_accept_all = data.get("is_accept_all", False)

        # deliverable = valid, risky = might be valid, undeliverable/unknown = invalid
        is_valid = result in ("deliverable", "risky")

        return EmailVerificationResult(
            email=email,
            is_valid=is_valid,
            is_catch_all=is_accept_all,
            score=score,
            message=f"Result: {result}" + (f" (score: {score})" if score else ""),
        )

    def find_valid_email(
        self, first_name: str, last_name: str, domain: str
    ) -> Optional[EmailVerificationResult]:
        """Find a valid email for a person at a domain."""
        permutations = self.generate_permutations(first_name, last_name, domain)
        logger.info(f"Testing {len(permutations)} email permutations for {first_name} {last_name}")

        for email in permutations:
            logger.debug(f"Verifying: {email}")
            result = self.verify_email(email)

            if result.is_valid:
                logger.info(f"Found valid email: {email}")
                return result

        logger.warning(f"No valid email found for {first_name} {last_name} at {domain}")
        return None

    def find_email_from_full_name(
        self, full_name: str, domain: str
    ) -> Optional[EmailVerificationResult]:
        """Find email from a full name string."""
        parts = full_name.strip().split()
        if len(parts) < 2:
            logger.warning(f"Cannot parse full name: {full_name}")
            first_name = parts[0] if parts else ""
            last_name = ""
        else:
            first_name = parts[0]
            last_name = parts[-1]

        return self.find_valid_email(first_name, last_name, domain)

    def close(self) -> None:
        """Close the HTTP client."""
        self._client.close()
