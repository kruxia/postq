import logging
import subprocess
import traceback
from functools import partial
from typing import Callable, Dict

import zmq

from postq.enums import Status
from postq.models import Task

log = logging.getLogger(__name__)


def executor(
    runner: Callable[[Task, str], Dict], address: str, jobdir: str, task_def: Dict
) -> None:
    """
    Execute the given Task definition using the given runner, and send a message to
    the given address with the results when the subprocess has completed.
    """
    try:
        task = Task(**task_def)
        assert task.command

        # execute the task and gather the results and any errors into the task
        process = subprocess.run(**runner(task, jobdir))
        task.results = process.stdout.decode()
        task.errors = process.stderr.decode()
        if process.returncode > 0:
            task.status = str(Status.error)
        elif task.errors:
            task.status = str(Status.warning)
        else:
            task.status = str(Status.success)

        send_data(address, task.dict())

    except Exception as exc:
        print(traceback.format_exc())
        task_def.setdefault('name', type(exc).__name__)
        task_def['status'] = 'error'
        task_def['errors'] = f"{type(exc).__name__}: {str(exc)}"
        send_data(address, task_def)


def send_data(address: str, data: dict):
    """
    Send (PUSH) task to zmq socket address.
    """
    # connect to PUSH socket (NOT zmq.asyncio, since this isn't a coroutine)
    context = zmq.Context.instance()
    task_sender = context.socket(zmq.PUSH)
    task_sender.connect(address)

    # send a message to the task_sink with the task results
    task_sender.send_json(data)


def shell_runner(task, jobdir):
    return {
        'args': task.command,
        'cwd': jobdir,
        'shell': True,
        'capture_output': True,
    }


def docker_runner(task, jobdir):
    command = task.command
    image = task.params['image']
    env = ' '.join([f'-e {key}="{val}"' for key, val in task.params.get('env') or {}])
    vol = f'-v {jobdir}:/jobdir'
    cwd = '-w /jobdir'
    cmd = f'docker run -t {env} {vol} {cwd} {image} {command}'

    return {'args': cmd, 'shell': True, 'capture_output': True}


shell_executor = partial(executor, shell_runner)
docker_executor = partial(executor, docker_runner)
