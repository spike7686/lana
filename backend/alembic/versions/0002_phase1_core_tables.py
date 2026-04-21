"""phase1 core tables

Revision ID: 0002_phase1_core_tables
Revises: 0001_baseline
Create Date: 2026-04-20 00:10:00

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0002_phase1_core_tables"
down_revision: Union[str, None] = "0001_baseline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "asset_pool",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("symbol", sa.String(length=32), nullable=False, unique=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column(
            "list_tags",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint("status IN ('active','inactive')", name="ck_asset_pool_status"),
        sa.CheckConstraint("source IN ('auto','manual')", name="ck_asset_pool_source"),
    )
    op.create_index("ix_asset_pool_status", "asset_pool", ["status"], unique=False)

    for table_name in ("kline_15m", "kline_1h"):
        op.create_table(
            table_name,
            sa.Column("symbol", sa.String(length=32), nullable=False),
            sa.Column("open_time", sa.DateTime(timezone=True), nullable=False),
            sa.Column("open", sa.Numeric(28, 12), nullable=False),
            sa.Column("high", sa.Numeric(28, 12), nullable=False),
            sa.Column("low", sa.Numeric(28, 12), nullable=False),
            sa.Column("close", sa.Numeric(28, 12), nullable=False),
            sa.Column("volume", sa.Numeric(28, 12), nullable=False),
            sa.Column("quote_volume", sa.Numeric(28, 12), nullable=True),
            sa.Column("trades", sa.Integer(), nullable=True),
            sa.PrimaryKeyConstraint("symbol", "open_time", name=f"pk_{table_name}"),
        )

    for table_name in ("oi_15m", "oi_1h"):
        op.create_table(
            table_name,
            sa.Column("symbol", sa.String(length=32), nullable=False),
            sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
            sa.Column("sum_open_interest", sa.Numeric(28, 12), nullable=True),
            sa.Column("sum_open_interest_value", sa.Numeric(28, 12), nullable=True),
            sa.PrimaryKeyConstraint("symbol", "ts", name=f"pk_{table_name}"),
        )

    op.create_table(
        "asset_profile",
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=True),
        sa.Column("sector", sa.String(length=128), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("website", sa.Text(), nullable=True),
        sa.Column("twitter", sa.Text(), nullable=True),
        sa.Column(
            "extra",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("symbol", name="pk_asset_profile"),
    )

    op.create_table(
        "collector_task_log",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("task_type", sa.String(length=64), nullable=False),
        sa.Column(
            "scope",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column(
            "summary",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "status IN ('running','success','failed')",
            name="ck_collector_task_log_status",
        ),
    )


def downgrade() -> None:
    op.drop_table("collector_task_log")
    op.drop_table("asset_profile")
    op.drop_table("oi_1h")
    op.drop_table("oi_15m")
    op.drop_table("kline_1h")
    op.drop_table("kline_15m")
    op.drop_index("ix_asset_pool_status", table_name="asset_pool")
    op.drop_table("asset_pool")
