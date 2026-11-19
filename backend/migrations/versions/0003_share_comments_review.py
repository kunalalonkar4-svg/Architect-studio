"""share links, comments, review requests

Revision ID: 0003
Revises: 0002
"""
from alembic import op
import sqlalchemy as sa

revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def _ts(): return sa.Column('created_at', sa.DateTime(timezone=True), nullable=False)


def upgrade():
    op.create_table('share_links',
        sa.Column('id', sa.String(36), primary_key=True), sa.Column('project_id', sa.String(36), sa.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False),
        sa.Column('revision_id', sa.String(36), nullable=False), sa.Column('token', sa.String(64), nullable=False),
        sa.Column('allow_comments', sa.Boolean(), nullable=False), sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True), _ts())
    op.create_index('ix_share_links_project_id', 'share_links', ['project_id'])
    op.create_index('ix_share_links_token', 'share_links', ['token'], unique=True)
    op.create_table('comments',
        sa.Column('id', sa.String(36), primary_key=True), sa.Column('project_id', sa.String(36), sa.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False),
        sa.Column('share_id', sa.String(36), nullable=True), sa.Column('revision_id', sa.String(36), nullable=False),
        sa.Column('sheet_id', sa.String(100), nullable=True), sa.Column('author', sa.String(80), nullable=False),
        sa.Column('from_owner', sa.Boolean(), nullable=False), sa.Column('body', sa.Text(), nullable=False),
        sa.Column('resolved', sa.Boolean(), nullable=False), _ts())
    op.create_index('ix_comments_project_id', 'comments', ['project_id'])
    op.create_index('ix_comments_share_id', 'comments', ['share_id'])
    op.create_table('review_requests',
        sa.Column('id', sa.String(36), primary_key=True), sa.Column('project_id', sa.String(36), sa.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False),
        sa.Column('revision_id', sa.String(36), nullable=False), sa.Column('kind', sa.String(20), nullable=False),
        sa.Column('reviewer_name', sa.String(200), nullable=False), sa.Column('reviewer_contact', sa.String(300), nullable=False),
        sa.Column('note', sa.Text(), nullable=False), sa.Column('status', sa.String(20), nullable=False),
        sa.Column('outcome_note', sa.Text(), nullable=False), _ts(), sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False))
    op.create_index('ix_review_requests_project_id', 'review_requests', ['project_id'])


def downgrade():
    op.drop_table('review_requests'); op.drop_table('comments'); op.drop_table('share_links')
