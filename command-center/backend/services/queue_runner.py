"""
Queue runner — processes the job_queue table one item at a time.

Dispatches each job to the correct runner function. Fired as a background
asyncio task on app startup. Runs until the process exits.

Supported job_type values:
  - "optimization"  → optimization_runner.run_optimization(optimization_id)
  - "stress_test"   → stress_tester.run_stress_test_task(stress_test_id, ...)
"""

from __future__ import annotations

import asyncio
import logging
import uuid

from services import lab_db

log = logging.getLogger("queue_runner")

_POLL_SEC = 5  # seconds between queue checks


async def _dispatch(item: dict) -> None:
    jtype   = item["job_type"]
    payload = item["payload"]

    if jtype == "optimization":
        from services import optimization_runner
        await optimization_runner.run_optimization(payload["optimization_id"])

    elif jtype == "stress_test":
        from services import stress_tester
        await stress_tester.run_stress_test_task(
            payload["stress_test_id"],
            include_walk_forward=payload.get("include_walk_forward", False),
            include_sensitivity=payload.get("include_sensitivity", False),
        )

    else:
        raise ValueError(f"Unknown job_type: {jtype!r}")


async def run_queue_loop() -> None:
    """Infinite loop: pop next pending → run → mark done/failed → repeat."""
    log.info("Queue runner started")
    while True:
        await asyncio.sleep(_POLL_SEC)

        if lab_db.queue_has_running():
            continue  # another job is already running (e.g. recovered after restart)

        item = lab_db.queue_next_pending()
        if not item:
            continue

        queue_id = item["queue_id"]
        lab_db.queue_set_running(queue_id)
        log.info("Queue: starting %s job %s", item["job_type"], queue_id)

        try:
            await _dispatch(item)
            lab_db.queue_set_done(queue_id)
            log.info("Queue: finished %s job %s", item["job_type"], queue_id)
        except Exception as exc:
            lab_db.queue_set_failed(queue_id, str(exc))
            log.error("Queue: %s job %s failed: %s", item["job_type"], queue_id, exc)


def enqueue_optimization(optimization_id: str) -> str:
    """Add a native optimization to the queue. Returns the queue_id."""
    qid = uuid.uuid4().hex[:16]
    lab_db.queue_enqueue(qid, "optimization", {"optimization_id": optimization_id})
    return qid


def enqueue_stress_test(
    stress_test_id: str,
    include_walk_forward: bool = False,
    include_sensitivity: bool = False,
) -> str:
    """Add a stress test to the queue. Returns the queue_id."""
    qid = uuid.uuid4().hex[:16]
    lab_db.queue_enqueue(qid, "stress_test", {
        "stress_test_id":     stress_test_id,
        "include_walk_forward": include_walk_forward,
        "include_sensitivity":  include_sensitivity,
    })
    return qid
