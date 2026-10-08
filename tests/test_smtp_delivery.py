from email.message import EmailMessage
from unittest.mock import patch

import pytest

from services.smtp_delivery import SmtpAuthCodeDelivery


@patch("services.smtp_delivery.smtplib.SMTP")
@patch("services.smtp_delivery.ssl.create_default_context")
def test_smtp_delivery_sends_email_with_starttls_and_authentication(
    create_default_context,
    smtp_factory,
    monkeypatch,
):
    monkeypatch.setattr("config.SMTP_HOST", "smtp.example.test")
    monkeypatch.setattr("config.SMTP_PORT", 587)
    monkeypatch.setattr("config.SMTP_USERNAME", "smtp-user")
    monkeypatch.setattr("config.SMTP_PASSWORD", "smtp-password")
    monkeypatch.setattr("config.SMTP_FROM_EMAIL", "no-reply@example.test")
    monkeypatch.setattr("config.SMTP_FROM_NAME", "NANOREM")
    monkeypatch.setattr("config.SMTP_TIMEOUT", 15)
    smtp = smtp_factory.return_value
    context = create_default_context.return_value

    SmtpAuthCodeDelivery().send_code(
        channel="email",
        destination="member@example.test",
        code="123456",
    )

    smtp_factory.assert_called_once_with(
        "smtp.example.test",
        587,
        timeout=15,
    )
    assert smtp.ehlo.call_count == 2
    smtp.starttls.assert_called_once_with(context=context)
    create_default_context.assert_called_once_with()
    smtp.login.assert_called_once_with("smtp-user", "smtp-password")
    smtp.send_message.assert_called_once()
    smtp.quit.assert_called_once_with()

    message = smtp.send_message.call_args.args[0]
    assert isinstance(message, EmailMessage)
    assert message["To"] == "member@example.test"
    assert str(message["From"]) == "NANOREM <no-reply@example.test>"
    assert message["Subject"] == "Код входа в NANOREM"
    assert "123456" in message.get_content()
    assert "Код действителен 10 минут." in message.get_content()
    assert (
        "Если вы не запрашивали код, просто проигнорируйте это письмо."
        in message.get_content()
    )


def test_smtp_delivery_rejects_non_email_channel():
    with patch("services.smtp_delivery.smtplib.SMTP") as smtp_factory:
        with pytest.raises(
            ValueError,
            match="^Unsupported authentication channel$",
        ):
            SmtpAuthCodeDelivery().send_code(
                channel="phone",
                destination="+15551234567",
                code="123456",
            )

    smtp_factory.assert_not_called()
