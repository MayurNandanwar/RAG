import os
import aiosmtplib
import asyncio
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587


class EmailConfigError(Exception):
    pass


def _get_email_config():
    sender_email = os.getenv("SENDER_EMAIL", "").strip()
    sender_password = os.getenv("SENDER_PASSWORD", "").strip()

    if not sender_email or not sender_password:
        raise EmailConfigError(
            "Email is not configured. Set SENDER_EMAIL and SENDER_PASSWORD in .env. "
            "For Gmail, use an App Password from https://myaccount.google.com/apppasswords"
        )

    return sender_email, sender_password



async def send_approval_email(
    receiver_email: str,
    approval_id: str,
    query: str,
):
    sender_email, sender_password = _get_email_config()

    if not receiver_email:
        raise EmailConfigError(
            "Reviewer email is not configured. "
            "Set REVIEWER_EMAIL in .env."
        )

    approve_url = (
        f"http://localhost:8000/approve/{approval_id}"
    )

    reject_url = (
        f"http://localhost:8000/reject/{approval_id}"
    )

    html = f"""
    <html>
    <body>

    <h2>Human Approval Required</h2>

    <p><b>Query:</b></p>

    <div style="
        padding:10px;
        border:1px solid #ccc;
        background:#f5f5f5;
        margin-bottom:20px;">
        {query}
    </div>

    <a href="{approve_url}"
       style="
       background:#28a745;
       color:white;
       padding:12px 25px;
       text-decoration:none;
       border-radius:5px;
       margin-right:20px;">

        Approve

    </a>

    <a href="{reject_url}"
       style="
       background:#dc3545;
       color:white;
       padding:12px 25px;
       text-decoration:none;
       border-radius:5px;">

        Reject

    </a>

    </body>
    </html>
    """

    message = MIMEMultipart("alternative")

    message["Subject"] = "Human Approval Required"
    message["From"] = sender_email
    message["To"] = receiver_email

    message.attach(
        MIMEText(html, "html")
    )

    try:

        await aiosmtplib.send(
            message,
            hostname=SMTP_SERVER,
            port=SMTP_PORT,
            start_tls=True,
            username=sender_email,
            password=sender_password,
            timeout=30,
        )

    except aiosmtplib.SMTPAuthenticationError as exc:

        raise EmailConfigError(
            "Gmail login failed. "
            "Use a Gmail App Password (not your normal password) "
            "in SENDER_PASSWORD."
        ) from exc

    except aiosmtplib.SMTPException as exc:

        raise EmailConfigError(
            f"Failed to send approval email: {exc}"
        ) from exc

    print(
        f"Approval email sent to "
        f"{receiver_email} for request {approval_id}"
    )






async def send_answer_to_user(
    receiver_email: str,
    query: str,
    answer: str):

    sender_email, sender_password = _get_email_config()

    html = f"""
    <html>
    <body>

    <h2>Your AI Request Has Been Reviewed</h2>

    <p>Your request has been reviewed and approved by our team.</p>

    <h3>Question</h3>

    <div style="padding:10px;background:#f5f5f5;border:1px solid #ccc;">
    {query}
    </div>

    <br>

    <h3>Approved Answer</h3>

    <div style="
        padding:10px;
        background:#eef6ff;
        border:1px solid #007bff;
        white-space:pre-wrap;">
    {answer}
    </div>

    </body>
    </html>
    """

    message = MIMEMultipart("alternative")
    message["Subject"] = "Your AI Response"
    message["From"] = sender_email
    message["To"] = receiver_email
    message.attach(MIMEText(html, "html"))

    await aiosmtplib.send(
        message,
        hostname=SMTP_SERVER,
        port=SMTP_PORT,
        start_tls=True,
        username=sender_email,
        password=sender_password
    )

    # with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
    #     server.starttls()
    #     server.login(sender_email, sender_password)
    #     server.sendmail(sender_email, receiver_email, message.as_string())



async def send_rejection_email(
    receiver_email: str,
    query: str,
    reason: str = None,
):
    sender_email, sender_password = _get_email_config()

    reason_html = ""
    if reason:
        reason_html = f"""
        <h3>Reason</h3>
        <div style="
            padding:10px;
            background:#fff3cd;
            border:1px solid #ffeeba;
            margin-bottom:20px;">
            {reason}
        </div>
        """

    html = f"""
    <html>
    <body>

    <h2>Your Request Could Not Be Approved</h2>

    <p>After review, your request could not be approved.</p>

    <h3>Your Query</h3>

    <div style="
        padding:10px;
        border:1px solid #ccc;
        background:#f5f5f5;
        margin-bottom:20px;">
        {query}
    </div>

    {reason_html}

    <p>
        If you believe this was a mistake or would like a different response,
        please submit a new request with additional details.
    </p>

    </body>
    </html>
    """

    message = MIMEMultipart("alternative")
    message["Subject"] = "Update on Your AI Request"
    message["From"] = sender_email
    message["To"] = receiver_email
    message.attach(MIMEText(html, "html"))

    await aiosmtplib.send(
        message,
        hostname=SMTP_SERVER,
        port=SMTP_PORT,
        start_tls=True,
        username=sender_email,
        password=sender_password
    )


    # with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
    #     server.starttls()
    #     server.login(sender_email, sender_password)
    #     server.sendmail(sender_email, receiver_email, message.as_string())


