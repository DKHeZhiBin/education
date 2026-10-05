from email.message import EmailMessage
import logging
import smtplib

from app.core.config import settings

logger = logging.getLogger(__name__)


class EmailDeliveryError(Exception):
    pass


class EmailSender:
    def send(self, recipient: str, subject: str, text: str) -> None:
        raise NotImplementedError


class SmtpEmailSender(EmailSender):
    def send(self, recipient: str, subject: str, text: str) -> None:
        message = EmailMessage()
        message["From"] = settings.smtp_from_email
        message["To"] = recipient
        message["Subject"] = subject
        message.set_content(text)
        try:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
                if settings.smtp_starttls:
                    smtp.starttls()
                if settings.smtp_username:
                    smtp.login(settings.smtp_username, settings.smtp_password)
                smtp.send_message(message)
        except (OSError, smtplib.SMTPException) as error:
            logger.warning("Unable to send account email", exc_info=True)
            raise EmailDeliveryError from error


class DisabledEmailSender(EmailSender):
    def send(self, recipient: str, subject: str, text: str) -> None:
        logger.info("Email delivery is disabled in this development environment")
        raise EmailDeliveryError("Email delivery is disabled")


email_sender: EmailSender = SmtpEmailSender() if settings.smtp_host else DisabledEmailSender()
