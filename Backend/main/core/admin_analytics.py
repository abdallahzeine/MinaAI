"""Admin analytics — aggregated stats over LLM-collected event leads.

Pure read-only aggregation over Conversation / ChatMessage / EventLead.
Used by the /admin dashboard. Never raises: failure returns an empty payload.
"""

from collections import Counter
from datetime import datetime, timedelta
from typing import Any

from django.db.models import Count
from django.utils import timezone


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def _local_date(dt: datetime) -> str:
    return timezone.localtime(dt).date().isoformat()


def _local_hour(dt: datetime) -> int:
    return timezone.localtime(dt).hour


def build_admin_analytics(days: int = 30) -> dict[str, Any]:
    from ..models import ChatMessage, Conversation, EventLead, LEAD_FIELDS

    total_sessions = Conversation.objects.count()
    total_messages = ChatMessage.objects.count()

    leads_qs = (
        EventLead.objects.select_related("conversation")
        .annotate(message_count=Count("conversation__chat_messages"))
        .order_by("-updated_at")
    )

    leads: list[dict[str, Any]] = []
    captured: Counter[str] = Counter()
    consented = 0
    company_counts: Counter[str] = Counter()
    position_counts: Counter[str] = Counter()
    completeness_sum = 0

    for lead in leads_qs:
        fields = {f: (getattr(lead, f) or "").strip() for f in LEAD_FIELDS}
        for name, value in fields.items():
            if value:
                captured[name] += 1
        nonempty = sum(1 for value in fields.values() if value)
        completeness = round(nonempty * 100 / len(LEAD_FIELDS))
        completeness_sum += completeness
        if lead.consent:
            consented += 1
        if fields["company_name"]:
            company_counts[fields["company_name"]] += 1
        if fields["position"]:
            position_counts[fields["position"]] += 1
        leads.append(
            {
                "id": lead.id,
                "session_id": lead.conversation.session_id,
                "name": fields["formal_name"] or None,
                "position": fields["position"] or None,
                "company": fields["company_name"] or None,
                "phone": fields["phone"] or None,
                "email": fields["email"] or None,
                "consent": lead.consent,
                "completeness": completeness,
                "message_count": lead.message_count,
                "created_at": _iso(lead.created_at),
                "updated_at": _iso(lead.updated_at),
            }
        )

    total_leads = len(leads)
    avg_completeness = round(completeness_sum / total_leads) if total_leads else 0

    now = timezone.now()
    start = now - timedelta(days=days - 1)
    lead_dates = Counter(
        _local_date(d)
        for d in EventLead.objects.filter(created_at__gte=start).values_list("created_at", flat=True)
    )
    message_dates = Counter(
        _local_date(d)
        for d in ChatMessage.objects.filter(created_at__gte=start).values_list("created_at", flat=True)
    )
    timeline: list[dict[str, Any]] = []
    for offset in range(days):
        day = (start + timedelta(days=offset)).date()
        label = day.isoformat()
        timeline.append(
            {
                "date": label,
                "leads": lead_dates.get(label, 0),
                "messages": message_dates.get(label, 0),
            }
        )

    lead_hours = Counter(
        _local_hour(d)
        for d in EventLead.objects.values_list("created_at", flat=True)
        if d is not None
    )
    hourly: list[dict[str, Any]] = [{"hour": h, "leads": lead_hours.get(h, 0)} for h in range(24)]

    lead_message_total = sum(lead["message_count"] for lead in leads)
    avg_msgs_lead = round(lead_message_total / total_leads) if total_leads else 0
    avg_msgs_session = round(total_messages / total_sessions) if total_sessions else 0
    conversion_rate = round(total_leads * 100 / total_sessions) if total_sessions else 0

    return {
        "generated_at": _iso(now),
        "overview": {
            "total_sessions": total_sessions,
            "total_messages": total_messages,
            "total_leads": total_leads,
            "consented_leads": consented,
            "conversion_rate": conversion_rate,
            "avg_completeness": avg_completeness,
            "avg_messages_per_session": avg_msgs_session,
            "avg_messages_per_lead": avg_msgs_lead,
            "captured": {field: captured.get(field, 0) for field in LEAD_FIELDS},
        },
        "leads": leads,
        "timeline": timeline,
        "hourly": hourly,
        "companies": [
            {"name": name, "count": count} for name, count in company_counts.most_common(10)
        ],
        "positions": [
            {"name": name, "count": count} for name, count in position_counts.most_common(10)
        ],
        "field_labels": {
            "formal_name": "Name",
            "position": "Position",
            "company_name": "Company",
            "phone": "Phone",
            "email": "Email",
        },
    }