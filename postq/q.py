import asyncio
import json
import logging
import subprocess
from threading import Thread

import zmq
import zmq.asyncio
from databases import Database

from postq import tables
from postq.enums import Status
from postq.models import Job, JobLog, Task

log = logging.getLogger(__name__)


async def manage_queue(dsn: str, qname: str, listeners: int = 1, max_wait: int = 30):
    """
    start listeners that will listen to the queue.

    * dsn = database url
    * qname = name of the queue to listen to
    * listeners = number of listeners to launch in coroutines
    * max_wait = the maximum sleep time for a given listener
    """
    database = Database(dsn, min_size=listeners, max_size=listeners)
    await database.connect()
    await asyncio.gather(
        *[
            listen_queue(database, qname, number, max_wait)
            for number in range(listeners)
        ]
    )


async def listen_queue(database: Database, qname: str, number: int, max_wait: int = 30):
    """
    poll the 'qname' queue for jobs, processing each one in order. when there are no
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
                joblog = await process_job(qname, number, job)
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


async def process_job(qname: str, number: int, job: Job) -> JobLog:
    """
    process the given Job and return a JobLog with the results. 

    Each job workflow consists of a DAG (directed acyclic graph) of tasks. While there
    are incomplete tasks, launch any ready tasks in threads and wait for a task to
    complete. When a task completes, log its results, then re-check for ready tasks
    (those whose ancestors have completed successfully) and launch them. When all tasks
    have completed, return the results.
    """
    # bind PULL socket (task sink)
    address = f"ipc://postq-{qname}-{number:02d}.ipc"
    context = zmq.asyncio.Context.instance()
    task_sink = context.socket(zmq.PULL)
    task_sink.bind(address)

    joblog = JobLog(**job.dict())

    # loop until all the tasks are finished (either completed or failed)
    while min([Status[task.status] for task in job.workflow.tasks]) < Status.completed:
        # do all the ready tasks (ancestors are completed and not failed)
        for task in job.workflow.ready_tasks:
            log.debug('[%s] %s ready = %r', address, task.name, task)

            # start an executor thread for each task. give it the address to send a
            # message. (send the task definition as a copy via `.dict()`)
            thread = Thread(target=subprocess_executor, args=(address, task.dict()))
            thread.start()
            task.status = Status.processing.name

        # wait for any task to complete. (all tasks send a message to the task_sink. the
        # task_result is the task definition itself as a `.dict()`).
        result = await task_sink.recv()
        result_task = Task(**json.loads(result))
        log.debug("[%s] %s result = %r", address, task.name, result_task)

        # when a task completes, update the task definition with its status and errors.
        task = job.workflow.tasks_dict[result_task.name]
        task.update(**result_task.dict())

        # if it failed, mark all descendants as cancelled
        if Status[task.status] >= Status.cancelled:
            for descendant_task in job.workflow.tasks_descendants[task.name]:
                log.debug("[%s] %s cancel = %r", address, task.name, descendant_task)
                descendant_task.status = Status.cancelled.name

    # all the tasks have now either succeeded, failed, or been cancelled. The Job status
    # is the maximum (worst) status of any task.
    job.status = max([Status[task.status] for task in job.workflow.tasks]).name
    joblog.update(**job.dict())
    return joblog


def subprocess_executor(address, task_def):
    task = Task(**task_def)

    # execute the task and gather the results and any errors into the task
    task.status = task.params.get('status') or 'completed'
    cmd = task.params.get('command')
    if cmd:
        process = subprocess.run(cmd, shell=True, capture_output=True)
        task.results = process.stdout
        task.errors = process.stderr
        if process.returncode > 0:
            task.status = Status.error.name
        elif task.errors:
            task.status = Status.warning.name
        else:
            task.status = Status.success.name
    else:
        task.status = Status.completed.name

    # connect to PUSH socket (NOT asyncio, this isn't a coroutine)
    context = zmq.Context.instance()
    task_sender = context.socket(zmq.PUSH)
    task_sender.connect(address)

    # send a message to the task_sink with the task results
    task_sender.send(task.json().encode())
