import asyncio
import json
from multiprocessing import Process

import zmq
from databases import Database

from . import tables
from .enums import Status
from .models import Job, JobLog, Task

MAX_WAIT_TIME = 30


async def listen_queue(database: Database, qname: str, number: int):
    wait_time = 1
    while True:
        # in a single database transaction...
        async with database.transaction():
            # poll the Q for available jobs
            if record := await database.fetch_one(
                query=Job.get(qname), values={'qname': qname}
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


async def process_job(qname: str, number: str, job: Job) -> JobLog:
    # bind PULL socket (task sink)
    address = f"ipc://{qname}{number:02d}.ipc"
    context = zmq.asyncio.Context.instance()
    task_sink = context.socket(zmq.PULL)
    task_sink.bind(address)

    # loop until all the tasks are finished (either completed or failed)
    while min(*[Status[task.status] for task in job.workflow]) < Status.completed:
        # do all the ready tasks (ancestors are completed and not failed)
        for task in job.workflow.ready_tasks:
            # start an executor process for each task. give it the address to send a
            # message. (send the task definition as a copy via `.dict()`)
            process = Process(target=task_executor, args=(address, task.dict()))
            process.start()
            task.status = Status.processing.name

        # wait for any task to complete. (all tasks send a message to the task_sink. the
        # task_result is the task definition itself as a `.dict()`).
        result = await task_sink.recv()
        result_task = Task(**json.loads(result))

        # when a task completes, update the task definition with its status and errors.
        task = job.workflow.tasks_dict[task.name]
        task.update(**result_task.dict())

        # if it failed, mark all descendants as cancelled
        if Status[task.status] >= Status.cancelled:
            for descendant_task in job.workflow.tasks_descendants[task.name]:
                descendant_task.status = Status.cancelled

    # all the tasks have now either succeeded, failed, or been cancelled. The Job status
    # is the maximum (worst) status of any task.
    job.status = list(Status.__members__.values())[
        max([Status[task.status] for task in job.workflow.tasks])
    ]
    return JobLog(**job.dict())


def task_executor(address, task_def):
    task = Task(**task_def)

    # execute the task in a subprocess

    # gather the results and any errors into the task

    # connect to PUSH socket (NOT asyncio, this isn't a coroutine)
    context = zmq.Context.instance()
    task_sender = context.socket(zmq.PUSH)
    task_sender.connect(address)

    # send a message to the task_sink with the results
    task_sender.send(task.json().encode())
