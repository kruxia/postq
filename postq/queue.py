import asyncio
import json
import logging
import subprocess
from threading import Thread

import zmq
import zmq.asyncio
from databases import Database

from . import tables
from .enums import Status
from .models import Job, JobLog, Task

log = logging.getLogger(__name__)
MAX_WAIT_TIME = 30


async def listen_queue(database: Database, qname: str, number: int):
    wait_time = 1
    while True:
        # in a single database transaction...
        async with database.transaction():
            # poll the Q for available jobs
            if record := await database.fetch_one(
                query=tables.Job.get(), values={'qname': qname}
            ):
                job = Job(**record)
                joblog = await process_job(qname, number, job)
                await database.execute(
                    query=tables.JobLog.insert(), values=joblog.dict()
                )
                await database.execute(query=tables.Job.delete(), values=job.dict())
                wait_time = 1

        await asyncio.sleep(wait_time)
        wait_time = min(round(wait_time * 1.618), MAX_WAIT_TIME)


async def process_job(qname: str, number: int, job: Job) -> JobLog:
    # bind PULL socket (task sink)
    address = f"ipc://postq-{qname}-{number:02d}.ipc"
    context = zmq.asyncio.Context.instance()
    task_sink = context.socket(zmq.PULL)
    task_sink.bind(address)

    # loop until all the tasks are finished (either completed or failed)
    while min(*[Status[task.status] for task in job.workflow.tasks]) < Status.completed:
        # do all the ready tasks (ancestors are completed and not failed)
        for task in job.workflow.ready_tasks:
            log.debug('[%s] %s ready = %r', address, task.name, task)
            # start an executor process for each task. give it the address to send a
            # message. (send the task definition as a copy via `.dict()`)
            process = Thread(target=subprocess_executor, args=(address, task.dict()))
            process.start()
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
    job.status = list(Status.__members__.values())[
        max([Status[task.status] for task in job.workflow.tasks])
    ]
    return JobLog(**job.dict())


def subprocess_executor(address, task_def):
    task = Task(**task_def)

    # execute the task and gather the results and any errors into the task
    task.status = task.params.get('status') or 'completed'
    if cmd:
        process = subprocess.run(cmd, shell=True, capture_output=True)
        task.results = process.stdout
        task.errors = process.stderr
        if process.returncode > 0:
            task.status = Status.error.name
        elif tasks.errors:
            task.status = Status.warning.name
        else:
            task.status = Status.success.name
    else:
        task.status = Status.completed.name

    # connect to PUSH socket (NOT asyncio, this isn't a coroutine)
    context = zmq.Context.instance()
    task_sender = context.socket(zmq.PUSH)
    task_sender.connect(address)

    # send a message to the task_sink with the results
    task_sender.send(task.json().encode())
