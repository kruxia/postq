import asyncio
import logging
import os

import click

from postq import q

for logger_name in [
    'databases',
]:
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.INFO)


@click.command()
@click.option('-d', '--dsn', default=os.getenv('POSTQ_DATABASE_DSN'))
@click.option('-q', '--qname', default='')
@click.option('-n', '--listeners', default=1)
@click.option('-l', '--level', default=logging.DEBUG)
@click.option('-w', '--max-wait', default=30)
def main(dsn, qname, listeners, level, max_wait):
    logging.basicConfig(level=level)
    asyncio.run(q.manage_queue(dsn, qname, listeners, max_wait))


if __name__ == '__main__':
    main()
