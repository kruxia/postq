import asyncio
import json
import logging
import os
import tempfile
from copy import deepcopy
from pathlib import Path
from threading import Thread
from typing import Callable

import asyncpg
import sqly
import zmq
import zmq.asyncio

from postq.enums import Status
from postq.models import Job, Queue, Task

log = logging.getLogger(__name__)


async def manage_queue(
    database_url: str,
    qname: str,
    listeners: int = None,
    max_sleep: int = 8,
    executor: Callable[[str, dict, str], None] = None,
):
    """
    Start listeners that will listen to the queue.

    * database_url = database connection url
    * qname = name of the queue to listen to
    * listeners = number of listeners to launch in coroutines (default: num CPUs)
    * max_sleep = the maximum sleep time for a given listener

    Each listener runs in a separate coroutine. A listener only runs one job at a time.
    Listeners and job processors are I/O-bound, but the parallelized task processors
    that they run are CPU-bound. Run as many listeners as you like, but realize that
    they will each poll the database separately, and they will each launch one job at a
    time with parallelized tasks.
    """
    listeners = listeners or os.cpu_count()
    database = await asyncpg.create_pool(
        dsn=database_url,
        min_size=listeners,
        max_size=listeners,
        max_inactive_connection_lifetime=10,
    )
    queue = Queue(
        qname=qname, dialect=sqly.Database.connection_string_dialect(database_url)
    )
    await asyncio.gather(
        *[
            listen_queue(database, queue, listener, max_sleep, executor)
            for listener in range(listeners)
        ]
    )


async def listen_queue(
    database: asyncpg.Pool,
    queue: Queue,
    listener: int,
    max_sleep: int = 30,
    executor: Callable[[str, dict, str], None] = None,
):
    """
    Poll the queue for jobs, processing each one in order. When there are no
    jobs, wait for an increasing number of seconds up to max_sleep.
    """
    wait_time = 1
    while True:
        result = await transact_one_job(database, queue, listener, executor)
        wait_time = 1 if result else min(round(wait_time * 1.618), max_sleep)
        log.debug("[%s %02d] sleep = %d sec...", queue, listener, wait_time)
        await asyncio.sleep(wait_time)


async def transact_one_job(database, queue, listener, executor, connection=None):
    if not connection:
        connection = await database.acquire()
    # in a single database transaction...
    async with connection.transaction():
        # poll the Q for available jobs
        if record := await connection.fetchrow(*queue.get()):
            job = Job(**record)
            log.debug("[%s %02d] job = %r", queue.qname, listener, job)
            joblog = await process_job(queue.qname, listener, job, executor)
            await connection.execute(*queue.put_log(joblog))
            await connection.execute(*queue.delete(job.id))
            return True


async def process_job(
    qname: str,
    listener: int,
    job: Job,
    executor: Callable[[str, dict, str], None],
) -> Job:
    """
    Process the given Job and return a JobLog with the results.

    Each job workflow consists of a DAG (directed acyclic graph) of tasks -- this is
    validated when the Job is loaded.

    Algorithm: While there are incomplete tasks, launch any ready tasks in threads and
    wait for a task to complete. When a task completes, log its results, then re-check
    for ready tasks (those whose ancestors have completed successfully) and launch them.
    When all tasks have completed, return the results.

    Each Task executor is run in its own OS thread, and the Task itself is executed as a
    separate subprocess managed by that thread.

    The algorithm allows as many tasks to be run in parallel as the workflow DAG itself
    will allow. Therefore, a given workflow can use as many system CPUs as its maximum
    parallelism will allow.

    The Job definition is stored in a temporary folder, which is also available for any
    job files that are created by tasks in the Job workflow. The temporary folder is
    automatically destroyed when the job is completed.
    """
    log.info(
        "[%s %02d] processing Job: %s [queued=%s]", qname, listener, job.id, job.queued
    )
    job = deepcopy(job)

    # bind PULL socket (task sink)
    socket_file = Path(os.getenv('TMPDIR', '')) / f'.postq-{qname}-{listener:02d}.ipc'
    address = f"ipc://{socket_file}"
    task_sink = bind_pull_socket(address)

    with tempfile.TemporaryDirectory() as jobdir:
        # The jobdir directory will be available to all tasks in the job workflow, to
        # use for temporary files in the processing of tasks.

        # Write the Job definition to a file named "job.json" in the jobdir.
        with open(Path(jobdir) / 'job.json', 'wb') as f:
            f.write(job.json().encode())

        # loop until all the tasks are finished (either completed or failed)
        while (
            min([Status[task.status] for task in job.tasks.values()]) < Status.completed
        ):
            # do all the ready tasks (ancestors are completed and not failed)
            for task in job.ready_tasks:
                log.debug('[%s] %s ready = %r', address, task.name, task)

                # start an executor thread for each task. give it the address to send a
                # message, the location of the job dir, and the task definition. (send
                # the task definition as a copy via `.dict()`)
                thread = Thread(target=executor, args=(address, jobdir, task.dict()))
                thread.start()
                task.status = str(Status.processing)

            # wait for any task to complete. (all tasks send a message to the task_sink.
            # the task_result is the task definition itself as a `.dict()`).
            result = await task_sink.recv()
            result_task = Task(**json.loads(result))
            log.debug("[%s] %s result = %r", address, task.name, result_task)

            # when a task completes, update the task definition with its status and
            # errors.
            task = job.tasks[result_task.name]
            task.update(**result_task.dict())

            # if it failed, mark all descendants as cancelled
            if Status[task.status] >= Status.cancelled:
                for descendant_task in job.task_descendants[task.name]:
                    log.debug(
                        "[%s] %s cancel = %r", address, task.name, descendant_task
                    )
                    descendant_task.status = str(Status.cancelled)

    # all the tasks have now either succeeded, failed, or been cancelled. The Job status
    # is the maximum (worst) status of any task.
    job.status = str(max([Status[task.status] for task in job.tasks.values()]))

    log.info(
        "[%s %02d] completed Job: %s [status=%s]", qname, listener, job.id, job.status
    )
    return job


def bind_pull_socket(address: str) -> zmq.Socket:
    context = zmq.asyncio.Context.instance()
    socket = context.socket(zmq.PULL)
    socket.bind(address)
    return socket
