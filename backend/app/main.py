import os
import time
from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from . import store
from .db import describe_schema
from .report import to_markdown
from .auth import AuthError  # For backward compatibility, kept for rollback
from .routers import auth_router
from .middleware import CSRFMiddleware
from .dependencies.auth import get_current_user_id

app = FastAPI(title="QueryPilot AI")
app.add_middleware(CORSMiddleware, allow_origins=os.getenv("ALLOWED_ORIGINS", "*").split(","),
                   allow_methods=["*"], allow_headers=["*"])
# Add CSRF middleware
app.add_middleware(CSRFMiddleware)

# Include authentication router
app.include_router(auth_router)


class Ask(BaseModel):
    question: str = Field(min_length=3, max_length=1000)


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/schema")
def schema():
    return {"schema": describe_schema()}


@app.post("/api/ask")
def ask(body: Ask, user_id: str = Depends(get_current_user_id)):
    """Ask a question - requires authentication."""
    from .agent import investigate  # lazy: other endpoints work without an API key
    start = time.monotonic()
    try:
        result = investigate(body.question)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Investigation failed: {e}")
    result["duration_ms"] = int((time.monotonic() - start) * 1000)
    result["id"] = store.save(result["question"], result["answer"], result["queries"], result["duration_ms"], result.get("findings", []), user_id=user_id)
    return result


@app.get("/api/investigations")
def list_investigations(user_id: str = Depends(get_current_user_id)):
    """List user's investigations - requires authentication."""
    return store.list_recent(user_id=user_id)


@app.get("/api/investigations/{inv_id}")
def get_investigation(inv_id: str, user_id: str = Depends(get_current_user_id)):
    """Get specific investigation - requires authentication and ownership."""
    inv = store.get(inv_id, user_id=user_id)
    if not inv:
        # Don't reveal whether investigation exists
        raise HTTPException(status_code=404, detail="Investigation not found")
    return inv


@app.get("/api/investigations/{inv_id}/export")
def export_investigation(inv_id: str, user_id: str = Depends(get_current_user_id)):
    """Export investigation as markdown - requires authentication and ownership."""
    inv = store.get(inv_id, user_id=user_id)
    if not inv:
        raise HTTPException(status_code=404, detail="Investigation not found")
    return PlainTextResponse(to_markdown(inv), media_type="text/markdown",
                             headers={"Content-Disposition": f'attachment; filename="investigation-{inv_id}.md"'})


@app.get("/api/me")
def me(user_id: str = Depends(get_current_user_id)):
    """Get current user info - for frontend to get user ID."""
    return {"user_id": user_id, "message": "Authenticated"}
