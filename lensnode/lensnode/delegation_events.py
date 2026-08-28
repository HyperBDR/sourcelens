"""In-process delivery of control-plane delegated Run updates."""

import threading


class DelegationEventRegistry:
    """Cache child-Run updates and wake synchronous runtime workers."""

    def __init__(self):
        self._condition = threading.Condition()
        self._events = {}

    def publish(self, payload):
        """Store one update and wake workers waiting for the child Run."""

        run_uuid = str((payload or {}).get("run_uuid") or "")
        if not run_uuid:
            return
        with self._condition:
            self._events[run_uuid] = dict(payload)
            self._condition.notify_all()

    def wait(self, run_uuid, timeout_s):
        """Return the latest update, waiting up to the supplied timeout."""

        key = str(run_uuid or "")
        with self._condition:
            if key not in self._events:
                self._condition.wait_for(
                    lambda: key in self._events,
                    timeout=max(float(timeout_s), 0),
                )
            return self._events.pop(key, None)


delegation_events = DelegationEventRegistry()
