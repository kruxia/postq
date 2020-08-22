"""init

Revision ID: 7e8956a72cf2
Revises: 
Create Date: 2020-08-22 19:33:46.423666+00:00

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = '7e8956a72cf2'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute("CREATE SCHEMA IF NOT EXISTS postq")


def downgrade():
    op.execute('DROP SCHEMA IF EXISTS postq')
