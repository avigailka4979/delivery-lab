"""delivery-lab: a tiny in-memory deliveries API (FastAPI)."""
import itertools
import threading

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

app = FastAPI()

STATUSES = ["created", "in_transit", "delivered"]
_deliveries = {}
_ids = itertools.count(1)
_lock = threading.Lock()


def error(code, message):
    return JSONResponse(status_code=code, content={"error": message})


async def read_json_object(request: Request):
    """Return (dict, None) or (None, error_response)."""
    raw = await request.body()
    if not raw.strip():
        return None, error(400, "request body is required")
    try:
        data = await request.json()
    except ValueError:
        return None, error(400, "body is not valid JSON")
    if not isinstance(data, dict):
        return None, error(400, "body must be a JSON object")
    return data, None


def find(delivery_id: str):
    try:
        return _deliveries.get(int(delivery_id))
    except ValueError:
        return None


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/deliveries")
async def create_delivery(request: Request):
    data, err = await read_json_object(request)
    if err:
        return err
    recipient = data.get("recipient")
    address = data.get("address")
    if not isinstance(recipient, str) or not recipient.strip():
        return error(400, "recipient must be a non-empty string")
    if not isinstance(address, str) or not address.strip():
        return error(400, "address must be a non-empty string")
    with _lock:
        delivery = {
            "id": next(_ids),
            "recipient": recipient,
            "address": address,
            "status": "created",
        }
        _deliveries[delivery["id"]] = delivery
    return JSONResponse(status_code=201, content=delivery)


@app.get("/deliveries")
def list_deliveries(status: str | None = None):
    if status is not None and status not in STATUSES:
        return error(400, f"unknown status: {status}")
    with _lock:
        items = list(_deliveries.values())
    if status is not None:
        items = [d for d in items if d["status"] == status]
    return items


@app.get("/deliveries/{delivery_id}")
def get_delivery(delivery_id: str):
    delivery = find(delivery_id)
    if delivery is None:
        return error(404, "delivery not found")
    return delivery


@app.patch("/deliveries/{delivery_id}/status")
async def update_status(delivery_id: str, request: Request):
    delivery = find(delivery_id)
    if delivery is None:
        return error(404, "delivery not found")
    data, err = await read_json_object(request)
    if err:
        return err
    new_status = data.get("status")
    if new_status not in STATUSES:
        return error(400, f"unknown status: {new_status}")
    current = STATUSES.index(delivery["status"])
    if STATUSES.index(new_status) != current + 1:
        return error(
            409,
            f"cannot go from {delivery['status']} to {new_status}",
        )
    with _lock:
        delivery["status"] = new_status
    return delivery


@app.delete("/deliveries/{delivery_id}")
def delete_delivery(delivery_id: str):
    delivery = find(delivery_id)
    if delivery is None:
        return error(404, "delivery not found")
    if delivery["status"] != "created":
        return error(409, f"cannot delete a delivery that is {delivery['status']}")
    with _lock:
        del _deliveries[delivery["id"]]
    return Response(status_code=204)
