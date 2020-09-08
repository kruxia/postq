## postq = cloud-native job queue system

Job queue system with API interface, database backend, and choice of {process, docker, kubernetes} job executors.

For the work I am doing, I need a job queue system with the following features:

* **Uses a PostgreSQL database as the (default) Job Queue.** Postgres provides persistence and ACID transaction guarantees. It is the simplest way to ensure that a job is not lost. It is also already running in most application clusters, so building on Postgres enables developers to easily add a Job Queue to their application without substantially increasing the necessary complexity of their application.

* **Defines Job Workflows as a DAG of Tasks.** Most existing job queue systems (e.g., Celery) define jobs as single tasks, so it's up to the user to define more complex workflows. But many workflows (like CI/CD pipelines and data applications) need to be able to define workflows at a higher level as a DAG of tasks, in which a given task might depend on earlier tasks that must first be completed, and which might be run in parallel with other tasks in the workflow.

* **Runs each Task in a (temporary) container using an image.** Many existing task queue systems assume that the programming environment in which the queue worker is written is available for the execution of each task. For example, Celery tasks are written and run in python. Instead, we need to be able to run tasks that have any environment that can be defined and built in a container image. This enables a task to use any software, not just the software that is available in the queue worker.

* [TODO] **Can use a message broker as the Job Queue.** Applications that need higher performance and throughput than PostgreSQL can provide must be able to shift up to something more performant. For example, RabbitMQ is a very high-performance message broker written in Erlang.

* [TODO] **Can run (persistent) Task workers.** Some Tasks or Task environments (images) are anticipated as being needed continually. In such job environments, the Task workers can be made persistent services that listen to the Job queue for their own Jobs. (In essence, this allows a Task to be a complete sub-workflow being handled by its own Workflow Job queue workers, in which the Tasks are enabled to run inside the Job worker container as subprocesses.)

### Architecture:

* **Workflow** = A (JSON/YAML) list of Task definitions that defines a DAG of Tasks.
* **Tasks** = processes that take input and produce output. 
* **Task definitions** are objects that include:
    * name = the name of the Task, must be unique in this Workflow (raise an error if not unique)
    * depends = a list of Task names that this Task depends on having completed before it begins.
    * params = values that are needed to run the task, such as the image name, any environment variables that must be set in that image, and any volume mounts that must be done.
* **Job Worker** = a persistent process that listens to the Job queue, loads Jobs, and executes their Workflows. The Job Worker only knows about the Workflow and its Tasks -- nothing about the business.
* **Job files** = storage that all Tasks in a Job can share. Possible backends include filesystem/volume, S3/minio, and Azure Blob Storage.
* **Executors** = ways of running ~~Tasks~~Workflows. Each Job worker is defined to run with a particular Executor, based on the environment in which it is running. (Workflows don't know anything about the Executor(s) that will be running them.)
    * **docker** = run the Task via `docker run` (must have a docker daemon running and be able to use it). 
        * input: STDIN, ENV, jobfiles
        * output: STDOUT, STDERR, jobfiles
        * jobfiles: filesystem volume mount
        * status: docker run return code
    * **kube** = spin up a kubernetes Job for the Task (must have access to cluster, kubectl installed).
        * management: create the Job definition, apply it to the cluster, and then periodically query the job status (via `kubectl describe`?) until it has completed
        * input: ConfigMap / Secret, jobfiles
        * output: logs, jobfiles
        * jobfiles: volume mounts
        * status: as given by `kubectl describe`
    * **shell** = e.g., bash script for the Task. 
        * management: launch and await the completion of the process. [NOTE: The process executor is very much like the docker executor defined above, but it doesn't involve spinning up a new docker container.]
        * input: STDIN, ENV, jobfiles
        * output: STDOUT and STDERR, jobfiles
        * jobfiles: filesystem
        * status: process return code
    * [TODO] **api** = send the Task to an API endpoint.
        * input: POST JSON request body
        * output: GET JSON response body
        * jobfiles: PUT request / GET response bodies
            * input jobfiles before the POST JSON
            * output jobfiles after the GET JSON
        * status: with output

### Workflow Execution Algorithm

Given the Workflow DAG for the Job, the general Execution algorithm can be:

1. Load the DAG and calculate the ancestors for each Task
2. For all Tasks that have no incomplete or failed ancestors,
    * Start the Task [async subprocess]
3. As each Task completes,
    * Log the Task as complete with status
    * Recurse to step 2.

* The Manager thread/actor initiates each Task thread/actor.
* Each Task thread/actor runs the Task, waits for the results, then sends a message to the Manager indicating the completion, status, and output of this Task.
* The Manager waits for messages from the Tasks and re-runs the (step 2) launch algorithm after receiving each message.

Implementing this algorithm requires multiprocessing or threading with message passing. Super interesting! (We are using asyncio and threading rather than multiprocessing because the performance is significantly higher, approximately 100x faster, and queue manager and task executors are all I/O-bound rather than CPU-bound. The Tasks, which are run as subprocesses inside the task executor threads, are CPU-bound, but since they aren't in the main queue application process, the queue application itself is I/O bound.)

### Message Passing Multiprocessing with ZeroMQ

(Using ZeroMQ is simpler and more robust than multiprocessing.Queue from the Python standard library.)

* QManager spawns QWorker processes (with some limit based on the number of CPUs available)
* QWorker binds Q socket: `"ipc://[qname][NN].ipc"`
* QWorker waits for an available Job (polling the Job Q)
* QWorker runs Job
    * QWorker spawns available TaskExecutor processes. 
    * QWorker listens for messages on the Q socket.
    * TaskExecutor process launches the task, waits for results, then connects on the Q socket and sends a message to the QWorker, exiting after message is delivered.
    * QWorker receives message, processes it, and spawns next round of available TaskExecutor processes. (Processing the Task message includes updating the Job status and logging any results to storage.)
    * When no Tasks remain (either all are completed, or something that is required has failed), QWorker logs the Job as complete.
* QWorker waits for the next available Job.
