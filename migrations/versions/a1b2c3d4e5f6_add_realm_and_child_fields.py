"""add realm and child-friendly fields to animals

Revision ID: a1b2c3d4e5f6
Revises: c5b4cb279d49
Create Date: 2026-07-02 07:30:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = 'c5b4cb279d49'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('animals', schema=None) as batch_op:
        batch_op.add_column(sa.Column('realm', sa.String(length=20), nullable=False, server_default='Land'))
        batch_op.add_column(sa.Column('human_activities', sa.Text(), nullable=False, server_default=''))
        batch_op.add_column(sa.Column('ecological_role', sa.Text(), nullable=False, server_default=''))
        batch_op.add_column(sa.Column('fun_fact', sa.Text(), nullable=False, server_default=''))
        batch_op.add_column(sa.Column('why_endangered', sa.Text(), nullable=False, server_default=''))
        batch_op.add_column(sa.Column('emoji', sa.String(length=16), nullable=False, server_default='\U0001F43E'))
        batch_op.add_column(sa.Column('accent', sa.String(length=20), nullable=False, server_default='leaf'))


def downgrade() -> None:
    with op.batch_alter_table('animals', schema=None) as batch_op:
        batch_op.drop_column('accent')
        batch_op.drop_column('emoji')
        batch_op.drop_column('why_endangered')
        batch_op.drop_column('fun_fact')
        batch_op.drop_column('ecological_role')
        batch_op.drop_column('human_activities')
        batch_op.drop_column('realm')
