"""price monitoring dashboard alerts

Revision ID: 20260429_0002
Revises: 20260429_0001
Create Date: 2026-04-29 00:10:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260429_0002"
down_revision = "20260429_0001"
branch_labels = None
depends_on = None


def _json_document() -> sa.types.TypeEngine:
    return sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    op.create_table(
        "alert_rules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("rule_type", sa.String(), nullable=False),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id", ondelete="SET NULL"), nullable=True),
        sa.Column("catalog_source", sa.String(), nullable=True),
        sa.Column("model", sa.String(), nullable=True),
        sa.Column("mpn", sa.String(), nullable=True),
        sa.Column("threshold_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("threshold_percent", sa.Numeric(12, 4), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("rule_type = 'competitor_below_own_price'", name="ck_alert_rules_rule_type"),
        sa.CheckConstraint("threshold_amount IS NULL OR threshold_amount > 0", name="ck_alert_rules_threshold_amount_positive"),
        sa.CheckConstraint("threshold_percent IS NULL OR threshold_percent > 0", name="ck_alert_rules_threshold_percent_positive"),
    )
    op.create_index("ix_alert_rules_active", "alert_rules", ["active"])
    op.create_index("ix_alert_rules_rule_type", "alert_rules", ["rule_type"])
    op.create_index("ix_alert_rules_product_id", "alert_rules", ["product_id"])
    op.create_index("ix_alert_rules_catalog_source_model", "alert_rules", ["catalog_source", "model"])
    op.create_index("ix_alert_rules_catalog_source_mpn", "alert_rules", ["catalog_source", "mpn"])
    op.create_index("ix_alert_rules_created_at", "alert_rules", ["created_at"])

    op.create_table(
        "alert_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("alert_rule_id", sa.Integer(), sa.ForeignKey("alert_rules.id", ondelete="CASCADE"), nullable=False),
        sa.Column("monitoring_run_id", sa.Integer(), sa.ForeignKey("monitoring_runs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("price_observation_id", sa.Integer(), sa.ForeignKey("price_observations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id", ondelete="SET NULL"), nullable=True),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("catalog_source", sa.String(), nullable=True),
        sa.Column("model", sa.String(), nullable=True),
        sa.Column("mpn", sa.String(), nullable=True),
        sa.Column("source", sa.String(), nullable=True),
        sa.Column("competitor_name", sa.String(), nullable=True),
        sa.Column("competitor_price", sa.Numeric(12, 2), nullable=True),
        sa.Column("own_price", sa.Numeric(12, 2), nullable=True),
        sa.Column("price_delta", sa.Numeric(12, 2), nullable=True),
        sa.Column("price_delta_percent", sa.Numeric(12, 4), nullable=True),
        sa.Column("severity", sa.String(), nullable=False, server_default="warning"),
        sa.Column("status", sa.String(), nullable=False, server_default="open"),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("dedupe_key", sa.String(), nullable=False),
        sa.Column("triggered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acknowledged_by", sa.String(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by", sa.String(), nullable=True),
        sa.Column("raw_context", _json_document(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('open', 'acknowledged', 'resolved')", name="ck_alert_events_status"),
        sa.CheckConstraint("severity = 'warning'", name="ck_alert_events_severity"),
    )
    op.create_index("ix_alert_events_alert_rule_id", "alert_events", ["alert_rule_id"])
    op.create_index("ix_alert_events_product_id", "alert_events", ["product_id"])
    op.create_index("ix_alert_events_run_id", "alert_events", ["run_id"])
    op.create_index("ix_alert_events_status", "alert_events", ["status"])
    op.create_index("ix_alert_events_triggered_at", "alert_events", ["triggered_at"])
    op.create_index("uq_alert_events_dedupe_key", "alert_events", ["dedupe_key"], unique=True)


def downgrade() -> None:
    op.drop_index("uq_alert_events_dedupe_key", table_name="alert_events")
    op.drop_index("ix_alert_events_triggered_at", table_name="alert_events")
    op.drop_index("ix_alert_events_status", table_name="alert_events")
    op.drop_index("ix_alert_events_run_id", table_name="alert_events")
    op.drop_index("ix_alert_events_product_id", table_name="alert_events")
    op.drop_index("ix_alert_events_alert_rule_id", table_name="alert_events")
    op.drop_table("alert_events")

    op.drop_index("ix_alert_rules_created_at", table_name="alert_rules")
    op.drop_index("ix_alert_rules_catalog_source_mpn", table_name="alert_rules")
    op.drop_index("ix_alert_rules_catalog_source_model", table_name="alert_rules")
    op.drop_index("ix_alert_rules_product_id", table_name="alert_rules")
    op.drop_index("ix_alert_rules_rule_type", table_name="alert_rules")
    op.drop_index("ix_alert_rules_active", table_name="alert_rules")
    op.drop_table("alert_rules")
