"""Live job events for the signed-in user, as Server-Sent Events (see app/jobs/events.py)."""

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.jobs.events import event_stream
from app.middleware.auth import get_current_user
from app.models.user import User

router = APIRouter(tags=["events"])

SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "X-Accel-Buffering": "no",
    # GZipMiddleware buffers streamed bodies; declaring an encoding makes it pass events through.
    "Content-Encoding": "identity",
}


def get_event_stream():
    """Tests override this to stream from a fake Redis."""
    return event_stream


@router.get("/events")
async def stream_events(
    current_user: User = Depends(get_current_user),
    stream=Depends(get_event_stream),
):
    """`ready` once subscribed, then `job` for each finished background job; `: ping` every 20s.

    The token is only checked when the stream opens: an open stream outlives a 15-minute access
    token, which is fine because it carries no data the user couldn't fetch, and every reconnect
    authenticates again.
    """
    return StreamingResponse(stream(current_user.id), media_type="text/event-stream", headers=SSE_HEADERS)
