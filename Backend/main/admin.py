import django_stubs_ext

django_stubs_ext.monkeypatch()

from django.contrib import admin

from .models import ChatMessage, Conversation, EventLead


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin[Conversation]):
    list_display = ("session_id", "created_at", "updated_at")
    search_fields = ("session_id",)


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin[ChatMessage]):
    list_display = ("conversation", "type", "created_at")
    list_filter = ("type",)
    search_fields = ("content",)


@admin.register(EventLead)
class EventLeadAdmin(admin.ModelAdmin[EventLead]):
    list_display = (
        "conversation",
        "formal_name",
        "position",
        "company_name",
        "phone",
        "email",
        "consent",
        "created_at",
        "updated_at",
    )
    search_fields = (
        "formal_name",
        "position",
        "company_name",
        "phone",
        "email",
        "conversation__session_id",
    )
    readonly_fields = ("created_at", "updated_at")
    list_filter = ("consent",)
