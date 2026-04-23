import random
import string
from typing import Optional

from django.utils.text import slugify
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings
from django.apps import apps

from core.models import LearningActivity


def send_email(user, subject, msg):
    send_mail(
        subject,
        msg,
        settings.EMAIL_FROM_ADDRESS,
        [user.email],
        fail_silently=False,
    )


def send_html_email(subject, recipient_list, template, context):
    """A function responsible for sending HTML email"""
    # Render the HTML template
    html_message = render_to_string(template, context)

    # Generate plain text version of the email (optional)
    plain_message = strip_tags(html_message)

    # Send the email
    send_mail(
        subject,
        plain_message,
        settings.EMAIL_FROM_ADDRESS,
        recipient_list,
        html_message=html_message,
    )


def random_string_generator(size=10, chars=string.ascii_lowercase + string.digits):
    return "".join(random.choice(chars) for _ in range(size))


def unique_slug_generator(instance, new_slug=None):
    """
    Assumes the instance has a model with a slug field and a title
    character (char) field.
    """
    if new_slug is not None:
        slug = new_slug
    else:
        base = getattr(instance, "title", "") or ""
        slug = slugify(base)

        # slugify() returns empty for non-latin titles (e.g. Chinese).
        # Fall back to other identifiers commonly present on our models.
        if not slug:
            for attr in ("code", "username", "session", "semester"):
                val = getattr(instance, attr, None)
                if not val:
                    continue
                slug = slugify(str(val))
                if slug:
                    break

        if not slug:
            slug = random_string_generator(size=12)

    klass = instance.__class__
    qs_exists = klass.objects.filter(slug=slug).exists()
    if qs_exists:
        new_slug = f"{slug}-{random_string_generator(size=4)}"
        return unique_slug_generator(instance, new_slug=new_slug)
    return slug


def log_learning_activity(
    user,
    activity_type: str,
    description: str = "",
    course=None,
    duration_seconds: Optional[int] = None,
):
    """
    统一记录学习行为，方便后续统计与可视化。
    """
    if user is None or not user.is_authenticated:
        return

    student = None
    try:
        if hasattr(user, "is_student") and user.is_student:
            Student = apps.get_model("accounts", "Student")
            student = Student.objects.filter(student__pk=user.id).first()
    except Exception:
        student = None

    LearningActivity.objects.create(
        user=user,
        student=student,
        course=course,
        activity_type=activity_type,
        description=description or "",
        duration_seconds=duration_seconds,
    )
