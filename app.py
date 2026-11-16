"""delivery-lab: a small REST API for deliveries (FastAPI, in-memory storage)."""
import threading
from typing import Optional

from fastapi import Body, FastAPI, HTTPException, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

app = FastAPI(title="delivery-lab")

STATUSES = ["created", "in_transit", "delivered"]
MAX_TEXT_LENGTH = 200

deliveries: dict[int, dict] = {}
next_id = 1
# Plain `def` endpoints run in a thread pool, so two POSTs can run at the same
# time. The lock makes "read next_id, store, increment" one step, so two
# deliveries never get the same id.
lock = threading.Lock()


# ---------- errors: always {"error": "..."} ----------

@app.exception_handler(StarletteHTTPException)
def http_error(request, exc):
    return JSONResponse({"error": str(exc.detail)}, status_code=exc.status_code)


@app.exception_handler(RequestValidationError)
def validation_error(request, exc):
    # Missing body, invalid JSON, a body that is not an object, or a non-numeric id.
    errors = exc.errors()
    where = errors[0].get("loc", ["body"])[0] if errors else "body"
    if where == "path":
        message = "delivery id must be an integer"
    else:
        message = "request body must be a JSON object"
    return JSONResponse({"error": message}, status_code=400)


# ---------- helpers ----------

def get_or_404(delivery_id: int) -> dict:
    delivery = deliveries.get(delivery_id)
    if delivery is None:
        raise HTTPException(404, f"delivery {delivery_id} not found")
    return delivery


def required_text(data: dict, field: str) -> str:
    value = data.get(field)
    if not isinstance(value, str) or not value.strip():
        raise HTTPException(400, f"'{field}' must be a non-empty string")
    if len(value) > MAX_TEXT_LENGTH:
        raise HTTPException(400, f"'{field}' must be at most {MAX_TEXT_LENGTH} characters")
    return value


# ---------- routes ----------

@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/deliveries", status_code=201)
def create_delivery(data: dict = Body(...)):
    global next_id
    recipient = required_text(data, "recipient")
    address = required_text(data, "address")
    with lock:
        delivery = {"id": next_id, "recipient": recipient, "address": address, "status": "created"}
        deliveries[next_id] = delivery
        next_id += 1
    return delivery


@app.get("/deliveries")
def list_deliveries(status: Optional[str] = None):
    if status is None:
        return list(deliveries.values())
    if status not in STATUSES:
        raise HTTPException(400, f"unknown status '{status}', use one of {STATUSES}")
    return [d for d in deliveries.values() if d["status"] == status]


@app.get("/deliveries/{delivery_id}")
def get_delivery(delivery_id: int):
    return get_or_404(delivery_id)


@app.patch("/deliveries/{delivery_id}/status")
def update_status(delivery_id: int, data: dict = Body(...)):
    delivery = get_or_404(delivery_id)
    new_status = data.get("status")
    if new_status not in STATUSES:
        raise HTTPException(400, f"unknown status, use one of {STATUSES}")
    current = STATUSES.index(delivery["status"])
    if STATUSES.index(new_status) != current + 1:
        raise HTTPException(409, f"cannot change status from '{delivery['status']}' to '{new_status}'")
    delivery["status"] = new_status
    return delivery


@app.delete("/deliveries/{delivery_id}")
def delete_delivery(delivery_id: int):
    delivery = get_or_404(delivery_id)
    if delivery["status"] != "created":
        raise HTTPException(409, f"only deliveries in status 'created' can be deleted (this one is '{delivery['status']}')")
    with lock:
        deliveries.pop(delivery_id, None)
    return Response(status_code=204)
