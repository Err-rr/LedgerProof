"""initial schema

Revision ID: af2df6d2622e
Revises:
Create Date: 2026-08-31 10:17:40.262201

Creates the four tables the API persists a reconciliation run into: runs,
match_records, exceptions, journal_lines. All monetary columns are BIGINT
paisa -- never numeric/float -- per CLAUDE.md rule 1. Primary keys are
application-generated UUID4 strings (see api/reconcile.py), stored as TEXT
so the app layer never needs a Postgres extension (pgcrypto/uuid-ossp) that
a free-tier Neon project may not have enabled.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'af2df6d2622e'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "runs",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("uploaded_files", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("summary", postgresql.JSONB(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "match_records",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("run_id", sa.Text(), sa.ForeignKey("runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("pass_number", sa.Integer(), nullable=False),
        sa.Column("method", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("evidence", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("matched_at", sa.Text(), nullable=False),
        sa.Column("record_type", sa.Text(), nullable=False),
        sa.Column("left_id", sa.Text(), nullable=False),
        sa.Column("right_id", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_match_records_run_id", "match_records", ["run_id"])

    op.create_table(
        "exceptions",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("run_id", sa.Text(), sa.ForeignKey("runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("severity", sa.Text(), nullable=False),
        sa.Column("record_type", sa.Text(), nullable=False),
        sa.Column("record_id", sa.Text(), nullable=False),
        sa.Column("amount_paisa", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("rupee_at_risk_paisa", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("details", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("status", sa.Text(), nullable=False, server_default="open"),
        sa.Column("resolution", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_exceptions_run_id", "exceptions", ["run_id"])
    # Powers GET /runs/{id}/exceptions, which lists exceptions by rupee amount desc.
    op.create_index(
        "ix_exceptions_run_id_rupee_at_risk",
        "exceptions",
        ["run_id", sa.text("rupee_at_risk_paisa DESC")],
    )

    op.create_table(
        "journal_lines",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("run_id", sa.Text(), sa.ForeignKey("runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("order_id", sa.Text(), nullable=False),
        sa.Column("account", sa.Text(), nullable=False),
        sa.Column("direction", sa.Text(), nullable=False),
        sa.Column("amount_paisa", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_journal_lines_run_id", "journal_lines", ["run_id"])

    op.create_check_constraint("ck_exceptions_status", "exceptions", "status IN ('open', 'resolved')")
    op.create_check_constraint("ck_journal_lines_direction", "journal_lines", "direction IN ('Dr', 'Cr')")


def downgrade() -> None:
    op.drop_table("journal_lines")
    op.drop_index("ix_exceptions_run_id_rupee_at_risk", table_name="exceptions")
    op.drop_index("ix_exceptions_run_id", table_name="exceptions")
    op.drop_table("exceptions")
    op.drop_index("ix_match_records_run_id", table_name="match_records")
    op.drop_table("match_records")
    op.drop_table("runs")
