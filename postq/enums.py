from enum import IntEnum


class Status(IntEnum):
    """
    Enumerations of Statuses for Tasks, Jobs, etc. Values are comparable as integers
    (due to inheriting from IntEnum), which makes querying status much more
    straightforward. For example:

    * incomplete == status < completed
    * failure == status > warning
    * successful == completed <= status and status <= warning
    * overall status == max(iterable of sub-statuses)
    """

    # incomplete statuses
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

    def __str__(self):
        """
        The string representation of a Status is its name, for human readability.
        """
        return self.name
