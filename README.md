# PostQ = Cloud-Native Job Queue and DAG Workflow System

PostQ is a job queue system with 

* workflows that are directed acyclic graphs, with tasks that depend on other tasks
* parallel task execution
* shared files among tasks
* a PostgreSQL database backend
* choice of task executors: {shell, docker, [coming soon: kubernetes]}
* easy on-ramp for developers: `git pull https://github.com/kruxia/postq; cd postq; docker-compose up` and you're running PostQ

## Features 

* **A PostQ Job Workflow is a DAG (Directed Acyclic Graph) of Tasks.** 

    Many existing job queue systems define jobs as single tasks, so it's up to the user to define more complex workflows. But many workflows (like CI/CD pipelines, and data applications) need to be able to define workflows at a higher level as a DAG of tasks, in which a given task might depend on earlier tasks that must first be completed, and which might be run in parallel with other tasks in the workflow.

    PostQ defines Job workflows as a DAG of tasks. For each named task, you list the other tasks that must be completed first, and PostQ will work out (using snazzy graph calculations) the simplest and most direct version of the workflow (i.e., the _transitive reduction_ of the graph). It runs the tasks in the order indicated by the graph of their dependencies, and finishes when all tasks have been either completed or cancelled due to a preceding failure.

* **Workflow Tasks Are Executed in Parallel.**

    When a PostQ Job is started, it begins by launching all the tasks that don't depend on other tasks. Then, as each task finishes, it launches all additional tasks for which the predecessors have been successfully completed. 
    
    At any given time, there might be many tasks in a Job running at the same time on different processors. <!-- (and soon, using Kubernetes, on different machines). --> The more you break down your workflows into tasks that can happen in parallel, the more CPUs your tasks can utilize, and the more quickly your jobs can be completed, limited only by the available resources.

* **Tasks in a Job Workflow Can Share Files.**

    For workflows that process large amounts of data that is stored in files, it's important to be able to share these files among all the tasks in a workflow. PostQ creates shared temporary file storage for each job, and each task is run with that directory as the current working directory. 
    
    So, for example, you can start your workflow with a task that pulls files from permanent storage, then other tasks can process the data in those files, create other files, etc. Then, at the end of the work, the files that need to be saved as artifacts of the job can be pushed to permanent storage. 

* **A PostgreSQL Database Is the (Default) Job Queue.** 

    PostgreSQL provides persistence and ACID transaction guarantees. It is the simplest way to ensure that a job is not lost, but is processed exactly once. PostgreSQL is also already running in many web and microservice application clusters, so building on Postgres enables developers to easily add a Job Queue to their application without substantially increasing the necessary complexity of their application. PostgreSQL combines excellent speed with fantastic reliability, durability, and transactional guarantees. 

* **The Docker Executor Runs each Task in a Container Using any Image.** 

    Many existing task queue systems assume that the programming environment in which the queue worker is written is available for the execution of each task. For example, Celery tasks are written and run in python. 
    
    Instead, PostQ has the ability to run tasks in separate containers. This enables a task to use any software, not just the software that is available in the queue worker system.

    (Author's Note: This was one of the primary motivations for writing PostQ. I am building an application that has workflows with tasks requiring NodeJS, or Java, or Python, or Chromium. It's possible to build an image that includes all of these requirements — and weighs in over a gigabyte! It's much more maintainable to separate the different task programs into different images, with each image including only the software it needs to complete its task.)

* **Easy On-ramp for Developers.**
    ```bash
    git pull https://github.com/kruxia/postq.git
    cd postq
    docker-compose up
    ```
    The default docker-compose.yml cluster definition uses the docker executor (so tasks must define an image) with a maximum queue sleep time of 5 seconds and the default qname=''. Note that the default cluster doesn't expose any ports to the outside world, but you can for example shell into the running cluster (using a second terminal) and start pushing tasks into the queue. Or, the more common case is that your PostgreSQL instance is available inside your application cluster, so you can push jobs into postq directly from your application. 

<!-- * [TODO] **Can use a message broker as the Job Queue.** Applications that need higher performance and throughput than PostgreSQL can provide must be able to shift up to something more performant. For example, RabbitMQ is a very high-performance message broker written in Erlang.

* [TODO] **Can run (persistent) Task workers.** Some Tasks or Task environments (images) are anticipated as being needed continually. In such job environments, the Task workers can be made persistent services that listen to the Job queue for their own Jobs. (In essence, this allows a Task to be a complete sub-workflow being handled by its own Workflow Job queue workers, in which the Tasks are enabled to run inside the Job worker container as subprocesses.) -->

## Usage Examples
    
Here is an example in Python using the running postq container itself. The Python stack is [Databases](https://encode.io/databases), [SQL Alchemy Core](https://docs.sqlalchemy.org/en/13/core/), and data models written in [Pydantic](https://pydantic-docs.helpmanual.io/):

```bash
$ docker-compose exec postq ipython
```

```python
# (Using the ipython shell, which allows async/await without an explicit event loop.)
import os
import time
import asyncpg
from postq import models

queue = models.Queue(qname='playq')
database = await asyncpg.create_pool(dsn=os.getenv('DATABASE_URL'))
connection = await database.acquire()
job = models.Job(
    tasks={'a': {'command': 'echo Hey!', 'params': {'image': 'debian:bullseye-slim'}}}
)
job.update(
    **await database.fetchrow(
        *queue.put(job)
    )
)

# Then, wait a few seconds...
time.sleep(5)

joblog = models.Job(
    **await connection.fetchrow(
        *queue.get_log(id=job.id)
    )
)

print(joblog.tasks['a'].results)  # Hey!
```
Now you have a job log entry with the output of your command in the task results. :tada:
