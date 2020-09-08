import logging
import subprocess
from typing import Dict

import zmq

from postq.enums import Status
from postq.models import Task

log = logging.getLogger(__name__)


def shell_executor(address: str, jobdir: str, task_def: Dict) -> None:
    """
    Execute the given Task definition in its own subprocess shell, and send a message to
    the given address with the results when the subprocess has completed.

    Task.params:

    * command = a string representing the shell command to run.
    """
    try:
        task = Task(**task_def)

        # execute the task and gather the results and any errors into the task
        cmd = task.params.get('command')
        if cmd:
            process = subprocess.run(cmd, cwd=jobdir, shell=True, capture_output=True)
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

    except Exception as exc:
        task.status = Status.error.name
        task.errors = f"{type(exc).__name__}: {str(exc)}"

    send_task(address, task)


def docker_executor(address: str, jobdir: str, task_def: Dict) -> None:
    """
    Execute the given Task definition in a docker container subprocess, and send a
    message to the given address with the results when the subprocess has completed.

    Task.params:

    * command = a string representing the command to run.
    * image = the image to use to run the command. The image can be locally cached, or
      it will be downloaded from Docker Hub or the given registry.
    * env = environment variables that will be passed into the docker container.
    """
    try:
        task = Task(**task_def)

        image = task.params['image']
        command = task.params['command']
        env = ' '.join(
            [f'-e {key}="{val}"' for key, val in task.params.get('env') or {}]
        )
        vol = f'-v {jobdir}:/jobdir'
        cwd = '-w /jobdir'

        cmd = f'docker run -t {env} {vol} {cwd} {image} {command}'
        log.debug(cmd)

        # execute the task and gather the results and any errors into the task
        process = subprocess.run(cmd, shell=True, capture_output=True)
        task.results = process.stdout
        task.errors = process.stderr
        if process.returncode > 0:
            task.status = Status.error.name
        elif task.errors:
            task.status = Status.warning.name
        else:
            task.status = Status.success.name

    except Exception as exc:
        task.status = Status.error.name
        task.errors = f"{type(exc).__name__}: {str(exc)}"

    send_task(address, task)


def send_task(address: str, task: Task):
    """
    Send (PUSH) task to zmq socket address.
    """
    # connect to PUSH socket (NOT zmq.asyncio, since this isn't a coroutine)
    context = zmq.Context.instance()
    task_sender = context.socket(zmq.PUSH)
    task_sender.connect(address)

    # send a message to the task_sink with the task results
    task_sender.send(task.json().encode())
