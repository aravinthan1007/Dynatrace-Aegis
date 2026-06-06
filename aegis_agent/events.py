"""In-memory event bus for the dashboard and agent workflow."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import UTC
from datetime import datetime
from queue import Empty
from queue import Queue
import threading
from typing import Any


@dataclass(slots=True)
class DashboardSubscriber:
    queue: Queue


class DashboardEventBus:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._history: deque[dict[str, Any]] = deque(maxlen=400)
        self._burn_samples: deque[dict[str, Any]] = deque(maxlen=240)
        self._subscribers: list[DashboardSubscriber] = []
        self._approval_event = threading.Event()
        self._approval_pending = False
        self._last_plan: dict[str, Any] | None = None

    def publish(self, event: dict[str, Any]) -> dict[str, Any]:
        payload = dict(event)
        payload.setdefault("ts", datetime.now(UTC).isoformat())
        payload.setdefault("type", "message")

        with self._lock:
            self._history.append(payload)
            if payload["type"] == "burn":
                self._burn_samples.append(payload)
            if payload["type"] == "approval_requested":
                self._approval_pending = True
                self._approval_event.clear()
                self._last_plan = payload
            if payload["type"] == "approval_granted":
                self._approval_pending = False
            subscribers = list(self._subscribers)

        for subscriber in subscribers:
            subscriber.queue.put(payload)
        return payload

    def subscribe(self) -> tuple[DashboardSubscriber, list[dict[str, Any]]]:
        subscriber = DashboardSubscriber(queue=Queue())
        with self._lock:
            self._subscribers.append(subscriber)
            history = list(self._history)
        return subscriber, history

    def unsubscribe(self, subscriber: DashboardSubscriber) -> None:
        with self._lock:
            if subscriber in self._subscribers:
                self._subscribers.remove(subscriber)

    def next_event(self, subscriber: DashboardSubscriber, timeout: float = 1.0) -> dict[str, Any] | None:
        try:
            return subscriber.queue.get(timeout=timeout)
        except Empty:
            return None

    def burn_samples(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._burn_samples)

    def approval_state(self) -> dict[str, Any]:
        with self._lock:
            return {
                "pending": self._approval_pending,
                "last_plan": self._last_plan,
            }

    def request_approval(self, plan: dict[str, Any]) -> None:
        self.publish({"type": "approval_requested", **plan})

    def approve(self, approved_by: str = "dashboard") -> None:
        self._approval_event.set()
        self.publish({"type": "approval_granted", "approved_by": approved_by})

    def wait_for_approval(self, timeout_seconds: int) -> bool:
        granted = self._approval_event.wait(timeout_seconds)
        if granted:
            self._approval_event.clear()
        return granted


event_bus = DashboardEventBus()
