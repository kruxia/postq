import json
from datetime import datetime, timezone
from typing import Any, List
from uuid import UUID

import networkx as nx
from pydantic import BaseModel, Field, validator

from . import enums


class Model(BaseModel):
    def dict(self, exclude_none=True, **kwargs):
        return super().dict(exclude_none=exclude_none, **kwargs)

    def update(self, **kwargs):
        self.__dict__.update(**kwargs)


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
    results: str = Field(default_factory=str)
    errors: str = Field(default_factory=str)


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
            graph.add_node(task.name)  # make sure every task is added
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
    def ancestors(self):
        """
        graph ancestors, with the keys in lexicographical topological sort order.
        """
        return {
            name: list(nx.ancestors(self.graph, name))
            for name in nx.lexicographical_topological_sort(self.graph)
        }

    @property
    def tasks_ancestors(self):
        return {
            task.name: [self.tasks_dict[name] for name in self.ancestors[task.name]]
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
    def started_tasks(self):
        """
        Started tasks are those with a Status value greater than or equal to
        Status.processing
        """
        return list(
            filter(
                lambda task: (enums.Status[task.status] >= enums.Status.processing),
                self.tasks,
            )
        )

    @property
    def completed_tasks(self):
        """
        Completed tasks are those with a Status value greater than or equal to
        Status.completed
        """
        return list(
            filter(
                lambda task: (enums.Status[task.status] >= enums.Status.completed),
                self.tasks,
            )
        )

    @property
    def failed_tasks(self):
        """
        Failed tasks are those with a Status value greater than or equal to
        Status.cancelled
        """
        return list(
            filter(
                lambda task: (enums.Status[task.status] >= enums.Status.cancelled),
                self.tasks,
            )
        )

    @property
    def successful_tasks(self):
        """
        Successful tasks are those that have completed and not failed.
        """
        completed = self.completed_tasks
        failed = self.failed_tasks
        return list(
            filter(
                lambda task: (task in completed and task not in failed),
                self.tasks,
            )
        )

    @property
    def ready_tasks(self):
        """
        Ready tasks are those that are not started, and for which all ancestors are
        successful.
        """
        started = self.started_tasks
        successful = self.successful_tasks
        return list(
            filter(
                lambda task: (
                    task not in started
                    and all(
                        map(
                            lambda task: task in successful,
                            self.tasks_ancestors[task.name],
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

    id: UUID = Field(default=None)
    qname: str
    retries: int = Field(default=1)
    status: str = Field(default=enums.Status.queued.name)
    queued: datetime = Field(default=None)
    scheduled: datetime = Field(default=None)
    workflow: Workflow = Field(default_factory=dict)
    data: dict = Field(default_factory=dict)

    @validator('status')
    def validate_job_status(cls, val, values, **kwargs):
        if val not in enums.Status.__members__.keys():
            raise ValueError(
                f'value must be one of {list(enums.Status.__members__.keys())}'
            )
        return val

    @validator('workflow', pre=True)
    def convert_job_workflow(cls, val, values, **kwargs):
        if isinstance(val, str):
            val = json.loads(val)
        return val

    @validator('data', pre=True)
    def convert_job_data(cls, val, values, **kwargs):
        if isinstance(val, str):
            val = json.loads(val)
        return val


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
    initialized: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))
    logged: datetime = Field(default=None)
    workflow: Workflow
    data: dict

    @validator('status')
    def validate_joblog_status(cls, val, values, **kwargs):
        if val not in enums.Status.__members__.keys():
            raise ValueError(
                f'value must be one of {list(enums.Status.__members__.keys())}'
            )
        return val

    @validator('workflow', pre=True)
    def convert_joblog_workflow(cls, val, values, **kwargs):
        if isinstance(val, str):
            val = json.loads(val)
        return val

    @validator('data', pre=True)
    def convert_joblog_data(cls, val, values, **kwargs):
        if isinstance(val, str):
            val = json.loads(val)
        return val
