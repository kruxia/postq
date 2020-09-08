from uuid import uuid4

import pytest

from postq import q
from postq.enums import Status
from postq.models import Job, Workflow
from postq.tests.mocks import mock_executor


@pytest.mark.asyncio
async def test_process_job_task_result_status():
    qname, number = 'test', 1
    data = [
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
    ]

    for item in data:
        job = Job(
            id=uuid4(), status='queued', qname=qname, workflow={'tasks': item['tasks']}
        )
        joblog = await q.process_job(qname, number, job, mock_executor)
        joblog.workflow = Workflow(**joblog.workflow)
        for task in joblog.workflow.tasks:
            assert task.status == item['status'][task.name]
        assert joblog.status == str(
            max(Status[task.status] for task in job.workflow.tasks)
        )
