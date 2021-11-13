import json
from datetime import datetime, timezone
from typing import Any, Dict, List
from uuid import UUID

import networkx as nx
from pydantic import BaseModel, Field, validator
from sqly import Dialect, Query

from postq.enums import Status


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
    * command = the command that this task executes
    * image = the image that this task uses (Docker executor)
    * params = other parameters, such as executor-specific parameters
    """

    # fields
    name: str
    command: str = Field(default_factory=str)
    image: str = Field(default=None)
    depends: List[str] = Field(default_factory=list)
    params: dict = Field(default_factory=dict)
    status: str = Field(default=str(Status.initialized))
    results: str = Field(default=None)
    errors: str = Field(default=None)


class Job(Model):
    """
    A single job in the Job queue and then in the log.

    * id - Unique identifier for this job.
    * qname - Name of the queue that this job is will be in. Different postq workers
      listen to different queues.
    * status - the current status of the job, one of the values in postq.Status.
    * queued - timestamp when the job was queued.
    * scheduled - timestamp when the job is scheduled (= queued by default).
    * initialed - timestamp when the job was initialized.
    * logged - timestamp when the job was logged.
    * tasks - define the job's workflow. key = name, value = Task. Each task defines its
      own dependencies, command, and image. The resulting workflow must form a directed
      acyclic graph -- i.e., there cannot be a dependency loop.
      * depends - the list of names of the other tasks that this task depends on.
      * command - the command that the task runs in the image container.
      * image - {docker, kubernetes} the image that is used to run the task.
    * graph - (generated from tasks) the DAG (directed acyclic graph) of tasks (a
      networkx.DiGraph), which is validated as acyclic.
    * data - extra data that is needed by the job or its tasks to complete the workflow.
    """

    # fields
    id: UUID = Field(default=None)
    qname: str = Field(default='')
    status: str = Field(default=str(Status.queued))
    queued: datetime = Field(default=None)
    scheduled: datetime = Field(default=None)
    initialized: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))
    logged: datetime = Field(default=None)
    tasks: Dict[str, Task] = Field(default_factory=dict)
    graph: Any = Field(default_factory=nx.DiGraph)
    data: dict = Field(default_factory=dict)

    @validator('status')
    def validate_job_status(cls, value, values, **kwargs):
        if value not in Status.__members__.keys():
            raise ValueError(f'value must be one of {list(Status.__members__.keys())}')
        return value

    @validator('tasks', pre=True)
    def convert_job_tasks(cls, value):
        # convert a string to a dict
        if isinstance(value, str):
            value = json.loads(value)

        # convert values that are dicts to Task instances
        return {
            name: (
                Task(name=name, **{k: v for k, v in val.items() if k != 'name'})
                if isinstance(val, dict)
                else val
            )
            for name, val in value.items()
        }

    @validator('data', pre=True)
    def convert_job_data(cls, value, values, **kwargs):
        # convert a string to a dict
        if isinstance(value, str):
            value = json.loads(value)
        return value

    @validator('tasks')
    def validate_tasks(cls, value, values, **kwargs):
        """
        Ensure that all Task.depends are defined as Tasks.
        """
        errors = []
        task_names = list(value.keys())
        for task_name, task in value.items():
            for depend_name in task.depends:
                if depend_name not in task_names:
                    errors.append(
                        f"Task '{task_name}' depends on undefined Task '{depend_name}'."
                    )
        if errors:
            raise ValueError(' '.join(errors))
        return value

    @validator('graph', always=True)
    def validate_graph(cls, value, values, **kwargs):
        """
        Build the job.graph from the job.tasks, and ensure that the graph is
        acyclic (a directed acyclic graph).
        """
        graph = nx.DiGraph()
        for task_name, task in (values.get('tasks') or {}).items():
            graph.add_node(task_name)  # make sure every task is added
            for depend_name in task.depends:
                graph.add_edge(depend_name, task_name)
        if not nx.is_directed_acyclic_graph(graph):
            raise ValueError(
                'The tasks graph must be acyclic, but it currently includes cycles.'
            )
        # the transitive reduction ensures the shortest version of the workflow.
        return nx.transitive_reduction(graph)

    # ancestors and descendants of a given task

    @property
    def task_ancestors(self):
        """
        graph ancestors, with the keys in lexicographical topological sort order.
        """
        return {
            task_name: [
                self.tasks[name] for name in nx.ancestors(self.graph, task_name)
            ]
            for task_name in nx.lexicographical_topological_sort(self.graph)
        }

    @property
    def task_descendants(self):
        return {
            task_name: [
                self.tasks[name] for name in nx.descendants(self.graph, task_name)
            ]
            for task_name in nx.lexicographical_topological_sort(self.graph)
        }

    # lists of tasks with various statuses

    @property
    def started_tasks(self):
        """
        Tasks with a Status value greater than or equal to Status.processing
        """
        return list(
            filter(
                lambda task: (Status[task.status] >= Status.processing),
                self.tasks.values(),
            )
        )

    @property
    def completed_tasks(self):
        """
        Tasks with a Status value greater than or equal to Status.completed
        """
        return list(
            filter(
                lambda task: (Status[task.status] >= Status.completed),
                self.tasks.values(),
            )
        )

    @property
    def failed_tasks(self):
        """
        Tasks with a Status value greater than or equal to Status.cancelled
        """
        return list(
            filter(
                lambda task: (Status[task.status] >= Status.cancelled),
                self.tasks.values(),
            )
        )

    @property
    def successful_tasks(self):
        """
        Tasks that have completed and not failed.
        """
        completed = self.completed_tasks
        failed = self.failed_tasks
        return list(
            filter(
                lambda task: (task in completed and task not in failed),
                self.tasks.values(),
            )
        )

    @property
    def ready_tasks(self):
        """
        Tasks that are not started, and for which all ancestors are successful.
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
                            self.task_ancestors[task.name],
                        )
                    )
                ),
                self.tasks.values(),
            )
        )

    def update(self, **kwargs):
        super().update(**kwargs)
        for attr in [self.tasks, self.data]:
            if isinstance(attr, str):
                attr = json.loads(attr)

    def dict(self, *args, **kwargs):
        # don't include graph in output, because it's not serializable, and it's
        # generated automatically from tasks.
        exclude = {'graph'} | (
            (kwargs.pop('exclude') or set()) if 'exclude' in kwargs else set()
        )
        return super().dict(*args, exclude=exclude, **kwargs)
        # # filter 'name' out of tasks
        # data['tasks'] = {
        #     name: {key: val for key, val in task.items() if key not in ['name']}
        #     for name, task in data['tasks'].items()
        # }
        # return data

    # field converters


class Queue(Model):
    qname: str
    dialect: Dialect = Dialect.ASYNCPG

    def put(self, job, table='postq.job'):
        job_data = job.dict(exclude_none=True)
        return self.dialect.render(
            f"""
            INSERT INTO {table}
                ({Query.fields(job_data)})
            VALUES ({Query.params(job_data)})
            RETURNING *
            """,
            job_data,
        )

    def put_log(self, job):
        return self.put(job, table='postq.job_log')

    def get(self):
        return self.dialect.render(
            """
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
            """,
            {'qname': self.qname},
        )

    def delete(self, job_id):
        return self.dialect.render(
            """
            DELETE FROM postq.job WHERE id=:job_id
            """,
            {'job_id': str(job_id)},
        )

    def get_log(self, **filters):
        return self.dialect.render(
            "select * from postq.job_log"
            + (f"where {Query.filters(filters)}" if filters else ''),
            filters,
        )

    def query(self, *args, **kwargs):
        return self.dialect.render(*args, **kwargs)
