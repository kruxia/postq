from enum import Enum


class Status(Enum):
    # status values are such that the status of a set of tasks is the max status of all
    # the individual tasks. So if one task had an error, the whole has an error status.
    initialized = 0
    queued = 1
    processing = 2
    # completed statuses
    completed = 3
    success = 4
    notice = 5
    warning = 6
    # failure statuses
    cancelled = 7
    failure = 8
    error = 9
