"""
Constants for task execution tracking.
"""


class TaskStatus:
    """Task execution status constants."""

    PENDING = "PENDING"
    STARTED = "STARTED"
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    RETRY = "RETRY"
    REVOKED = "REVOKED"

    @classmethod
    def get_all_statuses(cls):
        return [
            cls.PENDING,
            cls.STARTED,
            cls.SUCCESS,
            cls.FAILURE,
            cls.RETRY,
            cls.REVOKED,
        ]

    @classmethod
    def get_completed_statuses(cls):
        return [cls.SUCCESS, cls.FAILURE, cls.REVOKED]

    @classmethod
    def get_running_statuses(cls):
        return [cls.STARTED, cls.RETRY]
