import subprocess

import requests
import xml.etree.ElementTree as ET
from django.conf import settings
from requests.auth import HTTPBasicAuth
import logging, json as _json

logger = logging.getLogger(__name__)


def check_key_format(key_path):
    """
    Check the format of a private key and return its type.
    Returns: ('pkcs1'|'pkcs8'|'unknown', error_message if any)
    """
    try:
        with open(key_path, 'r') as f:
            content = f.read()

        if "-----BEGIN RSA PRIVATE KEY-----" in content:
            return 'pkcs1', None
        elif "-----BEGIN PRIVATE KEY-----" in content:
            return 'pkcs8', None
        elif "-----BEGIN ENCRYPTED PRIVATE KEY-----" in content:
            return 'encrypted', "Encrypted keys are not supported"
        else:
            return 'unknown', "Unknown key format"

    except Exception as e:
        return 'unknown', str(e)


def convert_key_to_pkcs8(input_path, output_path):
    """
    Convert a PKCS#1 key to PKCS#8 format
    """
    try:
        # First verify it's a valid PKCS#1 key
        result = subprocess.run([
            'openssl', 'rsa',
            '-in', input_path,
            '-check'
        ], capture_output=True, text=True)

        if result.returncode != 0:
            return False, f"Invalid RSA key: {result.stderr}"

        # Convert to PKCS#8
        result = subprocess.run([
            'openssl', 'pkcs8',
            '-topk8',
            '-in', input_path,
            '-out', output_path,
            '-nocrypt'
        ], capture_output=True, text=True)

        if result.returncode == 0:
            return True, "Successfully converted key to PKCS#8"
        else:
            return False, f"Conversion failed: {result.stderr}"

    except Exception as e:
        return False, f"Error during conversion: {str(e)}"


def handle_econt_response(response):
    print("=== Econt raw response ===")
    print(response.status_code)
    print(response.content.decode(errors="replace"))

    if response.status_code == 200 and response.content.strip():
        tree = ET.fromstring(response.content)
        shipment_num = tree.findtext(".//shipment_num")
        pdf_url = tree.findtext(".//pdf_url")
        return shipment_num, pdf_url
    else:
        raise Exception(f"Празен или грешен отговор от Econt:\n{response.status_code}\n{response.text}")


def build_econt_label_payload(order):
    """
    Build the JSON payload for Econt's LabelService.createLabel.json.
    - COD (= Наложен платеж) uses order.total in BGN.
    - For COD, receiver is the payer (shipping + COD collected at door).
    """

    # normalize payment method
    pm = (str(order.payment_method) or "").strip().lower()
    COD_VALUES = {
        "cash", "cod", "cash_on_delivery", "cash on delivery",
        "наложен", "наложен платеж", "наложен-платеж",
    }
    is_cod = pm in COD_VALUES

    # Make sure total is up-to-date
    total_bgn = float(order.get_total())  # Decimal -> float for JSON

    # Sender data from settings
    sender_name = getattr(settings, "ECONT_SENDER_NAME", "Сакарела")
    sender_phone = getattr(settings, "ECONT_SENDER_PHONE", "+359878630943")
    sender_city_name = getattr(settings, "ECONT_SENDER_CITY", "Ямбол")
    sender_city_postcode = getattr(settings, "ECONT_SENDER_POSTCODE", "8600")
    sender_street = getattr(settings, "ECONT_SENDER_STREET", "")
    sender_street_no = getattr(settings, "ECONT_SENDER_STREET_NO", "")

    # Base label (we override payer for COD below)
    label = {
        "shipmentType": order.econt_shipment_type(),
        "service": "toDoor",
        "packCount": 1,
        "weight": order.econt_shipment_weight_kg(),
        "shipmentDescription": f"Поръчка №{order.pk}",
        "payer": "SENDER",  # default – will be changed to RECEIVER for COD
        "label": {"format": "10x9"},

        # --- sender ---
        "senderClient": {
            "name": sender_name,
            "phones": [sender_phone],
        },
        "senderAgent": {
            "name": sender_name,
            "phones": [sender_phone],
        },
        "senderAddress": {
            "city": {
                "country": {"code3": "BGR"},
                "name": sender_city_name,
                "postCode": sender_city_postcode,
            },
            "street": f"{sender_street} {sender_street_no}".strip(),
        },

        # --- receiver from order ---
        "receiverClient": {
            "name": f"{order.full_name or ''} {order.last_name or ''}".strip(),
            "phones": [order.phone] if order.phone else [],
        },
        "receiverAddress": {
            "city": {
                "country": {"code3": "BGR"},
                "name": order.city or "",
                "postCode": order.post_code or "",
            },
            "street": order.address1 or "",
        },
    }

    # --- services / COD + declared value ---
    services = {
        "declaredValueAmount": total_bgn,
        "declaredValueCurrency": "BGN",
    }

    if is_cod:
        # COD = full order total
        services["cdAmount"] = total_bgn
        services["cdCurrency"] = "BGN"

        # Receiver is the payer – both for courier service & COD fees
        label["payer"] = "RECEIVER"

        # This pair tells Econt who *pays* the amount at the door
        label["paymentReceiverMethod"] = "CASH"
        label["paymentReceiverAmount"] = total_bgn

    label["services"] = services

    payload = {
        "mode": "create",
        "label": label,
    }
    return payload


econtlog = logging.getLogger("econt")


def ensure_econt_label_json(order):
    if getattr(order, "econt_shipment_num", None):
        econtlog.info("Order %s already has shipment_num=%s", order.pk, order.econt_shipment_num)
        return order.econt_shipment_num, order.label_url, None

    url = getattr(settings, "ECONT_CREATE_LABEL_URL",
                  "https://ee.econt.com/services/Shipments/LabelService.createLabel.json")
    payload = build_econt_label_payload(order)
    econtlog.info("POST %s | order=%s payload=%s", url, order.pk, _json.dumps(payload, ensure_ascii=False))

    resp = requests.post(
        url,
        json=payload,
        auth=HTTPBasicAuth(settings.ECONT_USER, settings.ECONT_PASS),
        headers={"Content-Type": "application/json; charset=utf-8"},
        timeout=30,
    )

    econtlog.info("RESP %s | status=%s text=%s", url, resp.status_code, (resp.text or "")[:4000])

    resp.raise_for_status()  # ← add this
    data = resp.json()

    labels = data.get("labels") or data.get("label") or []
    if isinstance(labels, dict):
        labels = [labels]
    if not labels:
        raise Exception(f"Econt did not return labels: {data}")

    first = labels[0]
    shipment_num = first.get("shipmentNumber") or first.get("shipmentNum") or ""
    label_url = first.get("labelURL") or first.get("pdfURL") or ""

    if not shipment_num:
        raise Exception(f"Econt returned no shipment number: {data}")

    order.econt_shipment_num = shipment_num
    order.label_url = label_url
    order.save(update_fields=["econt_shipment_num", "label_url"])

    econtlog.info("Order %s -> shipment=%s label=%s", order.pk, shipment_num, label_url)
    return shipment_num, label_url, data
