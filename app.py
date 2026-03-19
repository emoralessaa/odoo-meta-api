import os
import time
import hashlib
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

PIXEL_ID = os.environ.get("META_PIXEL_ID")
ACCESS_TOKEN = os.environ.get("META_ACCESS_TOKEN")
TEST_EVENT_CODE = os.environ.get("META_TEST_EVENT_CODE")
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET")

def sha256_normalized(value):
    if value is None:
        return ""
    text = str(value).strip().lower()
    if not text:
        return ""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def only_digits(value):
    if value is None:
        return ""
    return "".join(ch for ch in str(value) if ch.isdigit())

def build_meta_payload(odoo_data):
    record_id = odoo_data.get("id")
    email = odoo_data.get("email_from")
    phone = only_digits(odoo_data.get("phone"))
    value = odoo_data.get("expected_revenue") or 0

    try:
        value = float(value)
    except:
        value = 0

    user_data = {}
    if email:
        user_data["em"] = [sha256_normalized(email)]
    if phone:
        user_data["ph"] = [sha256_normalized(phone)]

    payload = {
        "data": [
            {
                "event_name": "Lead",
                "event_time": int(time.time()),
                "action_source": "system_generated",
                "event_id": f"lead-{record_id}",
                "user_data": user_data,
                "custom_data": {
                    "currency": "MXN",
                    "value": value
                }
            }
        ]
    }

    if TEST_EVENT_CODE:
        payload["test_event_code"] = TEST_EVENT_CODE

    return payload

def send_to_meta(payload):
    url = f"https://graph.facebook.com/v18.0/{PIXEL_ID}/events"
    response = requests.post(
        url,
        params={"access_token": ACCESS_TOKEN},
        json=payload
    )
    return response.json()

@app.route("/")
def home():
    return {"status": "ok"}

@app.route("/odoo/lead", methods=["POST"])
def odoo_lead():
    secret = request.headers.get("X-Webhook-Secret")

    if secret != WEBHOOK_SECRET:
        return {"error": "unauthorized"}, 401

    data = request.json

    payload = build_meta_payload(data)
    meta_response = send_to_meta(payload)

    return {
        "received": data,
        "sent": payload,
        "meta": meta_response
    }