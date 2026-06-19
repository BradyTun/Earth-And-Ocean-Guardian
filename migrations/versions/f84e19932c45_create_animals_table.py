"""create animals table

Revision ID: f84e19932c45
Revises: 
Create Date: 2026-06-13 15:41:46.678306
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f84e19932c45'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'animals',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('common_name', sa.String(length=120), nullable=False),
        sa.Column('scientific_name', sa.String(length=180), nullable=False),
        sa.Column('species_group', sa.String(length=80), nullable=False),
        sa.Column('conservation_status', sa.String(length=80), nullable=False),
        sa.Column('habitat', sa.String(length=120), nullable=False),
        sa.Column('region', sa.String(length=160), nullable=False),
        sa.Column('threats', sa.Text(), nullable=False),
        sa.Column('how_to_help', sa.Text(), nullable=False),
        sa.Column('population_trend', sa.Text(), nullable=False),
        sa.Column('image_url', sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('common_name', name='uq_animals_common_name'),
    )


def downgrade() -> None:
    op.drop_table('animals')
