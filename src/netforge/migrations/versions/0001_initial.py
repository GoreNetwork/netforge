"""Create tasks and task_logs

Revision ID: 0001
Revises:
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tasks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("task_type", sa.String(100), nullable=False),
        sa.Column("engine", sa.String(50), nullable=False),
        sa.Column("variables", JSONB, nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("result", JSONB),
        sa.Column("error", sa.Text),
        sa.Column("submitted_via", sa.String(20), nullable=False),
        sa.Column("worker_id", sa.String(100)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_tasks_status_created", "tasks", ["status", "created_at"])
    op.create_index("ix_tasks_created", "tasks", ["created_at"])
    op.create_table(
        "task_logs",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("task_id", UUID(as_uuid=True), sa.ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("line", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_task_logs_task_id", "task_logs", ["task_id", "id"])


def downgrade() -> None:
    op.drop_table("task_logs")
    op.drop_table("tasks")
