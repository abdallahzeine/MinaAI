import logging

from django.db import models

logger = logging.getLogger(__name__)


class Conversation(models.Model):
    session_id = models.CharField(max_length=128, unique=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return self.session_id


class Setting(models.Model):
    key = models.CharField(max_length=128, unique=True, db_index=True)
    value = models.TextField(default="")
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"{self.key}={self.value}"


class ChatMessage(models.Model):
    conversation = models.ForeignKey(
        Conversation, on_delete=models.CASCADE, related_name="chat_messages"
    )
    type = models.CharField(max_length=16)
    content = models.TextField()
    data = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [models.Index(fields=["conversation", "created_at"])]

    def __str__(self) -> str:
        return f"{self.type}:{self.conversation_id}:{self.pk}"


LEAD_FIELDS = ("formal_name", "position", "company_name", "phone", "email")


class EventLead(models.Model):
    conversation = models.OneToOneField(
        Conversation, on_delete=models.CASCADE, related_name="event_lead"
    )
    formal_name = models.CharField(max_length=255, null=True, blank=True)
    position = models.CharField(max_length=255, null=True, blank=True)
    company_name = models.CharField(max_length=255, null=True, blank=True)
    phone = models.CharField(max_length=64, null=True, blank=True)
    email = models.EmailField(max_length=254, null=True, blank=True)
    consent = models.BooleanField(null=True, blank=True, default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"EventLead:{self.conversation_id}:{self.pk}"


def save_lead_silently(session_id: str, extracted_data: dict | None = None):
    try:
        if not session_id:
            return None
        if extracted_data is None:
            extracted_data = {}
        conversation, _ = Conversation.objects.get_or_create(session_id=session_id)
        lead, _ = EventLead.objects.get_or_create(conversation=conversation)
        allowed_fields = LEAD_FIELDS + ("consent",)
        updated = False
        for field in allowed_fields:
            if field in extracted_data:
                value = extracted_data[field]
                if value is not None:
                    setattr(lead, field, value)
                    updated = True
        if updated:
            lead.save()
        return lead
    except Exception:
        logger.exception("Failed to save lead silently for session %s", session_id)
        return None
