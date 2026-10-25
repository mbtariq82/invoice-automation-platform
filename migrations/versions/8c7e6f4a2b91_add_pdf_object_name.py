"""store archived PDF object names

Revision ID: 8c7e6f4a2b91
Revises: 4b4dad0055e4
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "8c7e6f4a2b91"
down_revision: Union[str, Sequence[str], None] = "4b4dad0055e4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("invoice_records", sa.Column("pdf_object_name", sa.String(length=512), nullable=True))
    op.create_unique_constraint("uq_invoice_records_pdf_object_name", "invoice_records", ["pdf_object_name"])


def downgrade() -> None:
    op.drop_constraint("uq_invoice_records_pdf_object_name", "invoice_records", type_="unique")
    op.drop_column("invoice_records", "pdf_object_name")
