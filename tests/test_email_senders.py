from settlement_automation.services.email_senders import (
    GraphEmailConfig,
    GraphEmailSender,
    parse_recipient_list,
)
from settlement_automation.services.email_models import DailyEmailContent
from settlement_automation.services.email_senders import EmailRecipients


def test_parse_recipient_list_accepts_commas_and_semicolons():
    recipients = parse_recipient_list(
        "a@example.com, b@example.com; c@example.com"
    )

    assert recipients == [
        "a@example.com",
        "b@example.com",
        "c@example.com",
    ]


def test_graph_sender_missing_config_returns_error():
    sender = GraphEmailSender(
        GraphEmailConfig(
            tenant_id="",
            client_id="",
            client_secret="",
            sender_email="",
        )
    )

    result = sender.send(
        email=DailyEmailContent(
            subject="Test",
            plain_text="Test",
            html="<p>Test</p>",
        ),
        recipients=EmailRecipients(
            to=["test@example.com"],
            cc=[],
            bcc=[],
        ),
    )

    assert result.sent is False
    assert result.provider == "graph"
    assert result.error_message is not None
    assert "GRAPH_TENANT_ID" in result.error_message
    assert "GRAPH_CLIENT_ID" in result.error_message
    assert "GRAPH_CLIENT_SECRET" in result.error_message
    assert "GRAPH_SENDER_EMAIL" in result.error_message


def test_graph_sender_requires_to_recipient():
    sender = GraphEmailSender(
        GraphEmailConfig(
            tenant_id="tenant",
            client_id="client",
            client_secret="secret",
            sender_email="sender@example.com",
        )
    )

    result = sender.send(
        email=DailyEmailContent(
            subject="Test",
            plain_text="Test",
            html="<p>Test</p>",
        ),
        recipients=EmailRecipients(
            to=[],
            cc=[],
            bcc=[],
        ),
    )

    assert result.sent is False
    assert result.error_message == "At least one To recipient is required."