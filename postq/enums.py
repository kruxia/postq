from enum import Enum


class JobStatus(Enum):
    queued = 0
    processing = 1
    completed = 2
    success = 3
    notice = 4
    warning = 5
    failure = 6
    error = 7
    cancelled = -1
