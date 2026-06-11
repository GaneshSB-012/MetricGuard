"""add incidents table phase 12

Revision ID: e88cb9958742
Revises: 2fb7994c49bc
Create Date: 2026-06-10 21:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e88cb9958742'
down_revision: Union[str, Sequence[str], None] = '2fb7994c49bc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'incidents',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('incident_id', sa.String(length=20), nullable=False),
        sa.Column('root_cause', sa.String(length=255), nullable=False),
        sa.Column('impacted_services', sa.String(length=1000), nullable=False),
        sa.Column('priority', sa.String(length=5), nullable=False),
        sa.Column('severity', sa.String(length=20), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='OPEN'),
        sa.Column('alert_count', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('group_key', sa.String(length=500), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint(
            "status IN ('OPEN', 'INVESTIGATING', 'MITIGATED', 'RESOLVED', 'CLOSED')",
            name='chk_incident_status_valid'
        ),
        sa.CheckConstraint(
            "priority IN ('P1', 'P2', 'P3', 'P4')",
            name='chk_incident_priority_valid'
        ),
        sa.CheckConstraint(
            "alert_count >= 1",
            name='chk_alert_count_positive'
        )
    )
    op.create_index(op.f('ix_incidents_id'), 'incidents', ['id'], unique=False)
    op.create_index(op.f('ix_incidents_incident_id'), 'incidents', ['incident_id'], unique=True)
    op.create_index(op.f('ix_incidents_root_cause'), 'incidents', ['root_cause'], unique=False)
    op.create_index(op.f('ix_incidents_priority'), 'incidents', ['priority'], unique=False)
    op.create_index(op.f('ix_incidents_severity'), 'incidents', ['severity'], unique=False)
    op.create_index(op.f('ix_incidents_status'), 'incidents', ['status'], unique=False)
    op.create_index(op.f('ix_incidents_group_key'), 'incidents', ['group_key'], unique=False)
    op.create_index(op.f('ix_incidents_created_at'), 'incidents', ['created_at'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_incidents_created_at'), table_name='incidents')
    op.drop_index(op.f('ix_incidents_group_key'), table_name='incidents')
    op.drop_index(op.f('ix_incidents_status'), table_name='incidents')
    op.drop_index(op.f('ix_incidents_severity'), table_name='incidents')
    op.drop_index(op.f('ix_incidents_priority'), table_name='incidents')
    op.drop_index(op.f('ix_incidents_root_cause'), table_name='incidents')
    op.drop_index(op.f('ix_incidents_incident_id'), table_name='incidents')
    op.drop_index(op.f('ix_incidents_id'), table_name='incidents')
    op.drop_table('incidents')
