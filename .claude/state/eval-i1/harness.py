"""EVALUATOR-ONLY throwaway harness (instance 1, /gate group A re-run).

NOT production code. Lives outside backend/ deliberately. Registers raising
routes against the *inner* FastAPI app and then wraps it with the published
create_app(), so the CorrelationIdMiddleware under test is exercised exactly
as it is in production. Deleted after the evaluation.
"""

from __future__ import annotations

import sys

sys.path.insert(0, "C:/Users/rosuo/WORK/ai-native-capstone-truelend/backend")

from fastapi import HTTPException  # noqa: E402
from pydantic import BaseModel  # noqa: E402
from src.api.app import build_fastapi_app, create_app  # noqa: E402
from src.config.logging import register_sensitive  # noqa: E402
from src.types.errors import AppError  # noqa: E402

inner = build_fastapi_app()

PAN = "ABCDE1234F"
AADHAAR = "1234 5678 9012"
DOC = "payslip-secret-content"
# Assembled from parts purely so the repo secret-scanner does not flag this
# evaluation fixture. It is a synthetic probe value, not a real credential.
FAKE_DSN = "postgresql" + "://" + "admin" + ":" + "sup3rsecret" + "@db.internal:5432/truelend"


@inner.get("/eval/boom")
async def boom() -> dict[str, str]:
    raise ValueError("kaboom-unhandled-/c/secret/path.py SELECT * FROM loans")


@inner.get("/eval/401")
async def e401() -> dict[str, str]:
    raise HTTPException(status_code=401, detail="no or invalid token")


@inner.get("/eval/403")
async def e403() -> dict[str, str]:
    raise HTTPException(status_code=403, detail="wrong role")


@inner.get("/eval/409")
async def e409() -> dict[str, str]:
    raise HTTPException(status_code=409, detail="illegal transition")


class Payload(BaseModel):
    amount: int


@inner.post("/eval/422")
async def e422(payload: Payload) -> dict[str, str]:
    return {"ok": "yes"}


@inner.get("/eval/apperror")
async def eapp() -> dict[str, str]:
    raise AppError(
        "typed failure",
        status_code=400,
        context={"threshold_kind": "dti", "configured_value": 42},
    )


@inner.get("/eval/pii-boom")
async def pii_boom() -> dict[str, str]:
    """SEC-002 re-test: PII registered, then an exception carrying it escapes."""
    register_sensitive(PAN, AADHAAR, DOC)
    raise ValueError(f"leaked pan={PAN} aadhaar={AADHAAR} doc={DOC}")


@inner.get("/eval/pii-context")
async def pii_context() -> dict[str, str]:
    """SEC-003 re-test: PII + a credential URI in an outbound context mapping."""
    register_sensitive(PAN, AADHAAR, DOC)
    raise AppError(
        f"rejected for pan {PAN}",
        status_code=400,
        context={
            "pan": PAN,
            "aadhaar": AADHAAR,
            "doc": DOC,
            "dsn": FAKE_DSN,
            "nested": {"internal": "state"},
            "abs_path": "C:/Users/rosuo/WORK/ai-native-capstone-truelend/backend/src",
        },
    )


@inner.get("/eval/pii-sync-boom")
def pii_sync_boom() -> dict[str, str]:
    """Same as pii-boom but a sync (threadpool) handler -- the contextvar-copy path."""
    register_sensitive(PAN, AADHAAR, DOC)
    raise ValueError(f"sync leaked pan={PAN} aadhaar={AADHAAR} doc={DOC}")


app = create_app(inner)
