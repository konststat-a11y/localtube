"""baseline current schema

Revision ID: 001_baseline
Revises:
Create Date: 2026-05-28
"""

from alembic import op
import sqlalchemy as sa


revision = "001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(length=80), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("is_admin", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_users_id"), "users", ["id"], unique=False)
    op.create_index(op.f("ix_users_username"), "users", ["username"], unique=True)

    op.create_table(
        "videos",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("author", sa.String(length=255), nullable=False),
        sa.Column("category", sa.String(length=120), nullable=False),
        sa.Column("file_path", sa.String(length=1024), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("is_available", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("file_path"),
    )
    op.create_index(op.f("ix_videos_filename"), "videos", ["filename"], unique=False)
    op.create_index(op.f("ix_videos_id"), "videos", ["id"], unique=False)

    op.create_table(
        "comments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("video_id", sa.Integer(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["video_id"], ["videos.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_comments_created_at"), "comments", ["created_at"], unique=False)
    op.create_index(op.f("ix_comments_id"), "comments", ["id"], unique=False)
    op.create_index(op.f("ix_comments_user_id"), "comments", ["user_id"], unique=False)
    op.create_index(op.f("ix_comments_video_id"), "comments", ["video_id"], unique=False)

    op.create_table(
        "video_access",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("video_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["video_id"], ["videos.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "video_id", name="uq_user_video_access"),
    )
    op.create_index(op.f("ix_video_access_id"), "video_access", ["id"], unique=False)
    op.create_index(op.f("ix_video_access_user_id"), "video_access", ["user_id"], unique=False)
    op.create_index(op.f("ix_video_access_video_id"), "video_access", ["video_id"], unique=False)

    op.create_table(
        "video_progress",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("video_id", sa.Integer(), nullable=False),
        sa.Column("current_seconds", sa.Integer(), nullable=False),
        sa.Column("duration_seconds", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["video_id"], ["videos.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "video_id", name="uq_user_video_progress"),
    )
    op.create_index(op.f("ix_video_progress_id"), "video_progress", ["id"], unique=False)
    op.create_index(op.f("ix_video_progress_updated_at"), "video_progress", ["updated_at"], unique=False)
    op.create_index(op.f("ix_video_progress_user_id"), "video_progress", ["user_id"], unique=False)
    op.create_index(op.f("ix_video_progress_video_id"), "video_progress", ["video_id"], unique=False)

    op.create_table(
        "video_reactions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("video_id", sa.Integer(), nullable=False),
        sa.Column("value", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["video_id"], ["videos.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "video_id", name="uq_user_video_reaction"),
    )
    op.create_index(op.f("ix_video_reactions_id"), "video_reactions", ["id"], unique=False)
    op.create_index(op.f("ix_video_reactions_user_id"), "video_reactions", ["user_id"], unique=False)
    op.create_index(op.f("ix_video_reactions_video_id"), "video_reactions", ["video_id"], unique=False)

    op.create_table(
        "view_history",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("video_id", sa.Integer(), nullable=False),
        sa.Column("viewed_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["video_id"], ["videos.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "video_id", name="uq_user_video_history"),
    )
    op.create_index(op.f("ix_view_history_id"), "view_history", ["id"], unique=False)
    op.create_index(op.f("ix_view_history_user_id"), "view_history", ["user_id"], unique=False)
    op.create_index(op.f("ix_view_history_video_id"), "view_history", ["video_id"], unique=False)
    op.create_index(op.f("ix_view_history_viewed_at"), "view_history", ["viewed_at"], unique=False)

    op.create_table(
        "watch_later",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("video_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["video_id"], ["videos.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "video_id", name="uq_user_video_watch_later"),
    )
    op.create_index(op.f("ix_watch_later_created_at"), "watch_later", ["created_at"], unique=False)
    op.create_index(op.f("ix_watch_later_id"), "watch_later", ["id"], unique=False)
    op.create_index(op.f("ix_watch_later_user_id"), "watch_later", ["user_id"], unique=False)
    op.create_index(op.f("ix_watch_later_video_id"), "watch_later", ["video_id"], unique=False)


def downgrade() -> None:
    op.drop_table("watch_later")
    op.drop_table("view_history")
    op.drop_table("video_reactions")
    op.drop_table("video_progress")
    op.drop_table("video_access")
    op.drop_table("comments")
    op.drop_table("videos")
    op.drop_table("users")
