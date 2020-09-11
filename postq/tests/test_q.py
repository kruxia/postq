from uuid import uuid4

import pytest

from postq import q, tables
from postq.enums import Status
from postq.executors import shell_executor
from postq.models import Job, Workflow
from postq.tests.mocks import mock_executor


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "item",
    [
        # the simplest workflow: one task, no dependencies.
        {
            'tasks': [{'name': 'a', 'depends': [], 'params': {'status': 'success'}}],
            'status': {'a': 'success'},
        },
        # if the first task fails, the dependent one is cancelled.
        {
            'tasks': [
                {'name': 'a', 'depends': [], 'params': {'status': 'failure'}},
                {'name': 'b', 'depends': ['a'], 'params': {'status': 'success'}},
            ],
            'status': {'a': 'failure', 'b': 'cancelled'},
        },
        # if a task fails, all dependent tasks are cancelled, but others run
        {
            'tasks': [
                {'name': 'a', 'depends': [], 'params': {'status': 'success'}},
                {'name': 'b', 'depends': ['a'], 'params': {'status': 'failure'}},
                {'name': 'c', 'depends': ['a'], 'params': {'status': 'success'}},
                {'name': 'd', 'depends': ['b'], 'params': {'status': 'success'}},
                {'name': 'e', 'depends': ['c'], 'params': {'status': 'success'}},
                {'name': 'f', 'depends': ['d', 'e'], 'params': {'status': 'success'}},
            ],
            'status': {
                'a': 'success',
                'b': 'failure',
                'c': 'success',
                'd': 'cancelled',
                'e': 'success',
                'f': 'cancelled',
            },
        },
    ],
)
async def test_process_job_task_result_status(item):
    """
    For each item, process the job and verify that the result status of each task and
    the job as a whole is as expected.
    """
    qname, number = 'test', 1
    job = Job(
        id=uuid4(), status='queued', qname=qname, workflow={'tasks': item['tasks']}
    )
    joblog = await q.process_job(qname, number, job, mock_executor)
    joblog.workflow = Workflow(**joblog.workflow)
    for task in joblog.workflow.tasks:
        assert task.status == item['status'][task.name]
    assert joblog.status == str(max(Status[task.status] for task in job.workflow.tasks))


@pytest.mark.asyncio
async def test_transact_job(database):
    """
    Use the queue database to transact a single job, and verify that the job was
    completed correctly. (This tests the transaction process, not the workflow logic.)
    """
    # queue the job
    qname = 'test'
    job = Job(
        qname=qname, workflow={'tasks': [{'name': 'a', 'params': {'command': "ls"}}]}
    )
    record = await database.fetch_one(
        tables.Job.insert().returning(*tables.Job.c), values=job.dict()
    )
    job.update(**record)

    # process one job from the queue
    result = await q.transact_one_job(database, qname, 1, shell_executor)
    job_record = await database.fetch_one(
        tables.Job.select().where(tables.Job.c.id == job.id).limit(1)
    )
    joblog_record = await database.fetch_one(
        tables.JobLog.select().where(tables.JobLog.c.id == job.id).limit(1)
    )
    assert result is True
    assert job_record is None  # already deleted
    assert joblog_record['id'] == job.id  # and logged
