"""ops hierarchy and roles

Revision ID: 8fca0566a70a
Revises: rev_20260405_fix_sequences
Create Date: 2026-07-23 22:00:51.771378

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '8fca0566a70a'
down_revision: Union[str, None] = 'rev_20260405_fix_sequences'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('ops_companies',
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.Column('created_by', sa.Integer(), nullable=True),
    sa.Column('updated_by', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
    sa.ForeignKeyConstraint(['updated_by'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('ops_user_roles',
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('role', sa.String(length=50), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('user_id')
    )
    op.create_table('ops_projects',
    sa.Column('company_id', sa.UUID(), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.Column('created_by', sa.Integer(), nullable=True),
    sa.Column('updated_by', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['company_id'], ['ops_companies.id'], ),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
    sa.ForeignKeyConstraint(['updated_by'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_ops_projects_company_id'), 'ops_projects', ['company_id'], unique=False)
    op.create_table('ops_sites',
    sa.Column('project_id', sa.UUID(), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('location', sa.String(length=300), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.Column('created_by', sa.Integer(), nullable=True),
    sa.Column('updated_by', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
    sa.ForeignKeyConstraint(['project_id'], ['ops_projects.id'], ),
    sa.ForeignKeyConstraint(['updated_by'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_ops_sites_project_id'), 'ops_sites', ['project_id'], unique=False)
    op.create_table('ops_wells',
    sa.Column('site_id', sa.UUID(), nullable=False),
    sa.Column('legacy_well_id', sa.Integer(), nullable=True),
    sa.Column('legal_well_name', sa.String(length=200), nullable=False),
    sa.Column('common_well_name', sa.String(length=200), nullable=True),
    sa.Column('uwi', sa.String(length=100), nullable=True),
    sa.Column('operator', sa.String(length=200), nullable=True),
    sa.Column('api_no', sa.String(length=100), nullable=True),
    sa.Column('description', sa.String(length=200), nullable=True),
    sa.Column('target_formation', sa.String(length=200), nullable=True),
    sa.Column('purpose', sa.String(length=200), nullable=True),
    sa.Column('reason', sa.String(length=200), nullable=True),
    sa.Column('spud_date', sa.Date(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.Column('created_by', sa.Integer(), nullable=True),
    sa.Column('updated_by', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
    sa.ForeignKeyConstraint(['legacy_well_id'], ['wells.id'], ),
    sa.ForeignKeyConstraint(['site_id'], ['ops_sites.id'], ),
    sa.ForeignKeyConstraint(['updated_by'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_ops_wells_site_id'), 'ops_wells', ['site_id'], unique=False)
    op.create_index(op.f('ix_ops_wells_uwi'), 'ops_wells', ['uwi'], unique=False)
    op.create_table('ops_wellbores',
    sa.Column('well_id', sa.UUID(), nullable=False),
    sa.Column('parent_wellbore_id', sa.UUID(), nullable=True),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('sidetrack_no', sa.String(length=20), nullable=True),
    sa.Column('trajectory_type', sa.String(length=50), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.Column('created_by', sa.Integer(), nullable=True),
    sa.Column('updated_by', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
    sa.ForeignKeyConstraint(['parent_wellbore_id'], ['ops_wellbores.id'], ),
    sa.ForeignKeyConstraint(['updated_by'], ['users.id'], ),
    sa.ForeignKeyConstraint(['well_id'], ['ops_wells.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_ops_wellbores_well_id'), 'ops_wellbores', ['well_id'], unique=False)
    op.create_table('ops_events',
    sa.Column('wellbore_id', sa.UUID(), nullable=False),
    sa.Column('event_code', sa.String(length=50), nullable=True),
    sa.Column('event_type', sa.String(length=50), nullable=True),
    sa.Column('objective', sa.String(length=200), nullable=True),
    sa.Column('contractor', sa.String(length=200), nullable=True),
    sa.Column('rig_name', sa.String(length=200), nullable=True),
    sa.Column('start_date', sa.Date(), nullable=True),
    sa.Column('end_date', sa.Date(), nullable=True),
    sa.Column('authorized_cost', sa.Integer(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.Column('created_by', sa.Integer(), nullable=True),
    sa.Column('updated_by', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
    sa.ForeignKeyConstraint(['updated_by'], ['users.id'], ),
    sa.ForeignKeyConstraint(['wellbore_id'], ['ops_wellbores.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_ops_events_wellbore_id'), 'ops_events', ['wellbore_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_ops_events_wellbore_id'), table_name='ops_events')
    op.drop_table('ops_events')
    op.drop_index(op.f('ix_ops_wellbores_well_id'), table_name='ops_wellbores')
    op.drop_table('ops_wellbores')
    op.drop_index(op.f('ix_ops_wells_uwi'), table_name='ops_wells')
    op.drop_index(op.f('ix_ops_wells_site_id'), table_name='ops_wells')
    op.drop_table('ops_wells')
    op.drop_index(op.f('ix_ops_sites_project_id'), table_name='ops_sites')
    op.drop_table('ops_sites')
    op.drop_index(op.f('ix_ops_projects_company_id'), table_name='ops_projects')
    op.drop_table('ops_projects')
    op.drop_table('ops_user_roles')
    op.drop_table('ops_companies')
