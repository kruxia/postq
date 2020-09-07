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


@click.command()
@click.option('-d', '--dsn', default=os.getenv('POSTQ_DATABASE_DSN'))
@click.option('-q', '--qname', default='')
@click.option('-n', '--listeners', default=1)
@click.option('-l', '--level', default=logging.INFO)
@click.option('-w', '--max-wait', default=30)
@click.option('-e', '--executor', default='shell')
def main(dsn, qname, listeners, level, max_wait, executor):
    logging.basicConfig(level=level)
    asyncio.run(q.manage_queue(dsn, qname, listeners, max_wait, EXECUTORS[executor]))


if __name__ == '__main__':
    main()
