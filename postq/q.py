import asyncio
import json
import logging
import tempfile
from pathlib import Path
from threading import Thread
from typing import Callable

import zmq
import zmq.asyncio
from databases import Database

from postq import executors, tables
from postq.enums import Status
from postq.models import Job, JobLog, Task

log = logging.getLogger(__name__)


async def manage_queue(
    dsn: str,
    qname: str,
    listeners: int = 1,
    max_wait: int = 30,
    executor: Callable[[str, dict, str], None] = None,
):
    """
    Start listeners that will listen to the queue.

    * dsn = database url
    * qname = name of the queue to listen to
    * listeners = number of listeners to launch in coroutines
    * max_wait = the maximum sleep time for a given listener

    Each listener runs in a separate coroutine. A listener only runs one job at a time.
    Listeners and job processors are I/O-bound, but the parallelized task processors
    that they run are CPU-bound. Run as many listeners as you like, but realize that
    they will each poll the database separately, and they will each launch one job at a
    time with parallelized tasks.
    """
    database = Database(dsn, min_size=listeners, max_size=listeners)
    await database.connect()
    await asyncio.gather(
        *[
            listen_queue(database, qname, number, max_wait, executor)
            for number in range(listeners)
        ]
    )


async def listen_queue(
    database: Database,
    qname: str,
    number: int,
    max_wait: int = 30,
    executor: Callable[[str, dict, str], None] = None,
):
    """
    Poll the 'qname' queue for jobs, processing each one in order. When there are no
    jobs, wait for an increasing number of seconds up to max_wait.
    """
    wait_time = 1
    while True:
        # in a single database transaction...
        async with database.transaction():
            # poll the Q for available jobs
            if record := await database.fetch_one(
                tables.Job.get(), values={'qname': qname}
            ):
                job = Job(**record)
                log.debug("[%s %02d] job = %r", qname, number, job)
                joblog = await process_job(qname, number, job, executor)
                await database.execute(
                    query=tables.JobLog.insert(), values=joblog.dict()
                )
                await database.execute(
                    'delete from postq.job where id=:id', values={'id': job.id}
                )
                # reset the wait time since there are active jobs
                wait_time = 1

        log.debug("[%s %02d] sleep = %d sec...", qname, number, wait_time)
        await asyncio.sleep(wait_time)
        wait_time = min(round(wait_time * 1.618), max_wait)


async def process_job(
    qname: str,
    number: int,
    job: Job,
    executor: Callable[[str, dict, str], None] = None,
) -> JobLog:
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
        "[%s %02d] processing Job: %s [queued=%s]", qname, number, job.id, job.queued
    )

    if executor is None:
        executor = executors.shell_executor

    # bind PULL socket (task sink)
    address = f"ipc://postq-{qname}-{number:02d}.ipc"
    context = zmq.asyncio.Context.instance()
    task_sink = context.socket(zmq.PULL)
    task_sink.bind(address)

    joblog = JobLog(**job.dict())

    with tempfile.TemporaryDirectory() as jobdir:
        # The jobdir directory will be available to all tasks in the job workflow, to
        # use for temporary files in the processing of tasks.

        # Write the Job definition to a file named "job.json" in the jobdir.
        with open(Path(jobdir) / 'job.json', 'wb') as f:
            f.write(job.json().encode())

        # loop until all the tasks are finished (either completed or failed)
        while (
            min([Status[task.status] for task in job.workflow.tasks]) < Status.completed
        ):
            # do all the ready tasks (ancestors are completed and not failed)
            for task in job.workflow.ready_tasks:
                log.debug('[%s] %s ready = %r', address, task.name, task)

                # start an executor thread for each task. give it the address to send a
                # message, the location of the job dir, and the task definition. (send
                # the task definition as a copy via `.dict()`)
                thread = Thread(target=executor, args=(address, jobdir, task.dict()))
                thread.start()
                task.status = Status.processing.name

            # wait for any task to complete. (all tasks send a message to the task_sink.
            # the task_result is the task definition itself as a `.dict()`).
            result = await task_sink.recv()
            result_task = Task(**json.loads(result))
            log.debug("[%s] %s result = %r", address, task.name, result_task)

            # when a task completes, update the task definition with its status and errors.
            task = job.workflow.tasks_dict[result_task.name]
            task.update(**result_task.dict())

            # if it failed, mark all descendants as cancelled
            if Status[task.status] >= Status.cancelled:
                for descendant_task in job.workflow.tasks_descendants[task.name]:
                    log.debug(
                        "[%s] %s cancel = %r", address, task.name, descendant_task
                    )
                    descendant_task.status = Status.cancelled.name

    # all the tasks have now either succeeded, failed, or been cancelled. The Job status
    # is the maximum (worst) status of any task.
    job.status = max([Status[task.status] for task in job.workflow.tasks]).name
    joblog.update(**job.dict())

    log.info(
        "[%s %02d] completed Job: %s [status=%s]", qname, number, job.id, job.status
    )

    return joblog
