from postq import enums, executors, models


def mock_executor(address, jobdir, task_def):
    """
    An executor that simulates running a task without actually calling a subprocess.

    Set the task status to the value of the task.params['status'] and send the task
    message back to address.
    """
    task = models.Task(**task_def)
    task.status = task.params.get('status') or str(enums.Status.completed)
    executors.send_data(address, task.dict())
