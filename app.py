import os
import time
import hashlib
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

PIXEL_ID = os.environ.get("META_PIXEL_ID", "")
ACCESS_TOKEN = os.environ.get("META_ACCESS_TOKEN", "")
TEST_EVENT_CODE = os.environ.get("META_TEST_EVENT_CODE", "")
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")

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

def map_event_name(odoo_data):
    raw_event = (
        odoo_data.get("meta_event_name")
        or odoo_data.get("event_type")
        or odoo_data.get("stage_name")
        or ""
    ).strip().lower()

    if raw_event:
        mapping = {
            "lead": "Lead",
            "qualified_lead": "QualifiedLead",
            "qualifiedlead": "QualifiedLead",
            "schedule": "Schedule",
            "scheduled": "Schedule",
            "appointment": "Schedule",
            "purchase": "Purchase",
            "sale": "Purchase",
            "won": "Purchase",
            "lost": "Lost"
        }
        return mapping.get(raw_event, "Lead")

    stage_id = odoo_data.get("stage_id")

    try:
        stage_id = int(stage_id)
    except (TypeError, ValueError):
        stage_id = None

    stage_mapping = {
        1: "Lead",
        2: "QualifiedLead",
        4: "Schedule",
        6: "Purchase",
        5: "Lost"
    }

    return stage_mapping.get(stage_id, "Lead")

def build_meta_payload(odoo_data):
    record_id = odoo_data.get("id")
    email = odoo_data.get("email_from") or odoo_data.get("email")
    phone = only_digits(odoo_data.get("phone") or odoo_data.get("mobile"))
    value = odoo_data.get("expected_revenue") or odoo_data.get("amount_total") or 0
    event_name = map_event_name(odoo_data)

    try:
        value = float(value)
    except (TypeError, ValueError):
        value = 0

    user_data = {}
    if email:
        user_data["em"] = [sha256_normalized(email)]
    if phone:
        user_data["ph"] = [sha256_normalized(phone)]

    payload = {
        "data": [
            {
                "event_name": event_name,
                "event_time": int(time.time()),
                "action_source": "system_generated",
                "event_id": f"{event_name.lower()}-{record_id if record_id is not None else int(time.time())}",
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
    if not PIXEL_ID or not ACCESS_TOKEN:
        return {
            "ok": False,
            "error": "Faltan META_PIXEL_ID o META_ACCESS_TOKEN en variables de entorno"
        }

    url = f"https://graph.facebook.com/v25.0/{PIXEL_ID}/events"

    try:
        response = requests.post(
            url,
            params={"access_token": ACCESS_TOKEN},
            json=payload,
            timeout=30
        )

        return {
            "ok": response.ok,
            "status_code": response.status_code,
            "body": response.json() if response.content else {}
        }
    except requests.RequestException as e:
        return {
            "ok": False,
            "error": str(e)
        }
    except ValueError:
        return {
            "ok": False,
            "status_code": response.status_code,
            "body": response.text
        }

@app.route("/", methods=["GET"])
def home():
    return jsonify({"ok": True, "message": "Render funcionando"}), 200

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"ok": True, "service": "odoo-meta-api"}), 200

@app.route("/odoo/lead", methods=["POST"])
def odoo_lead():
    secret = request.args.get("secret", "")

    if secret != WEBHOOK_SECRET:
        return jsonify({
            "ok": False,
            "error": "Unauthorized"
        }), 401

    incoming_data = request.get_json(silent=True)
    if not incoming_data:
        return jsonify({
            "ok": False,
            "error": "JSON inválido o vacío"
        }), 400

    event_name = map_event_name(incoming_data)
    payload = build_meta_payload(incoming_data)
    meta_response = send_to_meta(payload)

    print("\n====== EVENT DEBUG ======")
    print("STAGE ID:", incoming_data.get("stage_id"))
    print("EVENT NAME DETECTADO:", event_name)
    print("ODDO DATA:", incoming_data)
    print("PAYLOAD META:", payload)
    print("META RESPONSE:", meta_response)
    print("========================\n")

    return jsonify({
        "ok": True,
        "event_name": event_name,
        "received_from_odoo": incoming_data,
        "sent_to_meta": payload,
        "meta_response": meta_response
    }), 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)