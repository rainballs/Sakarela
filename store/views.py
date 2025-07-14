# Create your views here.
import base64
import uuid
import logging

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding
from django.conf import settings
from django.contrib import messages
from django.db.models import Prefetch
from django.http import HttpResponse
from django.shortcuts import redirect, get_object_or_404
from django.shortcuts import render
from django.template.loader import render_to_string
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt

from zeep import Client
from zeep.transports import Transport
from requests.auth import HTTPBasicAuth
import requests

from store.models import Product, Order, OrderItem, Category, Brand, PackagingOption
from .forms import OrderForm
from .utils import send_econt_label_request, handle_econt_response, generate_econt_label_xml

logger = logging.getLogger(__name__)

def store_home(request):
    query = request.GET.get('q', '')
    min_price = request.GET.get('min_price')
    max_price = request.GET.get('max_price')
    selected_weight = float(request.GET.get('weight', '1.00'))

    all_categories = Category.objects.order_by('name')
    all_brands = Brand.objects.order_by('name')
    selected_cats = request.GET.getlist('category')
    selected_brands = request.GET.getlist('brand')

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
    cart = request.session.get('cart', {})
    cart_items = []
    cart_total = 0
    for cart_key, qty in cart.items():
        try:
            product_id, packaging_id = cart_key.split('_')
            product = Product.objects.get(pk=product_id)
            packaging = PackagingOption.objects.get(pk=packaging_id)
            price = packaging.current_price
            cart_items.append({
                'product': product,
                'packaging': packaging,
                'quantity': qty,
                'price': price,
                'subtotal': price * qty
            })
            cart_total += price * qty
        except (Product.DoesNotExist, PackagingOption.DoesNotExist, ValueError):
            continue

    context = {
        'products': filtered_products,
        'query': query,
        'max_price': max_effective_price,
        'min_price': min_effective_price,
        'all_categories': all_categories,
        'all_brands': all_brands,
        'selected_cats': selected_cats,
        'selected_brands': selected_brands,
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
        if any(param in request.GET for param in ['min_price', 'max_price', 'category', 'brand']):
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


def view_cart(request):
    cart = request.session.get('cart', {})
    cart_items = []
    cart_total = 0
    for cart_key, qty in cart.items():
        try:
            product_id, packaging_id = cart_key.split('_')
            product = Product.objects.get(pk=product_id)
            packaging = PackagingOption.objects.get(pk=packaging_id)
            price = packaging.current_price
            cart_items.append({'product': product, 'packaging': packaging, 'quantity': qty, 'price': price, 'subtotal': price * qty})
            cart_total += price * qty
        except (Product.DoesNotExist, PackagingOption.DoesNotExist, ValueError):
            continue
    return render(request, 'store/cart.html', {'cart_items': cart_items, 'cart_total': cart_total})


def order_info(request):
    if request.method == 'POST':
        form = OrderForm(request.POST)
        if form.is_valid():
            order = form.save()
            cart = request.session.get('cart', {})
            for cart_key, qty in cart.items():
                try:
                    product_id, packaging_id = cart_key.split('_')
                    product = Product.objects.get(pk=product_id)
                    packaging = PackagingOption.objects.get(pk=packaging_id)
                    price = packaging.current_price
                    OrderItem.objects.create(
                        order=order,
                        product=product,
                        quantity=qty,
                        price=price
                    )
                except (Product.DoesNotExist, PackagingOption.DoesNotExist, ValueError):
                    continue
            request.session['cart'] = {}
            order.update_total()
            if order.payment_method == 'cash':
                return redirect('store:order_summary', pk=order.pk)
            else:
                return redirect('store:mypos_payment', order_id=order.pk)
    else:
        form = OrderForm()
    return render(request, 'store/order_info.html', {'form': form})


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
DEFAULT_PHONE = "0889402222"  # Placeholder phone number
DEFAULT_CURRENCY = "EUR"  # Changed back to BGN
DEFAULT_LANGUAGE = "EN"
DEFAULT_CARD_TOKEN_REQUEST = "0"
DEFAULT_PAYMENT_PARAMS_REQUIRED = "1"


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


def mypos_payment(request, order_id):
    """Handle myPOS payment initiation with proper signature generation"""
    order = get_object_or_404(Order, id=order_id)

    # Generate unique transaction ID if not exists
    if not order.transaction_id:
        order.transaction_id = str(uuid.uuid4())
        order.save(update_fields=["transaction_id"])

    # Get order items
    order_items = order.order_items.select_related('product').all()

    # Clean up URLs - remove trailing slashes for consistency
    base_url = request.build_absolute_uri('/').rstrip('/')
    result_url = f"{base_url}{reverse('store:payment_result')}".rstrip('/')
    callback_url = f"{base_url}{reverse('store:payment_callback')}".rstrip('/')

    # Base parameters required for signature
    params = {
        "IPCmethod": "IPCPurchase",
        "IPCVersion": "1.4",
        "IPCLanguage": DEFAULT_LANGUAGE,
        "SID": settings.MYPOS_SID,
        "walletnumber": settings.MYPOS_WALLET,
        "Amount": f"{order.get_total():.2f}",
        "Currency": DEFAULT_CURRENCY,
        "OrderID": order.transaction_id,
        "URL_OK": result_url,
        "URL_Cancel": result_url,
        "URL_Notify": callback_url,
        "CardTokenRequest": DEFAULT_CARD_TOKEN_REQUEST,
        "KeyIndex": settings.MYPOS_KEYINDEX,
        "PaymentParametersRequired": DEFAULT_PAYMENT_PARAMS_REQUIRED,
        "customeremail": order.email,
        "customerfirstnames": order.full_name,
        "customerfamilyname": order.last_name,
        "customerphone": DEFAULT_PHONE,
        "customercountry": "BGR",
        # "customercountry": order.country,
        "customercity": order.city,
        "customerzipcode": order.post_code,
        "customeraddress": order.address1,  # Only use primary address
        "Note": "",
        "CartItems": str(order_items.count())
    }

    # Add cart items parameters - these don't go into signature
    cart_items_params = {}
    for idx, item in enumerate(order_items, start=1):
        # If item has a related packaging, use its current_price
        try:
            packaging = PackagingOption.objects.get(product=item.product, price=item.price)
            price = packaging.current_price
        except PackagingOption.DoesNotExist:
            price = item.price
        cart_items_params.update({
            f'Article_{idx}': item.product.name[:100],
            f'Quantity_{idx}': str(item.quantity),
            f'Price_{idx}': f"{price:.2f}",
            f'Currency_{idx}': DEFAULT_CURRENCY,
            f'Amount_{idx}': f"{(item.quantity * price):.2f}"
        })

    # Generate signature before adding cart items
    try:
        params["Signature"] = _generate_signature(params)
    except Exception as e:
        logger.exception("Error generating payment signature")
        return render(request, "store/payment_error.html", {"error": str(e), "debug": getattr(settings, 'DEBUG', False)})

    # Add cart items parameters after signature generation
    params.update(cart_items_params)

    # Debug information
    print("\nFinal parameters being sent to myPOS:")
    for key, value in params.items():
        print(f"{key}: {value}")

    print("\nVerifying signature components:")
    verify_string = []
    for param in SIGN_ORDER:
        value = params.get(param, '')
        verify_string.append(f"{param}={value}")
    print("Parameters used in signature:\n" + "\n".join(verify_string))

    return render(request, "store/payment_redirect.html", {
        "action_url": settings.MYPOS_BASE_URL,
        "params": params,
    })


@csrf_exempt
def payment_callback(request):
    """
    myPOS will POST here when the payment completes (server→server).
    We look up the Order by transaction_id and mark it paid.
    """
    if request.method == 'POST':
        data = request.POST
        order_id = data.get("OrderID")
        status = data.get("Status")

        print(f"Payment callback received: OrderID={order_id}, Status={status}")

        try:
            order = Order.objects.get(transaction_id=order_id)

            if status == "Success":
                order.payment_status = "paid"
            else:
                order.payment_status = "failed"

            order.save(update_fields=['payment_status'])
            print(f"Order {order_id} payment status updated to {order.payment_status}")

        except Order.DoesNotExist:
            print(f"Order with transaction_id {order_id} not found")

    return HttpResponse("OK")


def payment_result(request):
    """
    The customer's browser lands here after payment.
    Display success or failure message based on status.
    """
    status = request.GET.get("Status", "")
    order_id = request.GET.get("OrderID", "")
    error = request.GET.get("error", None)

    context = {
        "status": status,
        "order_id": order_id,
        "success": status == "Success",
        "error": error,
        "debug": getattr(settings, 'DEBUG', False)
    }

    return render(request, "store/payment_result.html", context)


def confirm_order(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    try:
        response = send_econt_label_request(order)
        shipment_num, label_url = handle_econt_response(response)
        order.econt_shipment_num = shipment_num
        order.label_url = label_url
        order.save()
        return redirect("order_detail", order_id=order.id)
    except Exception as e:
        messages.error(request, f"Econt error: {e}")
        return redirect("store:order_summary", pk=order.id)


def test_econt_label(request):
    xml_data = generate_econt_label_xml(order=None)  # or pass an actual order

    url = "https://demo.econt.com/ee/services/createLabel"
    headers = {"Content-Type": "application/xml"}
    auth = HTTPBasicAuth("iasp-dev", "1Asp-dev")

    response = requests.post(url, data=xml_data, headers=headers, auth=auth)

    print("=== Outgoing XML ===")
    print(xml_data.decode("utf-8"))
    print("=== Response Status ===")
    print(response.status_code)
    print("=== Response Content (text) ===")
    print(response.text)
    print("=== Response Content (raw) ===")
    print(response.content)

    if not response.content.strip():
        return HttpResponse("Econt API returned an empty response. Please check your XML and credentials, or try again later.", content_type="text/plain")

    return HttpResponse(response.text, content_type="text/xml")


def generate_econt_label_xml(order=None):
    import xml.etree.ElementTree as ET

    root = ET.Element("parcels")

    client = ET.SubElement(root, "client")
    ET.SubElement(client, "username").text = "iasp-dev"
    ET.SubElement(client, "password").text = "1Asp-dev"

    loadings = ET.SubElement(root, "loadings")
    row = ET.SubElement(loadings, "row")

    sender = ET.SubElement(row, "sender")
    ET.SubElement(sender, "name").text = "Тест клиент"
    ET.SubElement(sender, "phone_num").text = "+359888888888"
    ET.SubElement(sender, "city").text = "София"
    ET.SubElement(sender, "post_code").text = "1000"
    ET.SubElement(sender, "street").text = "бул. България 1"
    ET.SubElement(sender, "country").text = "BGR"

    receiver = ET.SubElement(row, "receiver")
    ET.SubElement(receiver, "name").text = "Иван Тестов"
    ET.SubElement(receiver, "phone_num").text = "+359888123456"
    ET.SubElement(receiver, "email").text = "test@econt.com"
    ET.SubElement(receiver, "city").text = "София"
    ET.SubElement(receiver, "post_code").text = "1404"
    ET.SubElement(receiver, "street").text = "бул. България 1"
    ET.SubElement(receiver, "country").text = "BGR"

    shipment = ET.SubElement(row, "shipment")
    ET.SubElement(shipment, "shipment_type").text = "PACK"
    ET.SubElement(shipment, "weight").text = "1"

    services = ET.SubElement(row, "services")
    ET.SubElement(services, "cd").text = "1"
    ET.SubElement(services, "cd_currency").text = "BGN"
    ET.SubElement(services, "cd_amount").text = "1.00"

    return ET.tostring(root, encoding="utf-8", xml_declaration=True)