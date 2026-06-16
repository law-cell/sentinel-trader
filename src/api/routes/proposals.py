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

Approve/reject logic lives in src/orders/service.py so the Telegram
callback handler can share the same code path.
"""

from fastapi import APIRouter, HTTPException, Request

from src.orders.models import Proposal
from src.orders.service import approve_proposal as svc_approve, reject_proposal as svc_reject
from src.orders.tracker import get_tracker

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
    ib = getattr(request.app.state, "ib", None)
    result = await svc_approve(proposal_id, ib)
    if not result.ok:
        status_code = 404 if result.proposal is None else 400
        raise HTTPException(status_code=status_code, detail=result.reason)
    return result.proposal


@router.post("/{proposal_id}/reject", response_model=Proposal)
async def reject_proposal(proposal_id: str):
    result = await svc_reject(proposal_id)
    if not result.ok:
        status_code = 404 if result.proposal is None else 400
        raise HTTPException(status_code=status_code, detail=result.reason)
    return result.proposal
