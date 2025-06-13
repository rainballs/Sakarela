# Create your views here.
import base64
import json
import uuid

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding
from django.conf import settings
from django.db.models import Max, Case, When, F, FloatField
from django.http import HttpResponse
from django.shortcuts import redirect, get_object_or_404
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt

from store.models import Product, Order, OrderItem, Category, Brand
from .forms import OrderForm


def store_home(request):
    query = request.GET.get('q', '')
    min_price = request.GET.get('min_price')
    max_price = request.GET.get('max_price')

    all_categories = Category.objects.order_by('name')
    all_brands = Brand.objects.order_by('name')

    selected_cats = request.GET.getlist('category')
    selected_brands = request.GET.getlist('brand')

    # Base queryset with effective_price annotation
    base_qs = Product.objects.annotate(
        effective_price=Case(
            When(is_on_sale=True, then=F('sale_price')),
            default=F('price'),
            output_field=FloatField()
        )
    )

    # Apply search and price filtering
    if query:
        base_qs = base_qs.filter(name__icontains=query)
    if min_price:
        base_qs = base_qs.filter(effective_price__gte=float(min_price))
    if max_price:
        base_qs = base_qs.filter(effective_price__lte=float(max_price))
    if selected_cats:
        base_qs = base_qs.filter(category__id__in=selected_cats)
    if selected_brands:
        base_qs = base_qs.filter(brand__id__in=selected_brands)

    # Calculate maximum price for slider range
    max_effective_price = Product.objects.annotate(
        effective_price=Case(
            When(is_on_sale=True, then=F('sale_price')),
            default=F('price'),
            output_field=FloatField()
        )
    ).aggregate(Max('effective_price'))['effective_price__max'] or 100

    # Resolve cart items from session
    cart = request.session.get('cart', {})
    cart_items = []
    for product_id, qty in cart.items():
        try:
            product = Product.objects.get(pk=product_id)
            cart_items.append({'product': product, 'qty': qty})
        except Product.DoesNotExist:
            continue

    return render(request, 'store/store_home.html', {
        'products': base_qs,
        'query': query,
        'max_price': max_effective_price,
        'all_categories': all_categories,
        'all_brands': all_brands,
        'selected_cats': selected_cats,
        'selected_brands': selected_brands,
        'cart_items': cart_items,
    })


def product_detail(request, pk):
    # Fetch the requested product
    product = get_object_or_404(Product, pk=pk)

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
    }

    return render(request, 'store/product_detail.html', context)


def add_to_cart(request, product_id):
    product_id = str(product_id)
    cart = request.session.get('cart', {})
    cart[product_id] = cart.get(product_id, 0) + 1
    request.session['cart'] = cart
    return redirect(request.META.get('HTTP_REFERER', 'store:store_home'))


def remove_from_cart(request, product_id):
    cart = request.session.get('cart', {})
    if str(product_id) in cart:
        del cart[str(product_id)]
    request.session['cart'] = cart
    return redirect(request.META.get('HTTP_REFERER', 'store:store_home'))


def update_cart_quantity(request, product_id, action):
    cart = request.session.get('cart', {})
    if str(product_id) in cart:
        if action == 'increment':
            cart[str(product_id)] += 1
        elif action == 'decrement' and cart[str(product_id)] > 1:
            cart[str(product_id)] -= 1
    request.session['cart'] = cart
    return redirect(request.META.get('HTTP_REFERER', 'store:store_home'))


def view_cart(request):
    cart = request.session.get('cart', {})
    cart_items = []

    for product_id, qty in cart.items():
        product = get_object_or_404(Product, id=product_id)
        cart_items.append({'product': product, 'qty': qty})

    return render(request, 'store/cart.html', {'cart_items': cart_items})


def order_info(request):
    if request.method == 'POST':
        form = OrderForm(request.POST)
        if form.is_valid():
            order = form.save()

            cart = request.session.get('cart', {})
            for product_id, qty in cart.items():
                product = get_object_or_404(Product, pk=product_id)
                price = product.sale_price if product.is_on_sale else product.price
                OrderItem.objects.create(
                    order=order,
                    product=product,
                    quantity=qty,
                    price=price
                )

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


# The exact order of parameters (no more, no less) per the v1_4 IPCPurchase spec
SIGN_ORDER = [
    "IPCmethod",  # Changed from "method" to "IPCmethod"
    "IPCVersion",  # Changed from "version" to "IPCVersion"
    "IPCLanguage",
    "SID",
    "WalletNumber",
    "KeyIndex",
    "Source",  # Add Source parameter
    "OrderID",  # Changed from "OrderId" to "OrderID"
    "Amount",
    "Currency",
    "CartItems",
    "URL_Notify",  # Changed from "URLNotify" to "URL_Notify"
    "URL_OK",  # Changed from "URLOk" to "URL_OK"
    "URL_Cancel",  # Changed from "URLCancel" to "URL_Cancel"
]


def _generate_signature(params):
    """Generate signature for myPOS API request"""
    # Create concatenated string from parameters in specific order
    concat_string = ""
    for key in SIGN_ORDER:
        if key in params:
            concat_string += str(params[key])

    print("CONCATENATED STRING:", concat_string)

    # Base64 encode the concatenated string
    encoded_data = base64.b64encode(concat_string.encode('utf-8'))
    print("BASE64 ENCODED:", encoded_data)

    # Load private key
    try:
        with open(settings.MYPOS_PRIVATE_KEY_PATH, 'rb') as key_file:
            private_key = serialization.load_pem_private_key(
                key_file.read(),
                password=None
            )
    except Exception as e:
        print(f"Error loading private key: {e}")
        raise

    # Sign the encoded data
    signature = private_key.sign(
        encoded_data,
        padding.PKCS1v15(),
        hashes.SHA256()
    )

    # Base64 encode the signature
    signature_b64 = base64.b64encode(signature).decode('utf-8')
    print("SIGNATURE:", signature_b64)

    return signature_b64


def mypos_payment(request, order_id):
    order = get_object_or_404(Order, id=order_id)

    # Generate unique transaction ID if not exists
    if not order.transaction_id:
        order.transaction_id = str(uuid.uuid4())
        order.save(update_fields=["transaction_id"])

    # Prepare cart items
    cart_items = []
    for item in order.order_items.select_related('product').all():
        cart_items.append({
            "Name": item.product.name,
            "Quantity": item.quantity,
            "UnitPrice": f"{item.price:.2f}",
        })

    # Convert cart items to base64 encoded JSON
    cart_json = json.dumps(cart_items, separators=(",", ":"))
    cart_items_b64 = base64.b64encode(cart_json.encode('utf-8')).decode('utf-8')

    # Prepare parameters for myPOS API
    params = {
        "IPCmethod": "IPCPurchase",  # Changed from "method"
        "IPCVersion": "1.4",  # Changed from "version"
        "IPCLanguage": "EN",
        "SID": settings.MYPOS_SID,
        "WalletNumber": settings.MYPOS_WALLET,
        "KeyIndex": settings.MYPOS_KEYINDEX,
        "Source": "sdk_python",  # Add Source parameter
        "OrderID": order.transaction_id,  # Changed from "OrderId"
        "Amount": f"{order.get_total():.2f}",
        "Currency": "BGN",
        "CartItems": cart_items_b64,
        "URL_Notify": request.build_absolute_uri("/store/payment/callback/"),
        "URL_OK": request.build_absolute_uri("/store/payment/result/"),
        "URL_Cancel": request.build_absolute_uri("/store/payment/result/"),
    }

    # Generate signature
    try:
        params["Signature"] = _generate_signature(params)
    except Exception as e:
        print(f"Error generating signature: {e}")
        return render(request, "store/payment_error.html", {"error": str(e)})

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
        order_id = data.get("OrderID")  # Changed from "OrderId"
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

    context = {
        "status": status,
        "order_id": order_id,
        "success": status == "Success"
    }

    return render(request, "store/payment_result.html", context)
