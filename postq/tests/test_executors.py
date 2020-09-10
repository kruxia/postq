import os

import pytest

from postq import executors, q


@pytest.mark.asyncio
async def test_shell_executor():
    """
    live-test the shell_executor
    """
    address = "ipc://postq-test.ipc"
    task_sink = q.bind_pull_socket(address)
    executor = executors.shell_executor
    jobdir = os.getcwd()
    data = [
        # Empty task -> error
        {'task': {}, 'result': {'status': 'error'}},
        # Task with a name but no command -> error
        {'task': {'name': 'a'}, 'result': {'status': 'error'}},
        # Task with cmd that works
        {
            'task': {'name': 'a', 'params': {'command': 'ls'}},
            'result': {'status': 'success'},
        },
        # Task with cmd that errors
        {
            'task': {'name': 'a', 'params': {'command': 'exit 1'}},
            'result': {'status': 'error'},
        },
        # Task with cmd that warns
        {
            'task': {'name': 'a', 'params': {'command': '>&2 echo "error"'}},
            'result': {'status': 'warning'},
        },
    ]

    for item in data:
        executor(address, jobdir, {**item['task']})
        result = await task_sink.recv_json()
        for key in item['result']:
            assert result[key] == item['result'][key]


@pytest.mark.asyncio
async def test_docker_executor():
    """
    live-test the docker_executor. NOTE: Running commands in a docker container takes
    time as compared with the shell. So we limit the number of docker commands we test.
    """
    address = "ipc://postq-test.ipc"
    task_sink = q.bind_pull_socket(address)
    executor = executors.docker_executor
    jobdir = os.getcwd()
    data = [
        # Empty task -> error
        {'task': {}, 'result': {'status': 'error'}},
        # Task with a name but no command or image -> error
        {'task': {'name': 'a'}, 'result': {'status': 'error'}},
        # Task with a name and command but no image -> error
        {
            'task': {'name': 'a', 'params': {'command': 'ls'}},
            'result': {'status': 'error'},
        },
        # Task with cmd that works
        {
            'task': {
                'name': 'a',
                'params': {'command': 'ls', 'image': 'debian:buster-slim'},
            },
            'result': {'status': 'success'},
        },
        # Task with cmd that errors
        {
            'task': {
                'name': 'a',
                'params': {'command': 'exit 1', 'image': 'debian:buster-slim'},
            },
            'result': {'status': 'error'},
        },
        # Task with cmd that warns
        {
            'task': {
                'name': 'a',
                'params': {
                    'command': '>&2 echo "error"',
                    'image': 'debian:buster-slim',
                },
            },
            'result': {'status': 'warning'},
        },
    ]

    for item in data:
        executor(address, jobdir, {**item['task']})
        result = await task_sink.recv_json()
        for key in item['result']:
            assert result[key] == item['result'][key]
