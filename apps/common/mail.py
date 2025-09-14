import logging
from dataclasses import dataclass


logger = logging.getLogger(__name__)


@dataclass
class MailMessage:
    to: str
    subject: str
    body: str


class MailProvider:
    def send(self, msg: MailMessage):  # pragma: no cover - base
        raise NotImplementedError


class ConsoleMailProvider(MailProvider):
    def send(self, msg: MailMessage):
        logger.info("[DEV MAIL] To: %s — Subject: %s — Body: %s", msg.to, msg.subject, msg.body)


default_mail_provider = ConsoleMailProvider()

