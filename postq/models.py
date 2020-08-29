from datetime import datetime
from typing import Any, List
from uuid import UUID

import networkx as nx
from pydantic import BaseModel, Field, validator
from sqlalchemy import text

from . import enums, tables


class Model(BaseModel):
    def dict(self, exclude_none=True, **kwargs):
        return super().dict(exclude_none=exclude_none, **kwargs)


class Task(Model):
    """
    A single task in a Job workflow

    * name = the unique name of this task in this workflow
    * depends = the other tasks (names) that must be completed before this task
    * params = other parameters, such as executor-specific parameters
    """

    name: str
    depends: List[str] = Field(default_factory=list)
    params: dict = Field(default_factory=dict)


class Workflow(Model):
    """
    A workflow defines what tasks are included in a Job. The tasks define their own
    dependencies. The resulting workflow must form a directed acyclic graph -- i.e.,
    there cannot be a dependency loop.

    * tasks - the tasks that are included in the workflow
    * graph - the DAG (directed acyclic graph) of tasks (a networkx.DiGraph), which is
      generated from the tasks dependencies and validated as acyclic
    """

    tasks: List[Task] = Field(default_factory=list)
    graph: Any = Field(default_factory=nx.DiGraph)

    @validator('tasks')
    def validate_tasks(cls, value, values, **kwargs):
        """
        Ensure that all Task.depends are defined as Tasks.
        """
        errors = []
        task_names = [task.name for task in value]
        for task in value:
            for depend_name in task.depends:
                if depend_name not in task_names:
                    errors.append(
                        f"Task '{task.name}' depends on undefined Task '{depend_name}'."
                    )
        if errors:
            raise ValueError(' '.join(errors))
        return value

    @validator('graph', always=True)
    def validate_graph(cls, value, values, **kwargs):
        """
        Build the Workflow.graph from the Workflow.tasks, and ensure that the graph is
        acyclic (a directed acyclic graph).
        """
        graph = nx.DiGraph()
        for task in values.get('tasks') or []:
            for depend_name in task.depends:
                graph.add_edge(depend_name, task.name)
        if not nx.is_directed_acyclic_graph(graph):
            raise ValueError(
                'The tasks graph must be acyclic but contains one or more cycles.'
            )
        return graph


class Job(Model):
    """
    A single job in the Job queue.
    """

    id: UUID = Field(default=None)
    qname: str
    retries: int = Field(default=1)
    queued: datetime = Field(default=None)
    scheduled: datetime = Field(default=None)
    status: str = Field(default=enums.JobStatus.queued.name)
    workflow: Workflow = Field(default_factory=Workflow)
    data: dict = Field(default_factory=dict)

    class Config:
        orm_mode = True

    @validator('status')
    def validate_job_status(cls, val, values, **kwargs):
        if val not in enums.JobStatus.__members__.keys():
            raise ValueError(
                f'value must be one of {list(enums.JobStatus.__members__.keys())}'
            )
        return val

    # queries
    @classmethod
    def put(cls):
        return tables.Job.insert().returning(*tables.Job.columns)

    @classmethod
    def get(cls):
        return text(
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

    @classmethod
    def delete(cls):
        return tables.Job.delete()


class JobLog(Model):
    """
    A logged Job to maintain a historical record of Jobs that have been completed.
    """

    id: UUID
    qname: str
    retries: int
    queued: datetime
    scheduled: datetime
    status: str
    tasks: dict
    data: dict
    logged: datetime = Field(default=None)
    errors: dict = Field(default_factory=dict)

    class Config:
        orm_mode = True

    @validator('status')
    def validate_job_status(cls, val, values, **kwargs):
        if val not in enums.JobStatus.__members__.keys():
            raise ValueError(
                f'value must be one of {list(enums.JobStatus.__members__.keys())}'
            )
        return val


class Queue(Model):
    qname: str = Field(default=None)
