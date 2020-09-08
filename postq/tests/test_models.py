import json
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from postq.models import Job, JobLog


def test_job_joblog_invalid():
    """
    Invalid Job/Log definitions raise ValidationErrors
    """
    for tasks in [
        # 'b' depends on 'c', which doesn't exist
        [{'name': 'a'}, {'name': 'b', 'depends': ['c']}],
        # 'a' and 'b' depend each other, so the graph is not acyclic, as required
        [{'name': 'a', 'depends': ['b']}, {'name': 'b', 'depends': ['a']}],
    ]:
        with pytest.raises(ValidationError):
            Job(qname='test', workflow={'tasks': tasks})
        with pytest.raises(ValidationError):
            JobLog(
                id=uuid4(),
                qname='test',
                status='queued',
                retries=0,
                workflow={'tasks': tasks},
                data={},
            )

    # Job/Log with invalid status
    with pytest.raises(ValidationError):
        Job(qname='test', status='bad')
    with pytest.raises(ValidationError):
        JobLog(
            id=uuid4(),
            qname='test',
            status='bad',
            retries=0,
            workflow={'tasks': tasks},
            data={},
        )


def test_job_log_workflow_data_str():
    """
    Job/Log.workflow and Job/Log.data can be converted from a str
    """
    tasks = [{'name': 'a'}, {'name': 'b', 'depends': ['a']}]
    workflow = {'tasks': tasks}
    data = {'some': 'info', 'that': 'this', 'job': 'uses'}
    assert Job(qname='test', workflow=workflow, data=data) == Job(
        qname='test', workflow=json.dumps(workflow), data=json.dumps(data)
    )
    joblog_id = uuid4()
    timestamp = datetime.now(tz=timezone.utc)
    jl1 = JobLog(
        id=joblog_id,
        qname='test',
        initialized=timestamp,
        status='queued',
        retries=0,
        workflow=workflow,
        data=data,
    )
    jl2 = JobLog(
        id=joblog_id,
        qname='test',
        initialized=timestamp,
        status='queued',
        retries=0,
        workflow=json.dumps(workflow),
        data=json.dumps(data),
    )
    assert jl1.dict() == jl2.dict()
