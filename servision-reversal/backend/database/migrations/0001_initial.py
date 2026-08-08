"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-01-01
"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "strategy_versions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("label", sa.String(50), index=True),
        sa.Column("config_json", sa.JSON),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("notes", sa.Text, server_default=""),
    )
    op.create_table(
        "observations",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("symbol", sa.String(12), index=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), index=True,
                  server_default=sa.func.now()),
        sa.Column("as_of_epoch", sa.Integer, index=True),
        sa.Column("strategy_version_id", sa.Integer, sa.ForeignKey("strategy_versions.id")),
        sa.Column("price", sa.Float),
        sa.Column("move_pct", sa.Float),
        sa.Column("volume_ratio", sa.Float),
        sa.Column("vwap_distance_pct", sa.Float),
        sa.Column("higher_low", sa.Boolean),
        sa.Column("vwap_reclaim", sa.Boolean),
        sa.Column("eps_surprise_pct", sa.Float),
        sa.Column("revenue_surprise_pct", sa.Float),
        sa.Column("catalyst", sa.String(20)),
        sa.Column("score_total", sa.Float, index=True),
        sa.Column("status", sa.String(12), index=True),
        sa.Column("components_json", sa.JSON),
        sa.Column("snapshot_json", sa.JSON),
    )
    op.create_table(
        "paper_trades",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("symbol", sa.String(12), index=True),
        sa.Column("strategy_version_id", sa.Integer, sa.ForeignKey("strategy_versions.id")),
        sa.Column("opened_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("setup", sa.String(60), server_default="Earnings reversal"),
        sa.Column("instrument", sa.String(10), server_default="equity"),
        sa.Column("entry_price", sa.Float),
        sa.Column("stop_price", sa.Float),
        sa.Column("target1", sa.Float),
        sa.Column("target2", sa.Float),
        sa.Column("entry_epoch", sa.Integer),
        sa.Column("option_type", sa.String(4)),
        sa.Column("strike", sa.Float),
        sa.Column("expiration", sa.String(12)),
        sa.Column("entry_premium", sa.Float),
        sa.Column("status", sa.String(12), server_default="open"),
        sa.Column("exit_price", sa.Float),
        sa.Column("exit_epoch", sa.Integer),
        sa.Column("exit_reason", sa.String(20)),
        sa.Column("return_pct", sa.Float),
        sa.Column("score_at_entry", sa.Float),
        sa.Column("components_json", sa.JSON),
    )
    op.create_table(
        "backtests",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("strategy_version_id", sa.Integer, sa.ForeignKey("strategy_versions.id")),
        sa.Column("params_json", sa.JSON),
        sa.Column("results_json", sa.JSON),
        sa.Column("label", sa.String(120), server_default=""),
    )


def downgrade() -> None:
    op.drop_table("backtests")
    op.drop_table("paper_trades")
    op.drop_table("observations")
    op.drop_table("strategy_versions")
