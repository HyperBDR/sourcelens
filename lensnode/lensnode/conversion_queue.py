from dataclasses import dataclass


@dataclass
class ConversionJob:
    """One file conversion job."""

    index: int
    total: int
    item: object
    path: object


class ConversionQueue:
    """Base conversion queue executor."""

    name = "base"

    def run(self, jobs, handler):
        """Run conversion jobs with a handler callable."""

        raise NotImplementedError


class InlineConversionQueue(ConversionQueue):
    """Synchronous in-process conversion queue."""

    name = "inline"

    def run(self, jobs, handler):
        """Run jobs in order and yield handler results."""

        for job in jobs:
            try:
                result = handler(job)
            except Exception as exc:
                result = exc
            yield job, result


def conversion_queue_from_context(context):
    """Return the conversion queue configured for this context."""

    queue_name = (
        (context.get("conversion") or {}).get("queue")
        or context.get("conversion_queue")
        or "inline"
    )
    if queue_name != "inline":
        return InlineConversionQueue()
    return InlineConversionQueue()
