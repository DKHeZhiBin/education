from email.message import EmailMessage
import logging
import smtplib

from app.core.config import settings

logger = logging.getLogger(__name__)


class EmailDeliveryError(Exception):
    """中文：定义“邮箱·delivery·error”类，封装该职责相关的数据与行为。
    English: Defines the email delivery error class and encapsulates data and behavior for that responsibility.
    """
    pass


class EmailSender:
    """中文：定义“邮箱·sender”类，封装该职责相关的数据与行为。
    English: Defines the email sender class and encapsulates data and behavior for that responsibility.
    """
    def send(self, recipient: str, subject: str, text: str) -> None:
        """中文：处理“send”相关操作。
        English: Handles the send operation.
        """
        raise NotImplementedError


class SmtpEmailSender(EmailSender):
    """中文：定义“smtp·邮箱·sender”类，封装该职责相关的数据与行为。
    English: Defines the smtp email sender class and encapsulates data and behavior for that responsibility.
    """
    def send(self, recipient: str, subject: str, text: str) -> None:
        """中文：处理“send”相关操作。
        English: Handles the send operation.
        """
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
    """中文：定义“disabled·邮箱·sender”类，封装该职责相关的数据与行为。
    English: Defines the disabled email sender class and encapsulates data and behavior for that responsibility.
    """
    def send(self, recipient: str, subject: str, text: str) -> None:
        """中文：处理“send”相关操作。
        English: Handles the send operation.
        """
        logger.info("Email delivery is disabled in this development environment")
        raise EmailDeliveryError("Email delivery is disabled")


email_sender: EmailSender = SmtpEmailSender() if settings.smtp_host else DisabledEmailSender()
