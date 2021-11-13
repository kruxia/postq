import json
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from postq.models import Job


@pytest.mark.parametrize(
    'tasks',
    [
        # 'b' depends on 'c', which doesn't exist
        {'a': {}, 'b': {'depends': ['c']}},
        # 'a' and 'b' depend each other, so the graph is not acyclic, as required
        {'a': {'depends': ['b']}, 'b': {'depends': ['a']}},
    ],
)
def test_job_joblog_invalid(tasks):
    """
    Invalid Job definitions raise ValidationErrors
    """
    with pytest.raises(ValidationError):
        Job(qname='test', tasks=tasks)


def test_job_log_invalid_status():
    # Job/Log with invalid status
    with pytest.raises(ValidationError):
        Job(qname='test', status='bad')


def test_job_log_workflow_data_str():
    """
    Job/Log.workflow and Job/Log.data can be converted from a str
    """
    tasks = {'a': {}, 'b': {'depends': ['a']}}
    data = {'some': 'info', 'that': 'this', 'job': 'uses'}
    job_id = uuid4()
    timestamp = datetime.now(tz=timezone.utc)
    jl1 = Job(
        id=job_id,
        qname='test',
        initialized=timestamp,
        status='queued',
        tasks=tasks,
        data=data,
    )
    jl2 = Job(
        id=job_id,
        qname='test',
        initialized=timestamp,
        status='queued',
        tasks=json.dumps(tasks),
        data=json.dumps(data),
    )
    assert jl1.dict() == jl2.dict()
