from uuid import uuid4

import pytest
import sqly

from postq import q
from postq.enums import Status
from postq.executors import shell_executor
from postq.models import Job, Queue
from postq.tests.mocks import mock_executor


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "item",
    [
        # the simplest workflow: one task, no dependencies.
        {
            'tasks': {'a': {'depends': [], 'params': {'status': 'success'}}},
            'results': {'a': {'status': 'success'}},
        },
        # if the first task fails, the dependent one is cancelled.
        {
            'tasks': {
                'a': {'depends': [], 'params': {'status': 'failure'}},
                'b': {'depends': ['a'], 'params': {'status': 'success'}},
            },
            'results': {'a': {'status': 'failure'}, 'b': {'status': 'cancelled'}},
        },
        # if a task fails, all dependent tasks are cancelled, but others run
        {
            'tasks': {
                'a': {'depends': [], 'params': {'status': 'success'}},
                'b': {'depends': ['a'], 'params': {'status': 'failure'}},
                'c': {'depends': ['a'], 'params': {'status': 'success'}},
                'd': {'depends': ['b'], 'params': {'status': 'success'}},
                'e': {'depends': ['c'], 'params': {'status': 'success'}},
                'f': {'depends': ['d', 'e'], 'params': {'status': 'success'}},
            },
            'results': {
                'a': {'status': 'success'},
                'b': {'status': 'failure'},
                'c': {'status': 'success'},
                'd': {'status': 'cancelled'},  # depends on 'b'
                'e': {'status': 'success'},
                'f': {'status': 'cancelled'},  # depends on 'd' -> 'b'
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
    job = Job(id=uuid4(), status='queued', qname=qname, tasks=item['tasks'])
    joblog = await q.process_job(qname, number, job, mock_executor)
    for task_name, task in joblog.tasks.items():
        assert task.status == item['results'][task_name]['status']
    assert joblog.status == str(
        max(Status[task.status] for task in joblog.tasks.values())
    )


@pytest.mark.asyncio
async def test_transact_job(database, connection):
    """
    Use the queue database to transact a single job, and verify that the job was
    completed correctly. (This tests the transaction process, not the workflow logic.)
    """
    # queue the job
    queue = Queue(qname='test', dialect=sqly.Dialect.ASYNCPG)
    job = Job(qname=queue.qname, tasks={'a': {'command': 'ls'}})
    job.update(**await connection.fetchrow(*queue.put(job)))
    print(job.dict())

    # process one job from the queue
    result = await q.transact_one_job(
        database, queue, 1, shell_executor, connection=connection
    )
    job_record = await connection.fetchrow(*queue.get())
    joblog_record = await connection.fetchrow(
        *queue.dialect.render(
            "select * from postq.job_log where id=:job_id limit 1",
            {'job_id': job.id},
        )
    )
    assert result is True
    assert job_record is None  # already deleted
    assert joblog_record['id'] == job.id  # and logged
