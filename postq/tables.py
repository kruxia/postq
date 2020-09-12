from sqlalchemy import Column, DateTime, MetaData, String, Table, text
from sqlalchemy.dialects.postgresql import JSONB, UUID

metadata = MetaData(schema='postq')

Job = Table(
    'job',
    metadata,
    Column('id', UUID, primary_key=True, server_default=text("gen_random_uuid()")),
    Column('qname', String, nullable=False, index=True),
    Column('status', String, nullable=False),
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
    Column('initialized', DateTime(timezone=True), nullable=True),
    Column(
        'logged',
        DateTime(timezone=True),
        nullable=True,
    ),
    Column('tasks', JSONB, server_default=text("'{}'::jsonb")),
    Column('data', JSONB, server_default=text("'{}'::jsonb")),
)

Job.get = (
    lambda: """
    UPDATE postq.job job1 SET status = 'processing'
    WHERE job1.id = ( 
        SELECT job2.id FROM postq.job job2 
        WHERE job2.qname = :qname
        AND job2.status = 'queued'
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
    Column('id', UUID, nullable=False),
    Column('qname', String, nullable=False),
    Column('queued', DateTime(timezone=True), nullable=False),
    Column('scheduled', DateTime(timezone=True), nullable=False),
    Column('initialized', DateTime(timezone=True), nullable=True),
    Column(
        'logged',
        DateTime(timezone=True),
        nullable=False,
        server_default=text('current_timestamp'),
    ),
    Column('status', String, nullable=False),
    Column('tasks', JSONB, server_default=text("'{}'::jsonb")),
    Column('data', JSONB, server_default=text("'{}'::jsonb")),
)
