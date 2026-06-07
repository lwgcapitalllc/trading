"""Queue router — enqueue/list/delete jobs."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from services import lab_db, queue_runner

router = APIRouter(prefix="/queue", tags=["queue"])


class QueueEnqueueOptimizationRequest(BaseModel):
    optimization_id: str


class QueueEnqueueStressTestRequest(BaseModel):
    stress_test_id: str
    include_walk_forward: bool = False
    include_sensitivity: bool = False


@router.get("")
def list_queue():
    return lab_db.queue_list()


@router.post("/optimization", status_code=202)
def enqueue_optimization(body: QueueEnqueueOptimizationRequest):
    opt = lab_db.get_optimization(body.optimization_id)
    if not opt:
        raise HTTPException(404, "Optimization not found")
    qid = queue_runner.enqueue_optimization(body.optimization_id)
    return {"queue_id": qid, "status": "queued"}


@router.post("/stress-test", status_code=202)
def enqueue_stress_test(body: QueueEnqueueStressTestRequest):
    st = lab_db.get_stress_test(body.stress_test_id)
    if not st:
        raise HTTPException(404, "Stress test not found")
    qid = queue_runner.enqueue_stress_test(
        body.stress_test_id,
        include_walk_forward=body.include_walk_forward,
        include_sensitivity=body.include_sensitivity,
    )
    return {"queue_id": qid, "status": "queued"}


@router.delete("/{queue_id}", status_code=204)
def delete_queue_item(queue_id: str):
    deleted = lab_db.queue_delete(queue_id)
    if not deleted:
        raise HTTPException(404, "Item not found or already running/done")
