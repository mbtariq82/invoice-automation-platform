"""add invoice ownership

Revision ID: a7f1c2d3e4b5
Revises: 4b4dad0055e4
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "a7f1c2d3e4b5"
down_revision: Union[str, Sequence[str], None] = "4b4dad0055e4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("invoice_records", sa.Column("created_by", sa.String(length=255), nullable=True))
    op.create_index("ix_invoice_records_created_by", "invoice_records", ["created_by"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_invoice_records_created_by", table_name="invoice_records")
    op.drop_column("invoice_records", "created_by")
