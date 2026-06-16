"""
Proposals API Routes
=====================
Read + approve/reject endpoints for order proposals created by rules with
action.type "propose_stock_order" / "propose_option_order".

Endpoints:
    GET  /api/proposals/pending          — list PENDING proposals
    GET  /api/proposals/history          — all proposals, newest first
    GET  /api/proposals/{id}             — a single proposal
    POST /api/proposals/{id}/approve     — approve + (stub) execute
    POST /api/proposals/{id}/reject      — reject

Approve runs validate_for_execution (state may have drifted since the
proposal was created) before "executing" via StubProposalDispatcher.
"""

from fastapi import APIRouter, HTTPException, Request

from src.orders.dispatcher import get_dispatcher
from src.orders.models import Proposal
from src.orders.tracker import get_tracker
from src.orders.validation import validate_for_execution

router = APIRouter(prefix="/api/proposals", tags=["proposals"])


# NOTE: /pending and /history must be declared before /{proposal_id} to avoid
# being captured as a path parameter match.

@router.get("/pending", response_model=list[Proposal])
async def list_pending():
    return get_tracker().list_pending()


@router.get("/history", response_model=list[Proposal])
async def list_history(limit: int = 20):
    return get_tracker().list_history(limit)


@router.get("/{proposal_id}", response_model=Proposal)
async def get_proposal(proposal_id: str):
    proposal = get_tracker().get(proposal_id)
    if proposal is None:
        raise HTTPException(status_code=404, detail=f"Proposal '{proposal_id}' not found")
    return proposal


@router.post("/{proposal_id}/approve", response_model=Proposal)
async def approve_proposal(request: Request, proposal_id: str):
    tracker = get_tracker()
    proposal = tracker.get(proposal_id)
    if proposal is None:
        raise HTTPException(status_code=404, detail=f"Proposal '{proposal_id}' not found")

    ok, reason = tracker.approve(proposal_id)
    if not ok:
        raise HTTPException(status_code=400, detail=reason)

    ib = getattr(request.app.state, "ib", None)
    result = validate_for_execution(proposal, tracker, ib)
    if not result.ok:
        tracker.mark_failed(proposal_id, result.reason)
        raise HTTPException(status_code=400, detail=result.reason)

    ib_order_id = await get_dispatcher().dispatch_execution(proposal)
    tracker.mark_executed(proposal_id, ib_order_id)

    return tracker.get(proposal_id)


@router.post("/{proposal_id}/reject", response_model=Proposal)
async def reject_proposal(proposal_id: str):
    tracker = get_tracker()
    if tracker.get(proposal_id) is None:
        raise HTTPException(status_code=404, detail=f"Proposal '{proposal_id}' not found")

    ok, reason = tracker.reject(proposal_id)
    if not ok:
        raise HTTPException(status_code=400, detail=reason)

    return tracker.get(proposal_id)
