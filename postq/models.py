from datetime import datetime
from typing import Any, Dict, List
from uuid import UUID, uuid4

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
    status: str = Field(default=enums.Status.initialized.name)
    results: dict = Field(default_factory=dict)
    errors: dict = Field(default_factory=dict)


class Workflow(Model):
    """
    A workflow defines what tasks are included in a Job. The tasks define their own
    dependencies. The resulting workflow must form a directed acyclic graph -- i.e.,
    there cannot be a dependency loop.

    * tasks - the tasks that are included in the workflow. key = name, value = Task
    * graph - (generated from tasks) the DAG (directed acyclic graph) of tasks (a
      networkx.DiGraph), which is validated as acyclic
    """

    tasks: List[Task] = Field(default_factory=list)
    graph: Any = Field(default_factory=nx.DiGraph)

    def dict(self, *args, **kwargs):
        # don't include graph in output, because it's not serializable, and it's built from tasks
        return {
            k: v for k, v in super().dict(*args, **kwargs).items() if k not in ['graph']
        }

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
                'The tasks graph must be acyclic, but it currently includes cycles.'
            )
        # the transitive reduction ensures the shortest version of the workflow.
        return nx.transitive_reduction(graph)

    @property
    def tasks_dict(self):
        return {task.name: task for task in self.tasks}

    @property
    def predecessors(self):
        """
        graph predecessors, with the keys in lexicographical topological sort order.
        """
        return {
            name: list(self.graph.pred[name].keys())
            for name in nx.lexicographical_topological_sort(self.graph)
        }

    @property
    def tasks_predecessors(self):
        return {
            task.name: [self.tasks_dict[name] for name in self.predecessors[task.name]]
            for task in self.tasks
        }

    @property
    def tasks_descendants(self):
        return {
            task.name: [
                self.tasks_dict[name] for name in nx.descendants(self.graph, task.name)
            ]
            for task in self.tasks
        }

    @property
    def completed_tasks(self):
        return list(
            filter(
                lambda task: (enums.Status[task.status] >= enums.Status.completed),
                self.tasks,
            )
        )

    @property
    def failed_tasks(self):
        return list(
            filter(
                lambda task: (enums.Status[task.status] >= enums.Status.cancelled),
                self.tasks,
            )
        )

    @property
    def ready_tasks(self):
        return list(
            filter(
                lambda task: (
                    # the task is not complete
                    enums.Status[task.status] < enums.Status.completed
                    # all the task's predecessors are completed
                    and all(
                        map(
                            lambda task: task in self.completed_tasks,
                            self.tasks_predecessors[task.name],
                        )
                    )
                    # none of the task's predecessors are failed
                    and all(
                        map(
                            lambda task: task not in self.failed_tasks,
                            self.tasks_predecessors[task.name],
                        )
                    )
                ),
                self.tasks,
            )
        )


class Job(Model):
    """
    A single job in the Job queue.
    """

    id: UUID = Field(default_factory=uuid4)
    qname: str
    retries: int = Field(default=1)
    status: str = Field(default=enums.Status.queued.name)
    queued: datetime = Field(default=None)
    scheduled: datetime = Field(default=None)
    workflow: Workflow = Field(default_factory=Workflow)
    data: dict = Field(default_factory=dict)

    @validator('status')
    def validate_job_status(cls, val, values, **kwargs):
        if val not in enums.Status.__members__.keys():
            raise ValueError(
                f'value must be one of {list(enums.Status.__members__.keys())}'
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
    status: str
    queued: datetime = Field(default=None)
    scheduled: datetime = Field(default=None)
    logged: datetime = Field(default=None)
    workflow: Workflow
    data: dict

    @validator('status')
    def validate_job_status(cls, val, values, **kwargs):
        if val not in enums.Status.__members__.keys():
            raise ValueError(
                f'value must be one of {list(enums.Status.__members__.keys())}'
            )
        return val
