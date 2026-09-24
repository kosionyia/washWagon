"""add payment details

Revision ID: 8a6d1e4c2b90
Revises: f66d97aa4b2a
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
import sqlmodel


revision: str = "8a6d1e4c2b90"
down_revision: Union[str, Sequence[str], None] = "f66d97aa4b2a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    payment_method = sa.Enum("ONLINE", "CASH", name="paymentmethod")
    payment_method.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "payments",
        sa.Column("method", payment_method, nullable=False, server_default="ONLINE"),
    )
    op.add_column(
        "payments",
        sa.Column(
            "currency",
            sqlmodel.sql.sqltypes.AutoString(length=3),
            nullable=False,
            server_default="NGN",
        ),
    )
    op.add_column(
        "payments",
        sa.Column("authorization_url", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    )
    op.add_column(
        "payments",
        sa.Column("access_code", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    )
    op.add_column("payments", sa.Column("paid_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("payments", "paid_at")
    op.drop_column("payments", "access_code")
    op.drop_column("payments", "authorization_url")
    op.drop_column("payments", "currency")
    op.drop_column("payments", "method")
    sa.Enum(name="paymentmethod").drop(op.get_bind(), checkfirst=True)
