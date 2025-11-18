# Create your views here.
import base64
import uuid
import logging
from collections import OrderedDict
from decimal import Decimal

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding
from django.conf import settings
from django.contrib import messages
from django.db.models import Prefetch
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, get_object_or_404
from django.shortcuts import render
from django.template.loader import render_to_string
from django.urls import reverse, NoReverseMatch
from django.views.decorators.csrf import csrf_exempt
from .cart_utils import cart_items_and_total, get_session_cart, set_session_cart, cart_is_empty
from django.db import transaction
from django.views.decorators.csrf import ensure_csrf_cookie
from django.template import TemplateDoesNotExist
from django.views.decorators.http import require_GET
import json

from zeep import Client
from zeep.transports import Transport
from requests.auth import HTTPBasicAuth
import requests

from store.models import Product, Order, OrderItem, Category, Brand, PackagingOption, Store
from .forms import OrderForm
from .utils import (
    handle_econt_response,
    ensure_econt_label_json,
    econtlog,
    get_econt_delivery_price_for_order,
    econt_get_cities
)

logger = logging.getLogger(__name__)


def econt_city_suggestions(request):
    """
    Return small list of cities for autocomplete.
    GET /store/econt-cities/?q=burg
    Response: {"results": [{"name": "Burgas", "post_code": "8000"}, ...]}
    """
    term = (request.GET.get("q") or "").strip().lower()

    try:
        all_cities = econt_get_cities("BGR")
    except Exception as exc:
        logger.error("Econt getCities failed: %s", exc)
        return JsonResponse({"error": "econt_failed"}, status=500)

    results = []
    for c in all_cities:
        name_bg = (c.get("name") or "").strip()
        name_en = (c.get("nameEn") or "").strip()
        pc = (c.get("postCode") or "").strip()

        # Build a display label like: "[8000] Burgas"
        # Prefer Latin name if present, otherwise BG
        display_name = name_en or name_bg

        haystack = f"{name_bg} {name_en} {pc}".lower()
        if term and term not in haystack:
            continue

        results.append({
            "name": display_name,
            "post_code": pc,
        })
        if len(results) >= 15:
            break

    return JsonResponse({"results": results})


# ---- myPOS-safe OrderID generator (≤30 chars, ASCII, no dashes) ----
def generate_mypos_order_id(order_pk: int) -> str:
    # Example: O000123 + 16 hex chars = 23 chars total
    # (Trim to 30 just in case you tweak the format later)
    return f"O{order_pk:06d}{uuid.uuid4().hex[:16]}".upper()[:30]


SUCCESS_VALUES = {"success", "ok", "approved", "appoved", "accepted"}  # include common typos
CANCEL_VALUES = {"cancel", "cancelled", "canceled", "usercancel", "user_cancel"}
SUCCESS_CODES = {"00", "0"}  # typical “approved” ISO codes


def _extract_status_blob(data):
    """
    Normalize gateway responses: return (status_str_lower, resp_code, reason_text).
    Looks across common field names/cases myPOS uses.
    """
    # common fields with case variants
    status = (
            data.get("Status") or data.get("status") or data.get("STATUS") or
            data.get("Result") or data.get("RESULT") or data.get("TransStatus") or ""
    )
    status_lc = (status or "").strip().lower()

    # response/issuer code variants
    resp_code = (
            data.get("ResponseCode") or data.get("responsecode") or data.get("RespCode") or
            data.get("rc") or data.get("RC") or data.get("Code") or ""
    )
    resp_code = (resp_code or "").strip()

    # reason/message
    reason = (
            data.get("Reason") or data.get("reason") or
            data.get("Message") or data.get("message") or data.get("Error") or ""
    )
    reason = str(reason)

    return status_lc, resp_code, reason


@ensure_csrf_cookie
def store_home(request):
    query = request.GET.get('q', '')
    min_price = request.GET.get('min_price')
    max_price = request.GET.get('max_price')
    selected_weight = float(request.GET.get('weight', '1.00'))

    all_categories = Category.objects.order_by('name')
    all_brands = Brand.objects.order_by('name')
    all_badges = Product.objects.exclude(badge__isnull=True).exclude(badge='').values_list('badge',
                                                                                           flat=True).distinct().order_by(
        'badge')
    selected_cats = request.GET.getlist('category')
    selected_brands = request.GET.getlist('brand')
    selected_badges = request.GET.getlist('badge')

    # All available weights for filter
    all_weights = PackagingOption.objects.values_list('weight', flat=True).distinct().order_by('weight')

    # Only products that have at least one packaging option
    product_ids = PackagingOption.objects.values_list('product_id', flat=True).distinct()
    base_qs = Product.objects.filter(id__in=product_ids)

    # Prefetch all packaging options for each product
    base_qs = base_qs.prefetch_related('packaging_options')

    # Apply search and category/brand filtering
    if query:
        base_qs = base_qs.filter(name__icontains=query)
    if selected_cats:
        base_qs = base_qs.filter(category__id__in=selected_cats)
    if selected_brands:
        base_qs = base_qs.filter(brand__id__in=selected_brands)
    if selected_badges:
        base_qs = base_qs.filter(badge__in=selected_badges)

    # Filter by price for the smallest packaging option
    filtered_products = []
    for product in base_qs:
        packaging = product.packaging_options.all().order_by('weight').first()
        if not packaging:
            continue
        price = packaging.current_price
        if min_price and float(price) < float(min_price):
            continue
        if max_price and float(price) > float(max_price):
            continue
        product.selected_packaging = packaging
        filtered_products.append(product)

    # Calculate min and max price for slider (using the lowest price packaging option per product)
    prices = []
    if base_qs.exists():
        for product in base_qs:
            # Get the smallest packaging option (lowest weight)
            packaging = product.packaging_options.all().order_by('weight').first()
            if not packaging:
                continue
            price = packaging.current_price
            prices.append(float(price))
    if prices:
        max_effective_price = max(prices)
        min_effective_price = min(prices)
    else:
        max_effective_price = 100
        min_effective_price = 0

        # Cart logic
        # cart = request.session.get('cart', {})
        # cart_items = []
        # cart_total = 0
        # for cart_key, qty in cart.items():
        #     try:
        #         product_id, packaging_id = cart_key.split('_')
        #         product = Product.objects.get(pk=product_id)
        #         packaging = PackagingOption.objects.get(pk=packaging_id)
        #         price = packaging.current_price
        #         cart_items.append({
        #             'product': product,
        #             'packaging': packaging,
        #             'quantity': qty,
        #             'price': price,
        #             'subtotal': price * qty
        #         })
        #         cart_total += price * qty
        #     except (Product.DoesNotExist, PackagingOption.DoesNotExist, ValueError):
        #         continue

    # Cart logic (use helpers)
    cart_items, cart_total = cart_items_and_total(request)

    context = {
        'products': filtered_products,
        'query': query,
        'max_price': max_effective_price,
        'min_price': min_effective_price,
        'all_categories': all_categories,
        'all_brands': all_brands,
        'all_badges': all_badges,
        'selected_cats': selected_cats,
        'selected_brands': selected_brands,
        'selected_badges': selected_badges,
        'cart_items': cart_items,
        'cart_total': cart_total,
        'all_weights': all_weights,
        'selected_weight': selected_weight,
    }
    if request.headers.get('HX-Request'):
        # If the search bar is used (q param present), update only the product grid
        if 'q' in request.GET:
            return render(request, 'store/partials/product_grid.html', context)
        # If a filter is changed, update both sidebar and product grid (OOB swap)
        if any(param in request.GET for param in ['min_price', 'max_price', 'category', 'brand', 'badge']):
            sidebar_html = render_to_string('store/partials/sidebar.html', context, request=request)
            product_grid_html = render_to_string('store/partials/product_grid.html', context, request=request)
            return HttpResponse(sidebar_html + product_grid_html)
        # Default: update product grid
        return render(request, 'store/partials/product_grid.html', context)
    return render(request, 'store/store_home.html', context)


def product_detail(request, pk):
    # Fetch the requested product
    product = get_object_or_404(Product, pk=pk)

    # Get packaging options ordered by weight
    packaging_options = product.packaging_options.all().order_by('weight')

    # Get default packaging option (smallest weight)
    default_option = packaging_options.first() if packaging_options.exists() else None

    # Determine related products (same category, excluding the current one)
    related_products = Product.objects.filter(
        category=product.category
    ).exclude(
        pk=product.pk
    )

    # Pass both product and related items into the template context
    context = {
        'product': product,
        'related_products': related_products,
        'packaging_options': packaging_options,
        'default_option': default_option,
    }

    return render(request, 'store/product_detail.html', context)


def add_to_cart(request, product_id):
    if request.method == 'POST':
        product_id = str(product_id)
        packaging_id = str(request.POST.get('packaging_option'))
        quantity = int(request.POST.get('quantity', 1))
        cart = request.session.get('cart', {})
        cart_key = f"{product_id}_{packaging_id}"
        if cart_key in cart:
            cart[cart_key] += quantity
        else:
            cart[cart_key] = quantity
        request.session['cart'] = cart

        messages.success(request, "Продуктът беше добавен в количката!")

    return redirect(request.META.get('HTTP_REFERER', 'store:store_home'))


def remove_from_cart(request, product_id):
    packaging_id = request.GET.get('packaging_id')
    cart = request.session.get('cart', {})
    if packaging_id:
        cart_key = f"{product_id}_{packaging_id}"
        if cart_key in cart:
            del cart[cart_key]
    else:
        # Remove all packaging options for this product
        keys_to_remove = [k for k in cart if k.startswith(f"{product_id}_")]
        for k in keys_to_remove:
            del cart[k]
    request.session['cart'] = cart
    return redirect(request.META.get('HTTP_REFERER', 'store:store_home'))


def update_cart_quantity(request, product_id, action):
    packaging_id = request.GET.get('packaging_id')
    cart = request.session.get('cart', {})
    cart_key = f"{product_id}_{packaging_id}"
    if cart_key in cart:
        if action == 'increment':
            cart[cart_key] += 1
        elif action == 'decrement' and cart[cart_key] > 1:
            cart[cart_key] -= 1
        elif action == 'decrement' and cart[cart_key] <= 1:
            del cart[cart_key]
    request.session['cart'] = cart
    return redirect(request.META.get('HTTP_REFERER', 'store:store_home'))


# Old view
# def view_cart(request):
#     cart = request.session.get('cart', {})
#     cart_items = []
#     cart_total = 0
#     for cart_key, qty in cart.items():
#         try:
#             product_id, packaging_id = cart_key.split('_')
#             product = Product.objects.get(pk=product_id)
#             packaging = PackagingOption.objects.get(pk=packaging_id)
#             price = packaging.current_price
#             cart_items.append(
#                 {'product': product, 'packaging': packaging, 'quantity': qty, 'price': price, 'subtotal': price * qty})
#             cart_total += price * qty
#         except (Product.DoesNotExist, PackagingOption.DoesNotExist, ValueError):
#             continue
#
#     # Get recommended products (random selection of products with packaging options)
#     recommended_products = Product.objects.filter(
#         packaging_options__isnull=False
#     ).prefetch_related('packaging_options').distinct().order_by('?')[:6]  # Get 6 random products
#
#     return render(request, 'store/cart.html', {
#         'cart_items': cart_items,
#         'cart_total': cart_total,
#         'recommended_products': recommended_products
#     })

def view_cart(request):
    cart_items, cart_total = cart_items_and_total(request)

    # Recommended products (unchanged logic)
    recommended_products = Product.objects.filter(
        packaging_options__isnull=False
    ).prefetch_related('packaging_options').distinct().order_by('?')[:6]

    return render(request, 'store/cart.html', {
        'cart_items': cart_items,
        'cart_total': cart_total,
        'recommended_products': recommended_products
    })


# old view
# def order_info(request):
#     if request.method == 'POST':
#         form = OrderForm(request.POST)
#         if form.is_valid():
#             order = form.save()
#             cart = request.session.get('cart', {})
#             for cart_key, qty in cart.items():
#                 try:
#                     product_id, packaging_id = cart_key.split('_')
#                     product = Product.objects.get(pk=product_id)
#                     packaging = PackagingOption.objects.get(pk=packaging_id)
#                     price = packaging.current_price
#                     OrderItem.objects.create(
#                         order=order,
#                         product=product,
#                         quantity=qty,
#                         price=price
#                     )
#                 except (Product.DoesNotExist, PackagingOption.DoesNotExist, ValueError):
#                     continue
#             request.session['cart'] = {}
#             order.update_total()
#             if order.payment_method == 'cash':
#                 return redirect('store:order_summary', pk=order.pk)
#             else:
#                 return redirect('store:mypos_payment', order_id=order.pk)
#     else:
#         form = OrderForm()
#     return render(request, 'store/order_info.html', {'form': form})
def order_info(request):
    """
    - If cart is empty -> back to cart.
    - Save order + snapshot cart as OrderItems.
    - Recalculate total (including weight).
    - COD -> create Econt label NOW and go to order summary.
    - Card/other -> go to myPOS.
    """
    if request.method == 'POST':
        if cart_is_empty(request):
            messages.error(request, "Количката е празна. Моля, добавете продукти.")
            return redirect('store:view_cart')

        form = OrderForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                order = form.save()

                items, _total = cart_items_and_total(request)
                for row in items:
                    unit_weight_kg = Decimal("0.0")

                    # 1) If cart row already has weight in kg
                    if "weight_kg" in row:
                        unit_weight_kg = Decimal(str(row["weight_kg"]))

                    # 2) Or generic 'weight' in kg
                    elif "weight" in row:
                        unit_weight_kg = Decimal(str(row["weight"]))

                    # 3) cart stores the PackagingOption object (weight in kg)
                    elif "packaging" in row and isinstance(row["packaging"], PackagingOption):
                        unit_weight_kg = Decimal(str(row["packaging"].weight))

                    # 4) cart stores only packaging_id (again weight in kg)
                    elif "packaging_id" in row:
                        try:
                            pack = PackagingOption.objects.get(pk=row["packaging_id"])
                            unit_weight_kg = Decimal(str(pack.weight))
                        except PackagingOption.DoesNotExist:
                            unit_weight_kg = Decimal("0.0")

                    OrderItem.objects.create(
                        order=order,
                        product=row["product"],
                        quantity=row["quantity"],
                        price=row["price"],
                        # NOTE: field name is unit_weight_g, but we now store kg there:
                        unit_weight_g=unit_weight_kg,
                    )

                # 3) Recalculate order total from items (also sets total_weight_kg)
                order.update_total()
                # 1) Calculate delivery price from Econt and save it
                try:
                    shipping_price = get_econt_delivery_price_for_order(order)
                    order.shipping_cost = shipping_price
                    order.save(update_fields=["shipping_cost"])
                except Exception as e:
                    econtlog.error("Failed to get Econt delivery price for order %s: %s", order.pk, e)
                # create Econt label etc... (rest of your function unchanged)
                # --------------------------------------------------------------
                try:
                    sn, url, _raw = ensure_econt_label_json(order)
                    if sn:
                        messages.success(request, f"Еконт товарителница създадена: № {sn}")
                except Exception as e:
                    messages.error(request, f"Грешка при създаване на Еконт товарителница: {e}")

                pm = (str(order.payment_method) or "").strip().lower()
                COD_VALUES = {
                    "cash", "cod", "cash_on_delivery", "cash on delivery",
                    "наложен", "наложен платеж", "наложен-платеж",
                }
                is_cod = pm in COD_VALUES

                if is_cod:
                    set_session_cart(request, {})
                    return redirect('store:order_summary', pk=order.pk)

                return redirect('store:mypos_payment', order_id=order.pk)
        # invalid form:
        return render(request, "store/order_info.html", {"form": form})

    # GET:
    if cart_is_empty(request):
        messages.info(request, "Количката е празна.")
        return redirect('store:store_home')

    return render(request, "store/order_info.html", {"form": OrderForm()})


def order_summary(request, pk):
    order = get_object_or_404(Order, pk=pk)
    items = order.order_items.select_related('product').all()

    return render(request, 'store/order_summary.html', {
        'order': order,
        'cart_items': items,
    })


# The exact order of parameters for the v1_4 IPCPurchase spec
SIGN_ORDER = [
    "IPCmethod",
    "IPCVersion",
    "IPCLanguage",
    "SID",
    "walletnumber",
    "Amount",
    "Currency",
    "OrderID",
    "URL_OK",
    "URL_Cancel",
    "URL_Notify",
    "CardTokenRequest",
    "KeyIndex",
    "PaymentParametersRequired",
    "customeremail",
    "customerfirstnames",
    "customerfamilyname",
    "customerphone",
    "customercountry",
    "customercity",
    "customerzipcode",
    "customeraddress",
    "Note",
    "CartItems"
]

# Default values for myPOS integration
# DEFAULT_PHONE = "0889402222"  # Placeholder phone number
DEFAULT_CURRENCY = "BGN"
DEFAULT_LANGUAGE = "EN"
DEFAULT_CARD_TOKEN_REQUEST = "0"
DEFAULT_PAYMENT_PARAMS_REQUIRED = "1"


def bg_phone_no_prefix(phone: str) -> str:
    """
    Normalize a Bulgarian phone and ALWAYS return it prefixed with +359.
    - Strips all non-digits
    - Removes leading 359 or 0 (to get the 9-digit national number)
    - Trims to 9 digits (safety)
    - Returns '+359<9 digits>' or '' if nothing usable
    """
    if not phone:
        return ''
    digits = ''.join(ch for ch in phone if ch.isdigit())

    # get national significant number (usually 9 digits)
    if digits.startswith('359'):
        digits = digits[3:]
    elif digits.startswith('0'):
        digits = digits[1:]

    local = digits[:9]
    return f'+359{local}' if local else ''


def _generate_signature(params):
    """Generate signature for myPOS API request following their v1.4 specification"""
    required_settings = [
        'MYPOS_PRIVATE_KEY_PATH', 'MYPOS_SID', 'MYPOS_WALLET', 'MYPOS_KEYINDEX', 'MYPOS_BASE_URL'
    ]
    for s in required_settings:
        if not hasattr(settings, s) or not getattr(settings, s):
            logger.error(f"Missing myPOS setting: {s}")
            raise Exception(f"Payment configuration error. Please contact support. (Missing {s})")

    # Create concatenated string from parameters in specific order
    values_to_sign = []

    print("\nDebug - Parameters before signature generation:")
    for param_name in SIGN_ORDER:
        value = str(params.get(param_name, '')).strip()
        print(f"{param_name}: {value}")
        values_to_sign.append(value)

    # Join all values with '-'
    concat_string = '-'.join(values_to_sign)

    print("\nDebug - Concatenated string before base64:", concat_string)

    try:
        # Base64 encode the concatenated string
        encoded_data = base64.b64encode(concat_string.encode('utf-8'))
        print("Debug - Base64 encoded string:", encoded_data)

        # Load private key
        with open(settings.MYPOS_PRIVATE_KEY_PATH, 'rb') as key_file:
            key_data = key_file.read()
            print(f"\nDebug - Private key loaded from {settings.MYPOS_PRIVATE_KEY_PATH}")
            print("First few bytes of key:", key_data[:50])

            private_key = serialization.load_pem_private_key(
                key_data,
                password=None
            )

        # Sign the encoded data with SHA256
        signature = private_key.sign(
            encoded_data,
            padding.PKCS1v15(),
            hashes.SHA256()
        )

        # Base64 encode the signature
        signature_b64 = base64.b64encode(signature).decode('utf-8')
        print("\nDebug - Final signature:", signature_b64)

        return signature_b64

    except Exception as e:
        logger.exception("Error in signature generation")
        raise Exception("Payment signature error. Please try again later or contact support.")


def sign_params_in_post_order(ordered_params: "OrderedDict[str, str]", private_key_pem_bytes: bytes) -> str:
    """
    Signs exactly the values you will POST (all keys except 'Signature'),
    in the same insertion order, as myPOS expects:
    base64( '-'.join(values) ) -> sign(SHA256, RSA) -> base64(signature)
    """
    # 1) Concatenate values in post order (excluding 'Signature')
    values = []
    for k, v in ordered_params.items():
        if k == "Signature":
            continue
        values.append(str(v).strip())
    concatenated = "-".join(values)

    # 2) Base64 encode concatenated string
    to_sign = base64.b64encode(concatenated.encode("utf-8"))

    # 3) Load PK and sign (SHA256, PKCS#1 v1.5)
    private_key = serialization.load_pem_private_key(private_key_pem_bytes, password=None)
    signature = private_key.sign(to_sign, padding.PKCS1v15(), hashes.SHA256())

    # 4) Return base64(signature)
    return base64.b64encode(signature).decode("utf-8")


def mypos_payment(request, order_id):
    """Handle myPOS payment initiation with proper signature generation"""
    order = get_object_or_404(Order, id=order_id)

    # 💰 Products + shipping (for card payments)
    total = order.total or Decimal("0.00")
    shipping = order.shipping_cost or Decimal("0.00")
    gross_amount = (total + shipping).quantize(Decimal("0.01"))

    # 1) Create Econt label UPFRONT for card payments (safe to call repeatedly)
    try:
        ensure_econt_label_json(order)
    except Exception as e:
        # Do NOT block payment if Econt is down; just log and proceed.
        logger.error("Econt upfront label failed for order %s: %s", order.id, e)

    try:
        # 2) Ensure we have a myPOS-safe OrderID (<=30 chars, no dashes)
        if (not order.transaction_id) or ("-" in (order.transaction_id or "")) or (len(order.transaction_id) > 30):
            order.transaction_id = generate_mypos_order_id(order.pk)
            order.save(update_fields=["transaction_id"])

        # 3) Build return/callback URLs
        result_url = request.build_absolute_uri(reverse('store:payment_result'))
        callback_url = request.build_absolute_uri(reverse('store:payment_callback'))

        # Always include OrderID in the browser redirect URL
        result_url_with_id = f"{result_url}?OrderID={order.transaction_id}"

        # Remember as a fallback in case gateway omits it
        request.session['last_txn'] = order.transaction_id

        # 4) Build params in insertion order (exactly as posted)
        params = OrderedDict([
            ("IPCmethod", "IPCPurchase"),
            ("IPCVersion", "1.4"),
            ("IPCLanguage", DEFAULT_LANGUAGE),  # "EN"
            ("SID", settings.MYPOS_SID),
            ("walletnumber", settings.MYPOS_WALLET),
            ("Amount", f"{gross_amount:.2f}"),
            ("Currency", DEFAULT_CURRENCY),  # "BGN"
            ("OrderID", order.transaction_id),
            ("URL_OK", result_url_with_id),
            ("URL_Cancel", result_url_with_id),
            ("URL_Notify", callback_url),
            ("CardTokenRequest", DEFAULT_CARD_TOKEN_REQUEST),  # "0"
            ("KeyIndex", str(settings.MYPOS_KEYINDEX)),
            ("PaymentParametersRequired", DEFAULT_PAYMENT_PARAMS_REQUIRED),  # "1"
            ("customeremail", order.email or ""),
            ("customerfirstnames", order.full_name or ""),
            ("customerfamilyname", order.last_name or ""),
            ("customerphone", bg_phone_no_prefix(order.phone)),
            ("customercountry", "BGR"),
            ("customercity", order.city or ""),
            ("customerzipcode", order.post_code or ""),
            ("customeraddress", order.address1 or ""),
            ("Note", ""),
        ])

        # 5) Line items (BEFORE signing)
        order_items = order.order_items.select_related('product').all()
        params["CartItems"] = str(order_items.count())
        for idx, item in enumerate(order_items, start=1):
            price = float(item.price)  # use captured OrderItem price
            params[f'Article_{idx}'] = (item.product.name or "")[:100]
            params[f'Quantity_{idx}'] = str(int(item.quantity))
            params[f'Price_{idx}'] = f"{price:.2f}"
            params[f'Currency_{idx}'] = DEFAULT_CURRENCY
            params[f'Amount_{idx}'] = f"{item.quantity * price:.2f}"

        # 6) Sign (exclude Signature from the string to sign)
        with open(settings.MYPOS_PRIVATE_KEY_PATH, "rb") as fh:
            pk_bytes = fh.read()
        params["Signature"] = sign_params_in_post_order(params, pk_bytes)

        # 7) (Optional) precise debug/audit logging
        paylog = logging.getLogger("payments")
        sum_items = sum(float(i.quantity) * float(i.price) for i in order_items)
        concat_debug = "-".join(str(v).strip() for k, v in params.items() if k != "Signature")
        b64_debug = base64.b64encode(concat_debug.encode("utf-8")).decode("ascii")
        paylog.info(
            "POST myPOS | endpoint=%s | OrderID=%s | Amount=%s | SumItems=%.2f | Currency=%s | KeyIndex=%s",
            settings.MYPOS_BASE_URL, params.get("OrderID"), params.get("Amount"),
            sum_items, params.get("Currency"), params.get("KeyIndex"),
        )
        paylog.info("concat=%s", concat_debug)
        paylog.info("base64=%s", b64_debug)
        paylog.info("signature=%s...%s", params["Signature"][:12], params["Signature"][-12:])

        # 8) Auto-post form to myPOS
        return render(request, "store/payment_redirect.html", {
            "action_url": settings.MYPOS_BASE_URL,
            "params": params,
        })

    except Exception:
        logger.exception("myPOS initiation failed for order %s", order.id)
        messages.error(request, "Възникна грешка при иницииране на плащането. Опитайте отново.")
        return redirect('store:order_summary', pk=order.pk)


# @csrf_exempt
# def payment_callback(request):
#     """
#     myPOS will POST here when the payment completes (server→server).
#     We look up the Order by transaction_id and mark it paid.
#     """
#     if request.method == 'POST':
#         data = request.POST
#         order_id = data.get("OrderID")
#         status = data.get("Status")
#
#         print(f"Payment callback received: OrderID={order_id}, Status={status}")
#
#         try:
#             order = Order.objects.get(transaction_id=order_id)
#
#             if status == "Success":
#                 order.payment_status = "paid"
#             else:
#                 order.payment_status = "failed"
#
#             order.save(update_fields=['payment_status'])
#             print(f"Order {order_id} payment status updated to {order.payment_status}")
#
#         except Order.DoesNotExist:
#             print(f"Order with transaction_id {order_id} not found")
#
#     return HttpResponse("OK")

@csrf_exempt
def payment_callback(request):
    """
    Server→server notification from myPOS.
    Marks order paid/failed based on common status/code variants.
    """
    data = request.POST or request.GET  # some gateways GET this
    if getattr(settings, "DEBUG", False):
        try:
            import json as _json
            print("=== payment_callback payload ===")
            print(_json.dumps((request.POST or {}).dict(), ensure_ascii=False))
        except Exception:
            pass

    order_id = (
            data.get("OrderID") or data.get("orderid") or data.get("order_id") or ""
    )
    order_id = (order_id or "").strip()

    status_lc, resp_code, reason = _extract_status_blob(data)

    is_success = (
            (status_lc in SUCCESS_VALUES) or
            (resp_code in SUCCESS_CODES)
    )

    try:
        order = Order.objects.get(transaction_id=order_id)
        order.payment_status = "paid" if is_success else "failed"
        order.save(update_fields=["payment_status"])

        if getattr(settings, "DEBUG", False):
            print(
                f"[callback] tx={order_id} status='{status_lc}' code='{resp_code}' "
                f"-> {order.payment_status} | reason={reason!r}"
            )

        # 🔵 NEW/RESTORED: create Econt label only AFTER successful card payment
        try:
            pm = (str(order.payment_method) or "").strip().lower()
            COD_VALUES = {
                "cash", "cod", "cash_on_delivery", "cash on delivery",
                "наложен", "наложен платеж", "наложен-платеж",
            }
            is_cod = pm in COD_VALUES

            if order.payment_status == "paid" and not is_cod and not order.econt_shipment_num:
                ensure_econt_label_json(order)
        except Exception as e:
            logger.error(
                "Failed to create Econt label after card payment for order %s: %s",
                order.pk, e
            )

    except Order.DoesNotExist:
        if getattr(settings, "DEBUG", False):
            print(f"[callback] Order not found for transaction_id={order_id}")

    return HttpResponse("OK")


# old view
# def payment_result(request):
#     """
#     The customer's browser lands here after payment.
#     Display success or failure message based on status.
#     """
#     status = request.GET.get("Status", "")
#     order_id = request.GET.get("OrderID", "")
#     error = request.GET.get("error", None)
#
#     context = {
#         "status": status,
#         "order_id": order_id,
#         "success": status == "Success",
#         "error": error,
#         "debug": getattr(settings, 'DEBUG', False)
#     }
#
#     return render(request, "store/payment_result.html", context)
#


# def payment_result(request):
#     status = request.GET.get("Status", "")
#     transaction_id = request.GET.get("OrderID", "")
#     error = request.GET.get("error", None)
#
#     order = Order.objects.filter(transaction_id=transaction_id).first()
#     success_by_gateway = (status == "Success")
#     paid_by_server = bool(order and getattr(order, "payment_status", "") == "paid")
#
#     if success_by_gateway and paid_by_server:
#         set_session_cart(request, {})
#         msg = "Плащането е успешно!"
#         success_flag = True
#     elif success_by_gateway and not paid_by_server:
#         msg = "Плащането се обработва. Моля, изчакайте потвърждение."
#         success_flag = False
#     else:
#         msg = "Плащането е неуспешно." if status else "Връщане от плащане."
#         success_flag = False
#
#     context = {
#         "status": status,
#         "order_id": transaction_id,
#         "success": success_flag,
#         "error": error,
#         "message": msg,
#         "debug": getattr(settings, 'DEBUG', False),
#     }
#     return render(request, "store/payment_result.html", context)

# def payment_result(request):
#     # Read params case-insensitively and trim
#     raw_status = (request.GET.get("Status") or request.GET.get("status") or "").strip()
#     transaction_id = (request.GET.get("OrderID") or request.GET.get("orderid") or "").strip()
#     error = request.GET.get("error", None)
#
#     # Normalize status to lowercase for logic, keep original for display
#     status_lc = raw_status.lower()
#
#     order = Order.objects.filter(transaction_id=transaction_id).first()
#     paid_by_server = bool(order and getattr(order, "payment_status", "") == "paid")
#     success_by_gateway = (status_lc == "success")
#     cancelled = status_lc in ("cancel", "cancelled")
#
#     # Three clear states
#     pending = success_by_gateway and not paid_by_server  # waiting for server→server callback
#     success_flag = success_by_gateway and paid_by_server  # gateway ok + our DB says paid
#     failed = (not success_by_gateway) and (not cancelled)  # any other non-cancel failure
#
#     # Clear cart only when we are 100% sure it's paid
#     if success_flag:
#         set_session_cart(request, {})
#
#     context = {
#         "status": raw_status or "",  # keep as-is for template display
#         "order_id": transaction_id,
#         "success": success_flag,
#         "pending": pending,
#         "cancelled": cancelled,
#         "failed": failed,
#         "error": error,
#         "debug": getattr(settings, 'DEBUG', False),
#     }
#     return render(request, "store/payment_result.html", context)
# def payment_result(request):
#     # Accept both GET and POST (some myPOS methods POST back to URL_OK)
#     data = request.GET.copy()
#     if not data:
#         data = request.POST.copy()
#
#     # Dump everything when DEBUG to see what the gateway actually sent
#     if getattr(settings, "DEBUG", False):
#         try:
#             import json as _json
#             print("=== payment_result payload ===")
#             print("GET:", _json.dumps(request.GET.dict(), ensure_ascii=False))
#             print("POST:", _json.dumps(request.POST.dict(), ensure_ascii=False))
#         except Exception:
#             pass
#
#     # Read common variants (case-insensitive, different keys)
#     raw_status = (data.get("Status") or data.get("status") or data.get("STATUS") or "").strip()
#     transaction_id = (data.get("OrderID") or data.get("orderid") or data.get("order_id") or "").strip()
#     error = data.get("error") or data.get("Reason") or data.get("Message")
#
#     order = Order.objects.filter(transaction_id=transaction_id).first()
#     paid_by_server = bool(order and getattr(order, "payment_status", "") == "paid")
#
#     status_lc = raw_status.lower()
#     success_by_gateway = (status_lc == "success")
#     cancelled = status_lc in ("cancel", "cancelled")
#
#     pending = success_by_gateway and not paid_by_server
#     success_flag = success_by_gateway and paid_by_server
#     failed = (not success_by_gateway) and (not cancelled)
#
#     # Only clear cart when confirmed paid in DB
#     if success_flag:
#         set_session_cart(request, {})
#
#     context = {
#         "status": raw_status or "",
#         "order_id": transaction_id,
#         "success": success_flag,
#         "pending": pending,
#         "cancelled": cancelled,
#         "failed": failed,
#         "error": error,
#         "debug": getattr(settings, 'DEBUG', False),
#     }
#     return render(request, "store/payment_result.html", context)

# --- add these constants once (top of file is fine) ---

# --- Status dictionaries ---
SUCCESS_VALUES = {"success", "ok", "approved", "paid", "completed", "authorized", "authorised"}
CANCEL_VALUES = {"cancel", "cancelled", "canceled", "user_cancel", "usercancel"}

# Codes: extend with what myPOS actually emits
SUCCESS_CODES = {"0", "00", "000", "200"}  # OK-ish codes
FAIL_VALUES = {"failed", "failure", "declined", "denied", "error"}
FAIL_CODES = {"05", "51", "54", "57", "62", "65"}  # Do not honor, insufficient funds, expired, etc.


@csrf_exempt
def payment_result(request):
    """
    Browser lands here from myPOS (URL_OK / URL_Cancel).

    Rules:
      - DB is the source of truth (payment_status='paid' => SUCCESS) — handled where you read the order.
      - If DB not yet paid and Status/ResponseCode are missing/OK => PENDING (not FAILED).
      - CANCEL values => CANCELLED immediately.
      - Explicit decline values/codes => FAILED.
    """
    # 1) Accept both GET and POST
    data = request.GET or request.POST

    # 2) Debug dump
    if getattr(settings, "DEBUG", False):
        try:
            import json as _json
            print("=== payment_result payload ===")
            print("GET :", _json.dumps(getattr(request.GET, "dict", lambda: {})(), ensure_ascii=False))
            print("POST:", _json.dumps(getattr(request.POST, "dict", lambda: {})(), ensure_ascii=False))
        except Exception:
            pass

    # 3) Extract fields (case-insensitive), trimmed
    raw_status = (data.get("Status") or data.get("status") or data.get("STATUS") or "").strip()
    status_lc = raw_status.lower()

    # Some integrations also send result/response code fields
    resp_code = (
            data.get("ResponseCode") or data.get("responsecode") or
            data.get("ResultCode") or data.get("resultcode") or
            data.get("RespCode") or data.get("respcode") or
            ""
    )
    resp_code = str(resp_code).strip()

    txn_id = (data.get("OrderID") or data.get("orderid") or data.get("order_id") or "").strip()
    if not txn_id:
        # fallback to what we initiated (set in mypos_payment)
        txn_id = (request.session.get("last_txn") or "").strip()

    error_msg = str(
        data.get("error") or data.get("Reason") or data.get("Message") or data.get("reason") or ""
    )

    # 4) DB-first truth
    order = Order.objects.filter(transaction_id=txn_id).first()
    order_pk = order.pk if order else None
    paid_by_server = bool(order and getattr(order, "payment_status", "") == "paid")

    # 5) Decide flags
    if paid_by_server:
        success = True
        pending = False
        cancelled = False
        failed = False
    else:
        has_status = bool(raw_status)
        has_code = bool(resp_code)

        is_success = (status_lc in SUCCESS_VALUES) or (resp_code in SUCCESS_CODES)
        is_cancel = (status_lc in CANCEL_VALUES)
        is_fail = (status_lc in FAIL_VALUES) or (resp_code in FAIL_CODES)

        if is_cancel:
            success = False;
            pending = False;
            cancelled = True;
            failed = False
        elif is_fail:
            success = False;
            pending = False;
            cancelled = False;
            failed = True
        elif is_success:
            # Gateway indicates success but DB not yet updated by callback -> pending
            success = False;
            pending = True;
            cancelled = False;
            failed = False
        elif not has_status and not has_code:
            # Typical browser redirect with no data -> pending, not failed
            success = False;
            pending = True;
            cancelled = False;
            failed = False
        else:
            # Unknown non-success signal -> failed
            success = False;
            pending = False;
            cancelled = False;
            failed = True

    # 6) Clear cart ONLY when DB says it's paid
    if success:
        set_session_cart(request, {})

    ctx = {
        "status": raw_status or (resp_code or ""),  # show code if that's all we have
        "order_id": txn_id,
        "order_pk": order_pk,
        "success": success,
        "pending": pending,
        "cancelled": cancelled,
        "failed": failed,
        "error": error_msg,
        "debug": bool(getattr(settings, "DEBUG", False)),
    }

    if getattr(settings, "DEBUG", False):
        print(f"[payment_result] ctx: order_id={txn_id} DBpaid={paid_by_server} "
              f"raw_status='{raw_status}' resp_code='{resp_code}' "
              f"-> success={success}, pending={pending}, cancelled={cancelled}, failed={failed}")

    # 7) Render normally; if template fails, respond safely (never 500 here)
    try:
        return render(request, "store/payment_result.html", ctx)
    except (TemplateDoesNotExist, NoReverseMatch) as e:
        html = f"""<!doctype html>
<html lang="en"><meta charset="utf-8"><title>Payment Result</title>
<body style="font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial;max-width:700px;margin:40px auto">
<h1>Payment Result</h1>
<p><strong>Status:</strong> {raw_status or resp_code}</p>
<p><strong>Order ID:</strong> {txn_id}</p>
<p><strong>Error:</strong> {error_msg}</p>
<p><em>Template problem: {e.__class__.__name__}: {e}</em></p>
<p><a href="/store/">Back to store</a> &nbsp; <a href="/store/cart/">View cart</a></p>
</body></html>"""
        return HttpResponse(html, status=200)


# def where_to_buy(request):
#     # Store locations data - you can move this to a database model later
#     store_locations = [
#         {
#             'name': 'Сакарела - Централен офис',
#             'lat': 42.6977,
#             'lng': 23.3219,
#             'address': 'София, България',
#             'type': 'office',
#             'phone': '+359 2 123 4567',
#             'hours': 'Понеделник - Петък: 9:00 - 18:00'
#         },
#         {
#             'name': 'Сакарела - Магазин 1',
#             'lat': 42.6977,
#             'lng': 23.3219,
#             'address': 'ул. Витоша 1, София',
#             'type': 'store',
#             'phone': '+359 2 123 4568',
#             'hours': 'Понеделник - Неделя: 8:00 - 22:00'
#         },
#         {
#             'name': 'Сакарела - Магазин 2',
#             'lat': 42.6977,
#             'lng': 23.3219,
#             'address': 'ул. Граф Игнатиев 2, София',
#             'type': 'store',
#             'phone': '+359 2 123 4569',
#             'hours': 'Понеделник - Неделя: 8:00 - 22:00'
#         },
#         {
#             'name': 'Сакарела - Магазин 3',
#             'lat': 42.6977,
#             'lng': 23.3219,
#             'address': 'ул. Шипка 3, София',
#             'type': 'store',
#             'phone': '+359 2 123 4570',
#             'hours': 'Понеделник - Неделя: 8:00 - 22:00'
#         }
#     ]
#
#     context = {
#         'store_locations': json.dumps(store_locations),
#         'google_maps_api_key': getattr(settings, 'GOOGLE_MAPS_API_KEY', 'YOUR_API_KEY')
#     }
#
#     return render(request, 'store/where_to_buy.html', context)


def where_to_buy(request):
    stores = Store.objects.filter(show_on_map=True).only(
        "id", "name", "city", "address", "logo", "map_x_pct", "map_y_pct",
    )
    brands = Store.objects.filter(show_on_map=True).order_by().values_list("name", flat=True).distinct()
    return render(request, "store/where_to_buy.html", {"stores": stores, "brands": brands})
