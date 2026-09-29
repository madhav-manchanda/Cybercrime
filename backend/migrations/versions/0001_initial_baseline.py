"""initial baseline schema

Baseline migration that materialises the current ORM metadata.  Because models
are the single source of truth for the schema (and the same DDL is produced by
``init_sync_schema``/``scripts.seed``), this revision snapshots that metadata by
calling ``Base.metadata.create_all`` instead of hand-written DDL.  On
PostgreSQL it first enables the PostGIS extension so spatial columns work.

Downstream schema changes MUST be written as explicit Alembic revisions (use
``alembic revision --autogenerate`` against a live database) - this baseline
should not change.

Revision ID: 0001_initial_baseline
Revises:
Create Date: 2026-09-28

"""
from __future__ import annotations

from alembic import op

import app.models  # noqa: F401  ensure all model modules are loaded before metadata
from app.core.database import Base

revision = "0001_initial_baseline"
down_revision: str | None = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name.startswith("postgresql"):
        op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind, checkfirst=True)