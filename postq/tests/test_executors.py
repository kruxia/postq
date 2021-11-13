import os
from pathlib import Path

import pytest

from postq import executors, q


@pytest.mark.asyncio
async def test_shell_executor():
    """
    live-test the shell_executor
    """
    socket_file = Path(os.getenv('TMPDIR', '')) / '.postq-test.ipc'
    address = f'ipc://{socket_file}'
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
            'task': {'name': 'a', 'command': 'echo hi'},
            'result': {'status': 'success', 'results': 'hi\n'},
        },
        # Task with cmd that errors
        {
            'task': {'name': 'a', 'command': 'exit 1'},
            'result': {'status': 'error'},
        },
        # Task with cmd that warns
        {
            'task': {'name': 'a', 'command': '>&2 echo "error"'},
            'result': {'status': 'warning'},
        },
    ]

    for item in data:
        print('item =', item)
        executor(address, jobdir, {**item['task']})
        result = await task_sink.recv_json()
        print('result =', result)
        for key in item['result']:
            assert result[key] == item['result'][key]

    task_sink.close()
    os.remove(address.split('//')[-1])


@pytest.mark.asyncio
async def test_docker_executor():
    """
    Live-test the docker_executor.

    (NOTE: Running commands in a docker container takes time as compared with the shell.
    So the number of docker commands we test is limited.)

    (NOTE: This test isn't parametrized because of the overhead of the socket setup.)
    """
    socket_file = Path(os.getenv('TMPDIR', '')) / '.postq-test.ipc'
    address = f'ipc://{socket_file}'
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
            'task': {'name': 'a', 'command': 'ls'},
            'result': {'status': 'error'},
        },
        # Task with cmd that works (stdout, no stderr, no exit failure code)
        {
            'task': {
                'name': 'a',
                'command': 'echo hi',
                'params': {'image': 'debian:bullseye-slim'},
            },
            'result': {'status': 'success', 'results': 'hi\r\n'},
        },
        # Task with cmd that errors (exit 1 creates an error condition)
        {
            'task': {
                'name': 'a',
                'command': 'exit 1',
                'params': {'image': 'debian:bullseye-slim'},
            },
            'result': {'status': 'error'},
        },
        # Task with cmd that warns (stderr creates a warning condition)
        {
            'task': {
                'name': 'a',
                'command': '>&2 echo "error"',
                'params': {'image': 'debian:bullseye-slim'},
            },
            'result': {'status': 'warning'},
        },
    ]

    for item in data:
        print('item =', item)
        executor(address, jobdir, {**item['task']})
        result = await task_sink.recv_json()
        print('result =', result)
        for key in item['result']:
            assert result[key] == item['result'][key]

    task_sink.close()
    os.remove(address.split('//')[-1])
