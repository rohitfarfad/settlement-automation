from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Protocol
import base64

from settlement_automation.services.email_models import (
    DailyEmailContent,
    EmailAttachment,
)
@dataclass(frozen=True)
class EmailSendResult:
    sent: bool
    provider: str
    message: str | None = None
    error_message: str | None = None


@dataclass(frozen=True)
class EmailRecipients:
    to: list[str]
    cc: list[str]
    bcc: list[str]


class EmailSender(Protocol):
    def send(
        self,
        *,
        email: DailyEmailContent,
        recipients: EmailRecipients,
        attachments: list[EmailAttachment] | None = None,
    ) -> EmailSendResult:
        ...


@dataclass(frozen=True)
class GraphEmailConfig:
    tenant_id: str
    client_id: str
    client_secret: str
    sender_email: str


class GraphEmailSender:
    token_url_template = (
        "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    )
    graph_send_url_template = (
        "https://graph.microsoft.com/v1.0/users/{sender_email}/sendMail"
    )

    def __init__(self, config: GraphEmailConfig):
        self.config = config

    def send(
            self,
            *,
            email: DailyEmailContent,
            recipients: EmailRecipients,
            attachments: list[EmailAttachment] | None = None,
    ) -> EmailSendResult:
        missing = self._missing_config_fields()

        if missing:
            return EmailSendResult(
                sent=False,
                provider="graph",
                error_message=(
                    "Missing Microsoft Graph config values: "
                    + ", ".join(missing)
                ),
            )

        if not recipients.to:
            return EmailSendResult(
                sent=False,
                provider="graph",
                error_message="At least one To recipient is required.",
            )

        try:
            access_token = self._get_access_token()
            self._send_mail(
                access_token=access_token,
                email=email,
                recipients=recipients,
                attachments=attachments or [],
            )

            return EmailSendResult(
                sent=True,
                provider="graph",
                message="Email sent with Microsoft Graph.",
            )
        except Exception as exc:
            return EmailSendResult(
                sent=False,
                provider="graph",
                error_message=str(exc),
            )

    def _missing_config_fields(self) -> list[str]:
        missing = []

        if not self.config.tenant_id:
            missing.append("GRAPH_TENANT_ID")

        if not self.config.client_id:
            missing.append("GRAPH_CLIENT_ID")

        if not self.config.client_secret:
            missing.append("GRAPH_CLIENT_SECRET")

        if not self.config.sender_email:
            missing.append("GRAPH_SENDER_EMAIL")

        return missing

    def _get_access_token(self) -> str:
        token_url = self.token_url_template.format(
            tenant_id=urllib.parse.quote(self.config.tenant_id)
        )

        form_data = urllib.parse.urlencode(
            {
                "client_id": self.config.client_id,
                "client_secret": self.config.client_secret,
                "scope": "https://graph.microsoft.com/.default",
                "grant_type": "client_credentials",
            }
        ).encode("utf-8")

        request = urllib.request.Request(
            token_url,
            data=form_data,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
            },
            method="POST",
        )

        response = _open_json(request)
        access_token = response.get("access_token")

        if not access_token:
            raise RuntimeError(
                "Microsoft Graph token response did not include access_token."
            )

        return str(access_token)

    def _send_mail(
            self,
            *,
            access_token: str,
            email: DailyEmailContent,
            recipients: EmailRecipients,
            attachments: list[EmailAttachment],
    ) -> None:
        sender_email = urllib.parse.quote(self.config.sender_email)
        send_url = self.graph_send_url_template.format(
            sender_email=sender_email
        )

        payload = {
            "message": {
                "subject": email.subject,
                "body": {
                    "contentType": "HTML",
                    "content": email.html,
                },
                "toRecipients": _build_graph_recipients(recipients.to),
                "ccRecipients": _build_graph_recipients(recipients.cc),
                "bccRecipients": _build_graph_recipients(recipients.bcc),
            },
            "saveToSentItems": "true",
        }

        if attachments:
            payload["message"]["attachments"] = _build_graph_attachments(attachments)

        body = json.dumps(payload).encode("utf-8")

        request = urllib.request.Request(
            send_url,
            data=body,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        _open_empty_success(request)


def _build_graph_recipients(addresses: list[str]) -> list[dict]:
    return [
        {
            "emailAddress": {
                "address": address,
            }
        }
        for address in addresses
    ]

def _build_graph_attachments(
    attachments: list[EmailAttachment],
) -> list[dict]:
    return [
        {
            "@odata.type": "#microsoft.graph.fileAttachment",
            "name": attachment.name,
            "contentType": attachment.content_type,
            "contentBytes": base64.b64encode(
                attachment.content_bytes
            ).decode("ascii"),
        }
        for attachment in attachments
    ]


def parse_recipient_list(value: str) -> list[str]:
    if not value:
        return []

    return [
        item.strip()
        for item in value.replace(";", ",").split(",")
        if item.strip()
    ]


def _open_json(request: urllib.request.Request) -> dict:
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = response.read().decode("utf-8")

            if not payload:
                return {}

            return json.loads(payload)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(_format_http_error(exc)) from exc


def _open_empty_success(request: urllib.request.Request) -> None:
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            response.read()
    except urllib.error.HTTPError as exc:
        raise RuntimeError(_format_http_error(exc)) from exc


def _format_http_error(exc: urllib.error.HTTPError) -> str:
    body = exc.read().decode("utf-8", errors="replace")
    return f"HTTP {exc.code}: {body}"