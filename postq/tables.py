from sqlalchemy import Column, DateTime, MetaData, SmallInteger, String, Table, text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from . import enums

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

Job.get = lambda: text(
    """
    UPDATE postq.job job1 SET retries = retries - 1
    WHERE job1.id = ( 
        SELECT job2.id FROM postq.job job2 
        WHERE job2.qname=:qname
        AND job2.retries > 0
        AND job2.scheduled <= now()
        ORDER BY job2.queued
        FOR UPDATE SKIP LOCKED LIMIT 1 
    )
    RETURNING job1.*;
    """.strip()
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
    Column('status', String, nullable=False, default=enums.Status.queued.name),
    Column('workflow', JSONB, server_default=text("'{}'::jsonb")),
    Column('data', JSONB, server_default=text("'{}'::jsonb")),
    Column('errors', JSONB, server_default=text("'{}'::jsonb")),
)
