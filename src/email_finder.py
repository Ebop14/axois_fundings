"""Email discovery via permutation generation and SMTP verification."""

import logging
import smtplib
import socket
import time
from dataclasses import dataclass
from typing import Optional

import dns.resolver

logger = logging.getLogger(__name__)


@dataclass
class EmailVerificationResult:
    """Result of email verification attempt."""

    email: str
    is_valid: bool
    is_catch_all: bool
    smtp_code: Optional[int]
    message: str


class EmailFinder:
    """Find and verify founder email addresses."""

    def __init__(
        self,
        timeout: int = 10,
        rate_limit_delay: float = 2.0,
        from_email: str = "verify@example.com",
    ):
        self.timeout = timeout
        self.rate_limit_delay = rate_limit_delay
        self.from_email = from_email
        self._last_request_time = 0

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

    def get_mx_records(self, domain: str) -> list[str]:
        """Get MX records for a domain, sorted by priority."""
        try:
            answers = dns.resolver.resolve(domain, "MX")
            mx_records = []
            for rdata in answers:
                mx_records.append((rdata.preference, str(rdata.exchange).rstrip(".")))
            mx_records.sort(key=lambda x: x[0])
            return [mx[1] for mx in mx_records]
        except dns.resolver.NXDOMAIN:
            logger.warning(f"Domain does not exist: {domain}")
            return []
        except dns.resolver.NoAnswer:
            logger.warning(f"No MX records for domain: {domain}")
            return []
        except Exception as e:
            logger.error(f"DNS lookup error for {domain}: {e}")
            return []

    def _rate_limit(self) -> None:
        """Enforce rate limiting between SMTP requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.rate_limit_delay:
            time.sleep(self.rate_limit_delay - elapsed)
        self._last_request_time = time.time()

    def verify_email(self, email: str) -> EmailVerificationResult:
        """Verify if an email address exists via SMTP."""
        domain = email.split("@")[1]
        mx_records = self.get_mx_records(domain)

        if not mx_records:
            return EmailVerificationResult(
                email=email,
                is_valid=False,
                is_catch_all=False,
                smtp_code=None,
                message="No MX records found",
            )

        self._rate_limit()

        for mx_host in mx_records[:2]:
            try:
                result = self._smtp_check(email, mx_host)
                if result.smtp_code is not None:
                    return result
            except Exception as e:
                logger.debug(f"SMTP check failed for {mx_host}: {e}")
                continue

        return EmailVerificationResult(
            email=email,
            is_valid=False,
            is_catch_all=False,
            smtp_code=None,
            message="All MX servers unreachable",
        )

    def _smtp_check(self, email: str, mx_host: str) -> EmailVerificationResult:
        """Perform SMTP handshake to verify email."""
        try:
            smtp = smtplib.SMTP(timeout=self.timeout)
            smtp.connect(mx_host, 25)
            smtp.helo("mail.example.com")
            smtp.mail(self.from_email)
            code, message = smtp.rcpt(email)
            smtp.quit()

            message_str = message.decode("utf-8", errors="ignore")

            if code == 250:
                return EmailVerificationResult(
                    email=email,
                    is_valid=True,
                    is_catch_all=False,
                    smtp_code=code,
                    message=message_str,
                )
            elif code == 550:
                return EmailVerificationResult(
                    email=email,
                    is_valid=False,
                    is_catch_all=False,
                    smtp_code=code,
                    message=message_str,
                )
            elif code == 551 or code == 552 or code == 553:
                return EmailVerificationResult(
                    email=email,
                    is_valid=False,
                    is_catch_all=False,
                    smtp_code=code,
                    message=message_str,
                )
            else:
                return EmailVerificationResult(
                    email=email,
                    is_valid=False,
                    is_catch_all=False,
                    smtp_code=code,
                    message=f"Unexpected response: {message_str}",
                )

        except smtplib.SMTPServerDisconnected:
            return EmailVerificationResult(
                email=email,
                is_valid=False,
                is_catch_all=False,
                smtp_code=None,
                message="Server disconnected",
            )
        except smtplib.SMTPConnectError as e:
            return EmailVerificationResult(
                email=email,
                is_valid=False,
                is_catch_all=False,
                smtp_code=None,
                message=f"Connection error: {e}",
            )
        except socket.timeout:
            return EmailVerificationResult(
                email=email,
                is_valid=False,
                is_catch_all=False,
                smtp_code=None,
                message="Connection timeout",
            )
        except Exception as e:
            return EmailVerificationResult(
                email=email,
                is_valid=False,
                is_catch_all=False,
                smtp_code=None,
                message=str(e),
            )

    def check_catch_all(self, domain: str) -> bool:
        """Check if domain has catch-all enabled."""
        random_email = f"nonexistent.user.xyz123abc@{domain}"
        result = self.verify_email(random_email)
        return result.is_valid

    def find_valid_email(
        self, first_name: str, last_name: str, domain: str
    ) -> Optional[EmailVerificationResult]:
        """Find a valid email for a person at a domain."""
        if self.check_catch_all(domain):
            logger.warning(f"Domain {domain} appears to have catch-all enabled")
            permutations = self.generate_permutations(first_name, last_name, domain)
            if permutations:
                return EmailVerificationResult(
                    email=permutations[0],
                    is_valid=True,
                    is_catch_all=True,
                    smtp_code=250,
                    message="Catch-all domain - using best guess",
                )

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
