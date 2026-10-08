import smtplib
import ssl
from email.headerregistry import Address
from email.message import EmailMessage

import config


class SmtpAuthCodeDelivery:
    def send_code(
        self,
        *,
        channel: str,
        destination: str,
        code: str,
    ) -> None:
        if channel != "email":
            raise ValueError("Unsupported authentication channel")

        message = EmailMessage()
        message["Subject"] = "Код входа в NANOREM"
        message["From"] = Address(
            display_name=config.SMTP_FROM_NAME,
            addr_spec=config.SMTP_FROM_EMAIL,
        )
        message["To"] = destination
        message.set_content(
            "\n".join(
                (
                    f"Ваш код входа в NANOREM: {code}",
                    "Код действителен 10 минут.",
                    "Если вы не запрашивали код, просто проигнорируйте это письмо.",
                )
            )
        )

        smtp = smtplib.SMTP(
            config.SMTP_HOST,
            config.SMTP_PORT,
            timeout=config.SMTP_TIMEOUT,
        )
        smtp.ehlo()
        smtp.starttls(context=ssl.create_default_context())
        smtp.ehlo()
        smtp.login(config.SMTP_USERNAME, config.SMTP_PASSWORD)
        smtp.send_message(message)
        smtp.quit()
