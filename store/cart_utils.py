# store/cart_utils.py
from decimal import Decimal
from typing import List, Tuple
from store.models import Product, PackagingOption


def get_session_cart(request) -> dict:
    return request.session.get("cart", {}) or {}


def set_session_cart(request, cart_dict: dict) -> None:
    request.session["cart"] = cart_dict
    request.session.modified = True


def cart_items_and_total(request) -> Tuple[list, Decimal]:
    """
    Returns (items, total) from session cart.
    items: [{product, packaging, quantity, price, subtotal}]
    """
    cart = get_session_cart(request)
    items: List[dict] = []
    total = Decimal("0.00")

    for cart_key, qty in cart.items():
        try:
            product_id, packaging_id = cart_key.split('_')
            product = Product.objects.get(pk=product_id)
            packaging = PackagingOption.objects.get(pk=packaging_id)
            price = packaging.current_price  # Decimal
            subtotal = price * int(qty)
            items.append({
                "product": product,
                "packaging": packaging,
                "quantity": int(qty),
                "price": price,
                "subtotal": subtotal,
            })
            total += subtotal
        except (Product.DoesNotExist, PackagingOption.DoesNotExist, ValueError):
            continue
    return items, total


def cart_is_empty(request) -> bool:
    cart = get_session_cart(request)
    return not any(True for _ in cart.items())
