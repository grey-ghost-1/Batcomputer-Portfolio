"""Rename the assistant intents table to z_intents."""

from collections.abc import Sequence

from alembic import op

revision: str = "20261014_01"
down_revision: str | None = "20260826_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.rename_table("alfred_intents", "z_intents")


def downgrade() -> None:
    op.rename_table("z_intents", "alfred_intents")
