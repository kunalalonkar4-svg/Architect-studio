"""blob storage table (used when STORAGE_BACKEND=db)

Revision ID: 0002
Revises: 0001
"""
from alembic import op
import sqlalchemy as sa

revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('blobs', sa.Column('key', sa.String(length=600), primary_key=True), sa.Column('data', sa.LargeBinary(), nullable=False))


def downgrade():
    op.drop_table('blobs')
