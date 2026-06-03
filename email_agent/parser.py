"""EmailParser: parse .eml files and raw email text into structured fields."""

from __future__ import annotations

import email
import email.policy
from email.message import EmailMessage, Message
from pathlib import Path
from typing import Any


class EmailParser:
    """Parse .eml files or raw email text into structured dictionaries.

    Extracted fields:
        - sender  : the From header value
        - to      : the To header value
        - subject : the Subject header value
        - date    : the Date header value
        - body    : the plain-text body of the email
        - html    : the HTML body (if present), otherwise empty string
        - thread  : any quoted / forwarded thread text found in the body
        - raw     : the original raw text passed in
    """

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def parse_file(self, path: str) -> dict[str, Any]:
        """Parse a .eml file from disk.

        Args:
            path: Path to the .eml file.

        Returns:
            Parsed email dictionary.

        Raises:
            FileNotFoundError: if the file does not exist.
            ValueError: if the file is not a .eml file.
        """
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"Email file not found: {path}")
        if p.suffix.lower() != ".eml":
            raise ValueError(f"Expected a .eml file, got: {path}")
        raw = p.read_text(encoding="utf-8", errors="replace")
        result = self.parse_text(raw)
        result["file_path"] = str(p.resolve())
        return result

    def parse_text(self, raw: str) -> dict[str, Any]:
        """Parse raw email text (RFC 2822 format or plain text).

        If `raw` does not look like a proper RFC 2822 message (no headers),
        it is treated as a plain-text body with no metadata.

        Args:
            raw: Raw email string.

        Returns:
            Parsed email dictionary.
        """
        # Use the modern email policy for proper header decoding
        try:
            msg: Message = email.message_from_string(
                raw, policy=email.policy.default
            )
        except Exception:
            # Fallback: treat entire string as plain body
            return self._plain_body(raw)

        # If the message has no recognisable headers, treat as plain text
        if not msg.keys():
            return self._plain_body(raw)

        sender = self._decode_header(msg.get("From", ""))
        to = self._decode_header(msg.get("To", ""))
        subject = self._decode_header(msg.get("Subject", "(no subject)"))
        date = self._decode_header(msg.get("Date", ""))

        body, html = self._extract_body(msg)
        thread = self._extract_thread(body)
        # Strip the thread from the primary body
        clean_body = body
        if thread:
            clean_body = body[: body.find(thread)].strip()

        return {
            "sender": sender,
            "to": to,
            "subject": subject,
            "date": date,
            "body": clean_body,
            "html": html,
            "thread": thread,
            "raw": raw,
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _plain_body(raw: str) -> dict[str, Any]:
        """Return a minimal dict for text that has no RFC 2822 headers."""
        return {
            "sender": "",
            "to": "",
            "subject": "(no subject)",
            "date": "",
            "body": raw.strip(),
            "html": "",
            "thread": "",
            "raw": raw,
        }

    @staticmethod
    def _decode_header(value: str) -> str:
        """Return the string value of a (possibly encoded) header."""
        if not value:
            return ""
        # With email.policy.default the library already decodes RFC 2047
        # encoded words, so we just need to stringify.
        return str(value).strip()

    @staticmethod
    def _extract_body(msg: Message) -> tuple[str, str]:
        """Extract plain-text and HTML bodies from a (possibly multipart) message."""
        plain_parts: list[str] = []
        html_parts: list[str] = []

        if msg.is_multipart():
            for part in msg.walk():
                ct = part.get_content_type()
                disposition = str(part.get("Content-Disposition", ""))
                # Skip attachments
                if "attachment" in disposition:
                    continue
                if ct == "text/plain":
                    payload = part.get_payload(decode=True)
                    if payload:
                        charset = part.get_content_charset() or "utf-8"
                        plain_parts.append(
                            payload.decode(charset, errors="replace")
                        )
                elif ct == "text/html":
                    payload = part.get_payload(decode=True)
                    if payload:
                        charset = part.get_content_charset() or "utf-8"
                        html_parts.append(
                            payload.decode(charset, errors="replace")
                        )
        else:
            ct = msg.get_content_type()
            payload = msg.get_payload(decode=True)
            if payload:
                charset = msg.get_content_charset() or "utf-8"
                decoded = payload.decode(charset, errors="replace")
                if ct == "text/plain":
                    plain_parts.append(decoded)
                elif ct == "text/html":
                    html_parts.append(decoded)
                else:
                    # Treat unknown content types as plain text
                    plain_parts.append(decoded)
            else:
                # Payload might already be a string (non-binary transfer)
                raw_payload = msg.get_payload()
                if isinstance(raw_payload, str):
                    plain_parts.append(raw_payload)

        return "\n".join(plain_parts).strip(), "\n".join(html_parts).strip()

    @staticmethod
    def _extract_thread(body: str) -> str:
        """Attempt to extract quoted/forwarded thread text from the body.

        Recognises common quoting conventions:
            - Lines starting with '>'
            - '---- Original Message ----' / 'On <date> <person> wrote:' dividers
            - 'From:' blocks inside forwarded messages
        """
        if not body:
            return ""

        # Look for common thread/forward delimiters
        delimiters = [
            "\n> ",
            "\n>\n",
            "\n---- Original Message",
            "\n-----Original Message",
            "\n--- Original Message",
            "\nFrom:",          # forwarded block
            "\nBegin forwarded message:",
        ]
        earliest_pos = len(body)
        for delim in delimiters:
            pos = body.find(delim)
            if 0 < pos < earliest_pos:
                earliest_pos = pos

        if earliest_pos < len(body):
            return body[earliest_pos:].strip()
        return ""
