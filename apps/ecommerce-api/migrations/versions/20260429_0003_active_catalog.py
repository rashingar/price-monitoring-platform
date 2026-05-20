"""active catalog products

Revision ID: 20260429_0003
Revises: 20260429_0002
Create Date: 2026-05-02 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260429_0003"
down_revision = "20260429_0002"
branch_labels = None
depends_on = None


def _json_document() -> sa.types.TypeEngine:
    return sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    op.create_table(
        "catalog_products",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "catalog_source", sa.String(), nullable=False, server_default="sourceCata"
        ),
        sa.Column("model", sa.String(), nullable=False),
        sa.Column("mpn", sa.String(), nullable=False, server_default=""),
        sa.Column("name", sa.Text(), nullable=False, server_default=""),
        sa.Column("category", sa.Text(), nullable=False, server_default=""),
        sa.Column("raw_category", sa.Text(), nullable=False, server_default=""),
        sa.Column("family", sa.String(), nullable=False, server_default=""),
        sa.Column("category_name", sa.String(), nullable=False, server_default=""),
        sa.Column("sub_category", sa.String(), nullable=False, server_default=""),
        sa.Column("category_levels", _json_document(), nullable=True),
        sa.Column("manufacturer", sa.String(), nullable=False, server_default=""),
        sa.Column("price", sa.Numeric(12, 2), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=True),
        sa.Column("status", sa.Integer(), nullable=True),
        sa.Column("bestprice_status", sa.Integer(), nullable=True),
        sa.Column("skroutz_status", sa.Integer(), nullable=True),
        sa.Column(
            "is_atomic_model", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column(
            "automation_eligible",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_path", sa.Text(), nullable=True),
        sa.Column("source_filename", sa.String(), nullable=True),
        sa.Column("raw_catalog_row", _json_document(), nullable=True),
        sa.Column("warnings", _json_document(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "uq_catalog_products_catalog_source_model",
        "catalog_products",
        ["catalog_source", "model"],
        unique=True,
    )
    op.create_index(
        "ix_catalog_products_catalog_source_active",
        "catalog_products",
        ["catalog_source", "active"],
    )
    op.create_index("ix_catalog_products_model", "catalog_products", ["model"])
    op.create_index("ix_catalog_products_mpn", "catalog_products", ["mpn"])
    op.create_index(
        "ix_catalog_products_manufacturer", "catalog_products", ["manufacturer"]
    )
    op.create_index("ix_catalog_products_family", "catalog_products", ["family"])
    op.create_index(
        "ix_catalog_products_category_name", "catalog_products", ["category_name"]
    )
    op.create_index(
        "ix_catalog_products_sub_category", "catalog_products", ["sub_category"]
    )
    op.create_index(
        "ix_catalog_products_bestprice_status", "catalog_products", ["bestprice_status"]
    )
    op.create_index(
        "ix_catalog_products_skroutz_status", "catalog_products", ["skroutz_status"]
    )
    op.create_index(
        "ix_catalog_products_imported_at", "catalog_products", ["imported_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_catalog_products_imported_at", table_name="catalog_products")
    op.drop_index("ix_catalog_products_skroutz_status", table_name="catalog_products")
    op.drop_index("ix_catalog_products_bestprice_status", table_name="catalog_products")
    op.drop_index("ix_catalog_products_sub_category", table_name="catalog_products")
    op.drop_index("ix_catalog_products_category_name", table_name="catalog_products")
    op.drop_index("ix_catalog_products_family", table_name="catalog_products")
    op.drop_index("ix_catalog_products_manufacturer", table_name="catalog_products")
    op.drop_index("ix_catalog_products_mpn", table_name="catalog_products")
    op.drop_index("ix_catalog_products_model", table_name="catalog_products")
    op.drop_index(
        "ix_catalog_products_catalog_source_active", table_name="catalog_products"
    )
    op.drop_index(
        "uq_catalog_products_catalog_source_model", table_name="catalog_products"
    )
    op.drop_table("catalog_products")
