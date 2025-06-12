# Create your views here.
import base64
import json
import uuid
from pathlib import Path

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
    product = get_object_or_404(Product, pk=pk)
    return render(request, 'store/product_detail.html', {'product': product})


def add_to_cart(request, product_id):
    product_id = str(product_id)  # 🔧 Ensure key matches the rest
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
    cart = request.session.get('cart', {})
    # cart_items = []
    # total = 0

    # for product_id, qty in cart.items():
    #     product = get_object_or_404(Product, id=product_id)
    #     price = float(product.sale_price if product.is_on_sale else product.price)
    #     total += price * qty
    #     cart_items.append({'product': product, 'qty': qty, 'price': price})

    order = get_object_or_404(Order, pk=pk)
    items = order.order_items.select_related('product').all()

    return render(request, 'store/order_summary.html', {
        'order': order,
        'cart_items': items,
        # 'cart_total': total,
    })


# The exact order of parameters (no more, no less) per the v1_4 IPCPurchase spec
SIGN_ORDER = [
    "method",  # e.g. IPCPurchase
    "version",  # "1.4"
    "IPCLanguage",  # e.g. "EN"  <— this field is required by the spec!
    "WalletNumber",
    "SID",
    "KeyIndex",
    "ClientNumber",
    "TerminalId",
    "OrderId",
    "Amount",
    "Currency",
    "CartItems",
    "URLNotify",
    "URLOk",
    "URLCancel",
]


def _generate_signature(params):
    # 1) dash-join
    joined = "-".join(str(params[k]) for k in SIGN_ORDER).encode("utf-8")
    print("DASHED:", joined)
    # 2) Base64 that string
    payload = base64.b64encode(joined)
    print("PAYLOAD:", payload)
    # 3) load your private key
    pem = Path(settings.MYPOS_PRIVATE_KEY_PATH).read_bytes()
    priv = serialization.load_pem_private_key(pem, password=None)

    # 4) sign with SHA-256
    raw_sig = priv.sign(
        payload,
        padding.PKCS1v15(),
        hashes.SHA256()
    )
    sig = base64.b64encode(raw_sig).decode().strip()
    print("SIG:", sig)

    # 5) Base-64 the signature itself
    return sig


def mypos_payment(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    order.transaction_id = str(uuid.uuid4())
    order.save(update_fields=["transaction_id"])

    amt = f"{order.get_total():.2f}"
    cur = "BGN"

    # **directly** point at your store/ URLs
    notify = request.build_absolute_uri("/store/payment/callback/")
    ok = request.build_absolute_uri("/store/payment/result/")
    cancel = ok

    params = {
        "method": "IPCPurchase",
        "version": "1.4",
        "IPCLanguage": "EN",  # <— new
        "WalletNumber": settings.MYPOS_WALLET,
        "SID": settings.MYPOS_SID,
        "KeyIndex": settings.MYPOS_KEYINDEX,
        "ClientNumber": settings.MYPOS_CLIENT_NUMBER,
        "TerminalId": settings.MYPOS_TERMINAL_ID,
        "OrderId": order.transaction_id,
        "Amount": f"{order.get_total():.2f}",
        "Currency": "BGN",
        "URLNotify": request.build_absolute_uri("/store/payment/callback/"),
        "URLOk": request.build_absolute_uri("/store/payment/result/"),
        "URLCancel": request.build_absolute_uri("/store/payment/result/"),
    }

    cart_items = [
        {
            "Name": item.product.name,
            "Quantity": item.quantity,
            "UnitPrice": f"{item.price:.2f}",  # use the 'price' field on OrderItem
        }
        for item in order.order_items.all()  # related_name='order_items'
    ]

    params["CartItems"] = json.dumps(cart_items, separators=(",", ":"))

    params["Signature"] = _generate_signature(params)

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
    data = request.POST
    tx = data.get("OrderId")
    status = data.get("Status")  # check exact field name in your callback docs

    try:
        order = Order.objects.get(transaction_id=tx)
        order.payment_status = "Success" if status == "OK" else "Failed"
        if status == "OK":
            order.is_paid = True
        order.save()
    except Order.DoesNotExist:
        # ignore unknown callbacks
        pass

    return HttpResponse("OK")


def payment_result(request):
    """
    The customer’s browser lands here (URL has ?Status=OK or FAILED).
    We simply show them a success/fail page.
    """
    status = request.GET.get("Status", "")
    return render(request, "store/payment_result.html", {"status": status})
