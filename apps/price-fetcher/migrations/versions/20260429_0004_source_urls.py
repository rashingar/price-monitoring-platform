"""manual source urls

Revision ID: 20260429_0004
Revises: 20260429_0003
Create Date: 2026-05-02 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "20260429_0004"
down_revision = "20260429_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "source_urls",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("catalog_product_id", sa.Integer(), nullable=False),
        sa.Column("catalog_source", sa.String(), nullable=False),
        sa.Column("model", sa.String(), nullable=False),
        sa.Column("mpn", sa.String(), nullable=False, server_default=""),
        sa.Column("manufacturer", sa.String(), nullable=False, server_default=""),
        sa.Column("source_name", sa.String(), nullable=False),
        sa.Column("source_domain", sa.String(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("url_normalized", sa.Text(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="active"),
        sa.Column("url_type", sa.String(), nullable=False, server_default="manual"),
        sa.Column("trust_level", sa.String(), nullable=False, server_default="manual"),
        sa.Column("added_by", sa.String(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('active', 'disabled', 'broken', 'redirected', 'needs_review')",
            name="ck_source_urls_status",
        ),
        sa.CheckConstraint("url_type IN ('manual', 'imported', 'discovered')", name="ck_source_urls_url_type"),
        sa.ForeignKeyConstraint(["catalog_product_id"], ["catalog_products.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("catalog_product_id", "url_normalized", name="uq_source_urls_catalog_product_url_normalized"),
    )
    op.create_index("ix_source_urls_catalog_product_id", "source_urls", ["catalog_product_id"])
    op.create_index("ix_source_urls_catalog_source_model", "source_urls", ["catalog_source", "model"])
    op.create_index("ix_source_urls_source_name", "source_urls", ["source_name"])
    op.create_index("ix_source_urls_source_domain", "source_urls", ["source_domain"])
    op.create_index("ix_source_urls_status", "source_urls", ["status"])
    op.create_index("ix_source_urls_updated_at", "source_urls", ["updated_at"])


def downgrade() -> None:
    op.drop_index("ix_source_urls_updated_at", table_name="source_urls")
    op.drop_index("ix_source_urls_status", table_name="source_urls")
    op.drop_index("ix_source_urls_source_domain", table_name="source_urls")
    op.drop_index("ix_source_urls_source_name", table_name="source_urls")
    op.drop_index("ix_source_urls_catalog_source_model", table_name="source_urls")
    op.drop_index("ix_source_urls_catalog_product_id", table_name="source_urls")
    op.drop_table("source_urls")
