# PostQ = Cloud-Native Job Queue and DAG Workflow System

PostQ is a job queue system with 

* workflows that are directed acyclic graphs, with tasks that depend on other tasks
* parallel task execution
* shared files among tasks
* a PostgreSQL database backend
* choice of {shell, docker, [coming soon: kubernetes]} task executors
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

* **The Docker [and coming soon Kubernetes] Executor Runs each Task in a Container Using any Image.** 

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
    
    [**TODO**: _Move examples out of the features summary_]

    Here is an example in Python using [Databases](https://encode.io/databases), [SQL Alchemy Core](https://docs.sqlalchemy.org/en/13/core/), and data models written in [Pydantic](https://pydantic-docs.helpmanual.io/):

    ```python
    # (Using the ipython shell, which allows async/await without an explicit event loop.)
    import os
    from databases import Database
    from postq import models, tables
    
    database = Database(os.getenv('DATABASE_URL'))
    await database.connect()
    job = models.Job(
        workflow={
            'tasks': [
                {
                    'name': 'a', 
                    'params': {'image': 'debian:buster-slim', 'command': 'ls -laFh'}
                }
            ]
        }
    )
    record = await database.fetch_one(
        tables.Job.insert().returning(*tables.Job.columns), values=job.dict()
    )
    
    # Then, after a few seconds...

    joblog = models.JobLog(
        **await database.fetch_one(
            tables.JobLog.select().where(
                tables.JobLog.columns.id==record['id']
            ).limit(1)
        )
    )

    print(joblog.workflow.tasks[0].results)

    # total 4.0K
    # drwxr-xr-x 2 root root   64 Sep 11 04:11 ./
    # drwxr-xr-x 1 root root 4.0K Sep 11 04:11 ../
    ```
    Now you have a job log entry with the output of your command in the task results. :tada:

    Similar results can be achieved with SQL directly, or with any other interface. Here's the same example run in the `psql` terminal (`docker-compose exec postq bash` to shell into the postq container, then `psql $DATABASE_URL` to shell into the database from there):

    ```sql
    postq=# insert into postq.job (qname, status, workflow) values ('', 'queued', '{"tasks": [{"name": "a", "params": {"image": "debian:buster-slim", "command": "ls -laFh"}}]}') returning id;
    -[ RECORD 1 ]----------------------------
    id | 17d0a67c-98fb-4f84-913e-2f0532bc069f

    INSERT 0 1
    postq=# select * from postq.job_log where id = '17d0a67c-98fb-4f84-913e-2f0532bc069f';
    -[ RECORD 1 ]---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
    id          | 17d0a67c-98fb-4f84-913e-2f0532bc069f
    qname       | 
    retries     | 0
    queued      | 2020-09-11 04:48:53.897556+00
    scheduled   | 2020-09-11 04:48:53.897556+00
    initialized | 2020-09-11 04:48:54.40734+00
    logged      | 2020-09-11 04:48:54.400779+00
    status      | success
    workflow    | {"tasks": [{"name": "a", "errors": "", "params": {"image": "debian:buster-slim", "command": "ls -laFh"}, "status": "success", "depends": [], "results": "total 4.0K\r\ndrwxr-xr-x 2 root root   64 Sep 11 04:48 ./\r\ndrwxr-xr-x 1 root root 4.0K Sep 11 04:48 ../\r\n"}]}
    data        | {}
    ```

<!-- * [TODO] **Can use a message broker as the Job Queue.** Applications that need higher performance and throughput than PostgreSQL can provide must be able to shift up to something more performant. For example, RabbitMQ is a very high-performance message broker written in Erlang.

* [TODO] **Can run (persistent) Task workers.** Some Tasks or Task environments (images) are anticipated as being needed continually. In such job environments, the Task workers can be made persistent services that listen to the Job queue for their own Jobs. (In essence, this allows a Task to be a complete sub-workflow being handled by its own Workflow Job queue workers, in which the Tasks are enabled to run inside the Job worker container as subprocesses.) -->

