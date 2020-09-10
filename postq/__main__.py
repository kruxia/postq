import asyncio
import logging
import os

import click

from postq import executors, q

for logger_name in [
    'databases',
]:
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.INFO)

EXECUTORS = {
    'docker': executors.docker_executor,
    'shell': executors.shell_executor,
}
DATABASE_URL = os.getenv('DATABASE_URL')


@click.command()
@click.option('-d', '--database-url', default=DATABASE_URL, help="Database URL")
@click.option('-q', '--qname', default='', help='Name of the queue to listen to')
@click.option('-n', '--listeners', default=1, help='Number of parallel listers')
@click.option('-l', '--level', default=logging.INFO, help='Logging level')
@click.option('-s', '--max-sleep', default=30, help='Maximum seconds to sleep')
@click.option('-e', '--executor', default='shell', help='Executor function')
def main(database_url, qname, listeners, level, max_sleep, executor):
    logging.basicConfig(level=level)
    asyncio.run(
        q.manage_queue(database_url, qname, listeners, max_sleep, EXECUTORS[executor])
    )


if __name__ == '__main__':
    main()
