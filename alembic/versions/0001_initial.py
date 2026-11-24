"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-11-24
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sources",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("secret", sa.String(64), nullable=False),
        sa.Column("target_url", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_table(
        "events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "source_id", sa.Uuid(), sa.ForeignKey("sources.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("external_id", sa.String(200), nullable=True),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("delivery_status", sa.String(20), nullable=False),
        sa.Column(
            "received_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("source_id", "external_id", name="uq_events_source_external_id"),
    )
    op.create_index("ix_events_source_id", "events", ["source_id"])
    op.create_index("ix_events_source_received", "events", ["source_id", "received_at"])
    op.create_table(
        "deliveries",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "event_id", sa.Uuid(), sa.ForeignKey("events.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("ok", sa.Boolean(), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_deliveries_event_id", "deliveries", ["event_id"])


def downgrade() -> None:
    op.drop_table("deliveries")
    op.drop_table("events")
    op.drop_table("sources")
