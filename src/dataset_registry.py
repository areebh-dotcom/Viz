"""Dataset metadata and relationships for the Viz conversational agent."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass(frozen=True)
class Column:
    """Represents a dataset column and the metadata required for prompting."""

    name: str
    type: str
    role: str
    description: Optional[str] = None


@dataclass(frozen=True)
class Dataset:
    """Logical dataset exposed through the conversational interface."""

    name: str
    table: str
    columns: List[Column]
    related: List[str] = field(default_factory=list)
    default_order_by: Optional[str] = None


DATASETS: Dict[str, Dataset] = {
    "subscribers": Dataset(
        name="subscribers",
        table="subscribers",
        columns=[
            Column("user_id", "uuid", "identifier", "Unique user identifier."),
            Column("region", "string", "category", "Geographic region for the user."),
            Column("plan_type", "string", "category", "Subscription plan type."),
            Column("join_date", "date", "temporal", "Date the user joined."),
            Column("status", "string", "category", "Current lifecycle status."),
            Column("monthly_spend", "numeric", "measure", "Average monthly revenue."),
        ],
        related=["payments", "logins"],
        default_order_by="join_date DESC",
    ),
    "payments": Dataset(
        name="payments",
        table="payments",
        columns=[
            Column("payment_id", "uuid", "identifier"),
            Column("user_id", "uuid", "identifier"),
            Column("amount", "numeric", "measure", "Net payment amount in USD."),
            Column("currency", "string", "category"),
            Column("payment_date", "date", "temporal"),
            Column("status", "string", "category"),
        ],
        related=["subscribers"],
        default_order_by="payment_date DESC",
    ),
    "logins": Dataset(
        name="logins",
        table="logins",
        columns=[
            Column("user_id", "uuid", "identifier"),
            Column("login_date", "date", "temporal"),
            Column("login_count", "numeric", "measure"),
            Column("device_type", "string", "category"),
            Column("region", "string", "category"),
            Column("plan_type", "string", "category"),
        ],
        related=["subscribers"],
        default_order_by="login_date DESC",
    ),
    "tickets": Dataset(
        name="tickets",
        table="tickets",
        columns=[
            Column("ticket_id", "uuid", "identifier"),
            Column("user_id", "uuid", "identifier"),
            Column("opened_at", "timestamp", "temporal"),
            Column("resolved_at", "timestamp", "temporal"),
            Column("category", "string", "category"),
            Column("severity", "string", "category"),
            Column("status", "string", "category"),
            Column("response_time_hours", "numeric", "measure"),
        ],
        related=["subscribers", "business_units"],
        default_order_by="opened_at DESC",
    ),
    "business_units": Dataset(
        name="business_units",
        table="business_units",
        columns=[
            Column("unit_id", "uuid", "identifier"),
            Column("unit_name", "string", "category"),
            Column("region", "string", "category"),
            Column("revenue", "numeric", "measure"),
            Column("headcount", "numeric", "measure"),
        ],
        related=["tickets", "payments"],
        default_order_by="revenue DESC",
    ),
}


def list_datasets() -> List[str]:
    """Return the list of available dataset keys."""

    return sorted(DATASETS.keys())


def get_dataset(name: str) -> Dataset:
    """Retrieve a dataset, raising a ValueError if it is not registered."""

    try:
        return DATASETS[name]
    except KeyError as exc:  # pragma: no cover - defensive programming
        raise ValueError(f"Unknown dataset '{name}'.") from exc
