"""
Mailer: console (default/dev) or SMTP (prod — works with AWS SES SMTP, or any provider).
Stdlib only. The magic link is the only email this system ever sends in Phase 0.
"""
import logging
import os
import smtplib
import ssl
from email.message import EmailMessage

log = logging.getLogger("rms.mailer")

PROVIDER = os.environ.get("MAIL_PROVIDER", "console")  # console | smtp | disabled
SMTP_HOST = os.environ.get("SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASS = os.environ.get("SMTP_PASS", "")
MAIL_FROM = os.environ.get("MAIL_FROM", "signin@ratemy.systems")
ENV = os.environ.get("RMS_ENV", "dev")


class MailUnavailable(RuntimeError):
    pass


def send_magic_link(email: str, link: str) -> None:
    if PROVIDER == "smtp" and SMTP_HOST:
        msg = EmailMessage()
        msg["Subject"] = "Your Rate My Systems sign-in link"
        msg["From"] = MAIL_FROM
        msg["To"] = email
        msg.set_content(
            "Tap to sign in (valid 15 minutes, single use):\n\n"
            f"{link}\n\n"
            "If you didn't request this, ignore it. Nothing happens without the link.\n"
            "— Rate My Systems · no names, no individual ratings shown, ever"
        )
        ctx = ssl.create_default_context()   # verified TLS to the SMTP relay
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as s:
            s.starttls(context=ctx)
            if SMTP_USER:
                s.login(SMTP_USER, SMTP_PASS)
            s.send_message(msg)
        return
    if PROVIDER == "disabled":
        raise MailUnavailable("email sign-in is disabled")
    # console: DEV ONLY. In prod this path is unreachable — startup refuses to boot
    # with MAIL_PROVIDER=console (see security.validate_prod_env). Never logs in prod.
    if ENV == "prod":
        raise MailUnavailable("refusing to log a magic link in prod")
    log.warning("MAIL(console/dev) to=%s link=%s", email, link)
