"""add user profile fields

Revision ID: 002_user_profiles
Revises: 001_baseline
Create Date: 2026-05-28
"""

from alembic import op
import sqlalchemy as sa


revision = "002_user_profiles"
down_revision = "001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("email", sa.String(length=255), nullable=True))
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)

    op.create_table(
        "user_profiles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("bio", sa.Text(), nullable=False, server_default=""),
        sa.Column("avatar_path", sa.String(length=1024), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", name="uq_user_profile_user"),
    )
    op.create_index(op.f("ix_user_profiles_id"), "user_profiles", ["id"], unique=False)
    op.create_index(op.f("ix_user_profiles_user_id"), "user_profiles", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_table("user_profiles")
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_column("users", "email")
