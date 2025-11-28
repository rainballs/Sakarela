import subprocess
from decimal import Decimal

import time
import requests
import xml.etree.ElementTree as ET
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from requests.auth import HTTPBasicAuth
import logging, json as _json
from datetime import date, timedelta

logger = logging.getLogger(__name__)

econtlog = logging.getLogger("econt")

# --- SIMPLE IN-MEMORY CACHE FOR CITIES (optional but nice) ---
_ECONT_CITIES_CACHE = {
    "timestamp": 0,
    "cities": [],
}

COD_VALUES = {
    "cash", "cod", "cash_on_delivery", "cash on delivery",
    "наложен", "наложен платеж", "наложен-платеж",
}


def econt_shipping_preview_for_cart(*, items, cart_total, city, post_code, payment_method) -> Decimal:
    """
    Preview shipping price for the current cart WITHOUT creating a shipment.

    Uses the same LabelService.createLabel.json endpoint as real labels,
    but with mode="calculate".
    """
    from decimal import Decimal

    # If we don’t have address or cart – nothing to calculate
    if not items or not city or not post_code:
        return Decimal("0.00")

    # 1) Calculate total shipment weight in kg from the cart
    total_weight = Decimal("0.0")
    for row in items:
        qty = Decimal(str(row.get("quantity", 0) or 0))

        w = Decimal("0.0")
        pack = row.get("packaging")
        if pack is not None and getattr(pack, "weight", None) is not None:
            w = Decimal(str(pack.weight))
        elif "weight_kg" in row:
            w = Decimal(str(row["weight_kg"]))
        elif "weight" in row:
            w = Decimal(str(row["weight"]))

        total_weight += w * qty

    # Don’t send zero weight
    if total_weight <= 0:
        total_weight = Decimal("1.0")

    # 2) COD or not?
    pm = (payment_method or "").strip().lower()
    is_cod = pm in COD_VALUES

    # 3) Sender data from settings (same as build_econt_label_payload)
    sender_name = getattr(settings, "ECONT_SENDER_NAME", "Сакарела")
    sender_phone = getattr(settings, "ECONT_SENDER_PHONE", "+359878630943")
    sender_city_name = getattr(settings, "ECONT_SENDER_CITY", "Ямбол")
    sender_city_postcode = getattr(settings, "ECONT_SENDER_POSTCODE", "8600")
    sender_street = getattr(settings, "ECONT_SENDER_STREET", "")
    sender_street_no = getattr(settings, "ECONT_SENDER_STREET_NO", "")

    shipment_type = "cargo" if total_weight > Decimal("50") else "pack"

    # 4) Build the same LABEL structure, but for a cart preview
    label = {
        "shipmentType": shipment_type,
        "service": "toDoor",
        "packCount": 1,
        "weight": float(total_weight),
        "shipmentDescription": "Cart preview",
        "payer": "SENDER",  # <- default, same as build_econt_label_payload
        "label": {"format": "10x9"},
        "holidayDeliveryDay": "workday",

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

        "receiverClient": {},
        "receiverAddress": {
            "city": {
                "country": {"code3": "BGR"},
                "name": city,
                "postCode": post_code,
            },
            "street": "",
        },
    }

    services = {
        "declaredValueAmount": float(cart_total),
        "declaredValueCurrency": "BGN",
    }

    if is_cod:
        # EXACTLY like build_econt_label_payload
        services["cdAmount"] = float(cart_total)
        services["cdCurrency"] = "BGN"

        label["payer"] = "RECEIVER"
        label["paymentReceiverMethod"] = "CASH"
        label["paymentReceiverAmount"] = float(cart_total)

    label["services"] = services

    payload = {
        "mode": "calculate",  # ← THIS is the important part
        "label": label,
    }

    # Use the SAME endpoint as for real labels (demo/prod controlled via settings)
    url = getattr(
        settings,
        "ECONT_CREATE_LABEL_URL",
        "https://ee.econt.com/services/Shipments/LabelService.createLabel.json",
    )

    econtlog.info(
        "ECONT PREVIEW ▶ POST %s | payload=%s",
        url, _json.dumps(payload, ensure_ascii=False)
    )

    try:
        resp = requests.post(
            url,
            json=payload,
            auth=HTTPBasicAuth(settings.ECONT_USER, settings.ECONT_PASS),
            headers={"Content-Type": "application/json; charset=utf-8"},
            timeout=30,
        )

        econtlog.info(
            "ECONT PREVIEW ◀ %s | status=%s text=%s",
            url, resp.status_code, (resp.text or "")[:4000]
        )

        resp.raise_for_status()
        data = resp.json()

        # Response looks like the normal createLabel response, but without real shipment
        label_obj = data.get("label") or data.get("labels") or {}
        if isinstance(label_obj, list) and label_obj:
            label_obj = label_obj[0]

        total_price_obj = label_obj.get("totalPrice") or {}
        amount = None

        if isinstance(total_price_obj, dict):
            amount = total_price_obj.get("amount")
        elif isinstance(total_price_obj, (int, float, str)):
            try:
                amount = float(total_price_obj)
            except (TypeError, ValueError):
                amount = None

        if amount is None:
            raise Exception(f"Econt did not return totalPrice.amount: {data}")

        return Decimal(str(amount)).quantize(Decimal("0.01"))

    except Exception as exc:
        econtlog.error("Econt preview price failed: %s", exc)
        # On any error: don’t break checkout, just show 0.00
        return Decimal("0.00")


def econt_get_cities(country_code: str = "BGR"):
    """
    Load list of cities from Econt NomenclaturesService.getCities.json.

    Returns a list of dicts like:
      {"name": "...", "nameEn": "...", "postCode": "...", ...}

    Results are cached for 6 hours in-process.
    """
    global _ECONT_CITIES_CACHE

    now = time.time()
    # 6h cache
    if _ECONT_CITIES_CACHE["cities"] and (now - _ECONT_CITIES_CACHE["timestamp"] < 6 * 3600):
        return _ECONT_CITIES_CACHE["cities"]

    url = getattr(
        settings,
        "ECONT_CITIES_URL",
        "https://ee.econt.com/services/Nomenclatures/NomenclaturesService.getCities.json",
    )

    payload = {"countryCode": country_code}

    econtlog.info("ECONT CITIES ▶ POST %s | payload=%s", url, payload)

    resp = requests.post(
        url,
        json=payload,
        auth=HTTPBasicAuth(settings.ECONT_USER, settings.ECONT_PASS),
        headers={"Content-Type": "application/json; charset=utf-8"},
        timeout=30,
    )
    econtlog.info("ECONT CITIES ◀ %s | status=%s text=%s", url, resp.status_code, (resp.text or "")[:2000])

    resp.raise_for_status()
    data = resp.json()

    cities = data.get("cities") or []
    _ECONT_CITIES_CACHE = {
        "timestamp": now,
        "cities": cities,
    }
    return cities


# ---------- HIGH LEVEL: PRICE FOR A GIVEN ORDER ----------

def get_econt_delivery_price_for_order(order) -> Decimal:
    """
    High-level helper: compute delivery price for *this* Order
    using Econt's CalculatorService.

    Returns a Decimal rounded to 0.01 (BGN).
    On ANY error from Econt, logs and returns Decimal('0.00')
    so the checkout never crashes.
    """
    pm = (str(order.payment_method) or "").strip().lower()
    COD_VALUES = {
        "cash", "cod", "cash_on_delivery", "cash on delivery",
        "наложен", "наложен платеж", "наложен-платеж",
    }
    is_cod = pm in COD_VALUES

    total_bgn = float(order.get_total() or 0)
    weight_kg = float(order.econt_shipment_weight_kg() or 0)
    city = order.city or ""
    postcode = order.post_code or ""

    try:
        price = econt_calculate_price(
            weight_kg=weight_kg,
            receiver_city=city,
            receiver_postcode=postcode,
            total_bgn=total_bgn,
            is_cod=is_cod,
        )
    except Exception as exc:
        # 🔴 THIS is where your 500 from Econt is caught
        econtlog.error(
            "Failed to get Econt delivery price for order %s: %s",
            getattr(order, "pk", "?"),
            exc,
        )
        return Decimal("0.00")

    return Decimal(str(price)).quantize(Decimal("0.01"))


# ---------- LOW LEVEL: RAW CALCULATOR CALL ----------

def econt_calculate_price(*,
                          weight_kg: float,
                          receiver_city: str,
                          receiver_postcode: str,
                          total_bgn: float,
                          is_cod: bool) -> float:
    """
    Low-level helper that calls Econt's CalculatorService
    and returns the total delivery price in BGN for given params.
    """

    url = getattr(
        settings,
        "ECONT_PRICE_URL",
        "https://ee.econt.com/services/Shipments/CalculatorService.getShipmentPrice.json",
    )

    sender_city_name = getattr(settings, "ECONT_SENDER_CITY", "Ямбол")
    sender_city_postcode = getattr(settings, "ECONT_SENDER_POSTCODE", "8600")

    shipment_type = "cargo" if Decimal(str(weight_kg)) > Decimal("50") else "pack"

    payload = {
        "mode": "calculate",
        "shipment": {
            "shipmentType": shipment_type,
            "service": "toDoor",
            "packCount": 1,
            "weight": weight_kg,
            "payer": "RECEIVER" if is_cod else "SENDER",
            "senderAddress": {
                "city": {
                    "country": {"code3": "BGR"},
                    "name": sender_city_name,
                    "postCode": sender_city_postcode,
                }
            },
            "receiverAddress": {
                "city": {
                    "country": {"code3": "BGR"},
                    "name": receiver_city,
                    "postCode": receiver_postcode,
                }
            },
            "services": {
                "declaredValueAmount": total_bgn,
                "declaredValueCurrency": "BGN",
                **(
                    {
                        "cdAmount": total_bgn,
                        "cdCurrency": "BGN",
                    } if is_cod else {}
                ),
            },
        },
    }

    econtlog.info(
        "ECONT PRICE ▶ POST %s | payload=%s",
        url, _json.dumps(payload, ensure_ascii=False)
    )

    resp = requests.post(
        url,
        json=payload,
        auth=HTTPBasicAuth(settings.ECONT_USER, settings.ECONT_PASS),
        headers={"Content-Type": "application/json; charset=utf-8"},
        timeout=30,
    )

    econtlog.info(
        "ECONT PRICE ◀ %s | status=%s text=%s",
        url, resp.status_code, (resp.text or "")[:4000]
    )

    resp.raise_for_status()
    data = resp.json()

    total_price = data.get("totalPrice") or {}
    amount = total_price.get("amount")

    if amount is None:
        raise Exception(f"Econt did not return totalPrice.amount: {data}")

    return float(amount)


def next_workday(d: date | None = None) -> date:
    """
    Returns the next working day (Mon–Fri).

    - Mon–Thu -> next calendar day
    - Fri, Sat, Sun -> Monday
    """
    if d is None:
        d = date.today()

    wd = d.weekday()  # 0=Mon ... 6=Sun
    if wd >= 4:  # Fri(4), Sat(5), Sun(6) -> Monday
        return d + timedelta(days=7 - wd)
    return d + timedelta(days=1)


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
    total_bgn_dec = order.total or Decimal("0.00")
    if not total_bgn_dec:
        try:
            total_bgn_dec = sum(
                (item.price or Decimal("0.00")) * (item.quantity or 0)
                for item in order.order_items.all()
            )
        except Exception:
            # last resort – original get_total()
            total_bgn_dec = order.get_total()

    total_bgn = float(total_bgn_dec)

    # Sender data from settings
    sender_name = getattr(settings, "ECONT_SENDER_NAME", "Сакарела")
    sender_phone = getattr(settings, "ECONT_SENDER_PHONE", "+359878630943")
    sender_city_name = getattr(settings, "ECONT_SENDER_CITY", "Ямбол")
    sender_city_postcode = getattr(settings, "ECONT_SENDER_POSTCODE", "8600")
    sender_street = getattr(settings, "ECONT_SENDER_STREET", "")
    sender_street_no = getattr(settings, "ECONT_SENDER_STREET_NO", "")

    # delivery_day = next_workday(date.today()).strftime("%Y-%m-%d")
    holiday_delivery_day = "workday"  # could also be "halfday" or specific "YYYY-MM-DD"

    # Base label (we override payer for COD below)
    label = {
        "shipmentType": order.econt_shipment_type(),
        "service": "toDoor",
        "packCount": 1,
        "weight": order.econt_shipment_weight_kg(),
        "shipmentDescription": f"Поръчка №{order.pk}",
        "payer": "SENDER",  # default – will be changed to RECEIVER for COD
        "label": {"format": "10x9"},
        "holidayDeliveryDay": holiday_delivery_day,

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
        "instructions": [
            {
                "type": "return",
                "returnInstructionParams": {
                    # Къде да се върне опаковката
                    "returnParcelDestination": "sender",  # обратно при теб

                    # Какво се връща – пратка, не документ
                    "returnParcelIsDocument": False,

                    # Не е празен палет; връщаме същия тип пратка
                    "returnParcelIsEmptyPallet": False,

                    # 0 дни = веднага след доставката
                    "daysUntilReturn": 0,

                    # Кой плаща връщането – ти (подателят)
                    "returnParcelPaymentSide": "sender",

                    # Да се генерира товарителница за връщане още при създаване
                    "printReturnParcel": True,
                },
            }
        ],
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
    """
    Create an Econt label if the order doesn't have one yet.

    - Always returns (shipment_num, label_url, raw_json).
    - Also tries to populate order.shipping_cost from label["totalPrice"]
      if it isn't set yet.
    """
    if getattr(order, "econt_shipment_num", None):
        econtlog.info(
            "Order %s already has shipment_num=%s",
            order.pk,
            order.econt_shipment_num,
        )
        return order.econt_shipment_num, order.label_url, None

    url = getattr(
        settings,
        "ECONT_CREATE_LABEL_URL",
        "https://ee.econt.com/services/Shipments/LabelService.createLabel.json",
    )
    payload = build_econt_label_payload(order)
    econtlog.info(
        "POST %s | order=%s payload=%s",
        url,
        order.pk,
        _json.dumps(payload, ensure_ascii=False),
    )

    resp = requests.post(
        url,
        json=payload,
        auth=HTTPBasicAuth(settings.ECONT_USER, settings.ECONT_PASS),
        headers={"Content-Type": "application/json; charset=utf-8"},
        timeout=30,
    )

    econtlog.info(
        "RESP %s | status=%s text=%s",
        url,
        resp.status_code,
        (resp.text or "")[:4000],
    )

    resp.raise_for_status()
    data = resp.json()

    # ---- extract main label object ----
    label = data.get("label") or data.get("labels") or {}
    if isinstance(label, list) and label:
        label = label[0]

    # ---- SHIPPING PRICE (totalPrice) ----
    total_price_obj = label.get("totalPrice")
    shipping_amount = None

    if isinstance(total_price_obj, dict):
        shipping_amount = total_price_obj.get("amount")
    elif isinstance(total_price_obj, (int, float, str)):
        try:
            shipping_amount = float(total_price_obj)
        except (TypeError, ValueError):
            shipping_amount = None

    if shipping_amount is not None and not order.shipping_cost:
        try:
            from decimal import Decimal
            order.shipping_cost = Decimal(str(shipping_amount)).quantize(
                Decimal("0.01")
            )
            order.save(update_fields=["shipping_cost"])
            econtlog.info(
                "Order %s shipping_cost set from label.totalPrice = %s",
                order.pk,
                order.shipping_cost,
            )
        except Exception as exc:
            econtlog.error(
                "Failed to save shipping_cost from totalPrice for order %s: %s",
                order.pk,
                exc,
            )
    elif shipping_amount is None:
        econtlog.warning(
            "Could not parse Econt totalPrice for order %s: %r",
            order.pk,
            total_price_obj,
        )

    # ---- SHIPMENT NUMBER + LABEL URL ----
    shipment_num = (
            label.get("shipmentNumber")
            or label.get("shipmentNum")
            or ""
    )
    label_url = label.get("labelURL") or label.get("pdfURL") or ""

    if not shipment_num:
        raise Exception(f"Econt returned no shipment number: {data}")

    order.econt_shipment_num = shipment_num
    order.label_url = label_url
    order.save(update_fields=["econt_shipment_num", "label_url"])

    econtlog.info(
        "Order %s -> shipment=%s label=%s",
        order.pk,
        shipment_num,
        label_url,
    )
    return shipment_num, label_url, data


def econt_tracking_url(order) -> str | None:
    """
    Връща URL за проследяване в Еконт или None, ако няма номер.
    """
    num = getattr(order, "econt_shipment_num", "") or ""
    num = str(num).strip()
    if not num:
        return None
    return f"https://www.econt.com/services/track-shipment/{num}"


def send_order_emails_with_tracking(order):
    tracking_url = econt_tracking_url(order)

    # --- compute amounts exactly once, the same way as in mypos_payment ---
    subtotal = Decimal(order.total or 0)
    shipping = Decimal(order.shipping_cost or 0)
    grand_total = (subtotal + shipping).quantize(Decimal("0.01"))

    # --------- ADMIN EMAIL ----------
    admin_email = getattr(settings, "ORDER_NOTIFY_EMAIL", None) or getattr(settings, "DEFAULT_FROM_EMAIL", None)
    if admin_email:
        ctx_admin = {
            "order": order,
            "tracking_url": tracking_url,
            "subtotal": subtotal,
            "shipping": shipping,
            "grand_total": grand_total,
        }
        subject_admin = f"[Сакарела] Нова поръчка № {order.id}"
        text_body_admin = render_to_string("store/email/order_admin.txt", ctx_admin)
        html_body_admin = render_to_string("store/email/order_admin.html", ctx_admin)

        msg_admin = EmailMultiAlternatives(
            subject_admin,
            text_body_admin,
            settings.DEFAULT_FROM_EMAIL,
            [admin_email],
        )
        msg_admin.attach_alternative(html_body_admin, "text/html")
        msg_admin.send(fail_silently=False)

    # --------- CUSTOMER EMAIL ----------
    if order.email:
        ctx_customer = {
            "order": order,
            "tracking_url": tracking_url,
            "subtotal": subtotal,
            "shipping": shipping,
            "grand_total": grand_total,
        }
        subject_customer = f"Вашата поръчка № {order.id} в Сакарела"
        text_body_cust = render_to_string("store/email/order_customer.txt", ctx_customer)
        html_body_cust = render_to_string("store/email/order_customer.html", ctx_customer)

        msg_cust = EmailMultiAlternatives(
            subject_customer,
            text_body_cust,
            settings.DEFAULT_FROM_EMAIL,
            [order.email],
        )
        msg_cust.attach_alternative(html_body_cust, "text/html")
        msg_cust.send(fail_silently=False)
