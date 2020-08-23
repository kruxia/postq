from sqlalchemy import Column, DateTime, MetaData, SmallInteger, String, Table, text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from . import fields

metadata = MetaData(schema='postq')

Job = Table(
    'job',
    metadata,
    Column('id', UUID, primary_key=True, server_default=text("gen_random_uuid()")),
    Column('qname', String, nullable=False, index=True),
    Column('retries', SmallInteger, server_default=text("1"), index=True),
    Column(
        'queued',
        DateTime(timezone=True),
        nullable=False,
        server_default=text('current_timestamp'),
        index=True,
    ),
    Column(
        'scheduled',
        DateTime(timezone=True),
        nullable=False,
        server_default=text('current_timestamp'),
    ),
    Column('status', String, nullable=False),
    Column('workflow', JSONB, server_default=text("'{}'::jsonb")),
    Column('data', JSONB, server_default=text("'{}'::jsonb")),
)

# JobLog = log of jobs that have been completed
JobLog = Table(
    'job_log',
    metadata,
    Column('id', UUID),
    Column('qname', String, nullable=False),
    Column('retries', SmallInteger),
    Column('queued', DateTime(timezone=True), nullable=False),
    Column('scheduled', DateTime(timezone=True), nullable=False),
    Column(
        'logged',
        DateTime(timezone=True),
        nullable=False,
        server_default=text('current_timestamp'),
    ),
    Column('status', String, nullable=False, default=fields.JobStatus.queued.name),
    Column('workflow', JSONB, server_default=text("'{}'::jsonb")),
    Column('data', JSONB, server_default=text("'{}'::jsonb")),
    Column('errors', JSONB, server_default=text("'{}'::jsonb")),
)
