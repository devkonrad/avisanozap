from functools import lru_cache
from pathlib import Path

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from jinja2 import Environment, FileSystemLoader, select_autoescape


@lru_cache(maxsize=1)
def get_email_environment():
    template_dir = (
        Path(settings.BASE_DIR)
        / "templates"
        / "jinja2"
        / "emails"
    )

    return Environment(
        loader=FileSystemLoader(template_dir),
        autoescape=select_autoescape(
            enabled_extensions=("html", "xml"),
        ),
    )


def send_templated_email(
    *,
    subject,
    recipient,
    template_name,
    context,
):
    if not recipient:
        raise ValueError("An email recipient is required.")

    environment = get_email_environment()

    text_template = environment.get_template(
        f"{template_name}.txt",
    )
    html_template = environment.get_template(
        f"{template_name}.html",
    )

    text_body = text_template.render(**context)
    html_body = html_template.render(**context)

    message = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[recipient],
    )
    message.attach_alternative(html_body, "text/html")

    sent_count = message.send(fail_silently=False)

    if sent_count != 1:
        raise RuntimeError(
            f"Email delivery failed for {recipient}."
        )
