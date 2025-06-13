from django.shortcuts import get_object_or_404
from .models import Product, PackagingOption


def cart_items_context(request):
    cart = request.session.get('cart', {})
    cart_items = []
    total = 0

    for cart_key, qty in cart.items():
        try:
            product_id, packaging_id = cart_key.split('_')
            product = get_object_or_404(Product, id=product_id)
            packaging = get_object_or_404(PackagingOption, id=packaging_id)
            price = packaging.sale_price if packaging.sale_price else packaging.price
            line_total = price * qty
            total += line_total
            cart_items.append({
                'product': product,
                'packaging': packaging,
                'quantity': qty,
                'line_total': line_total
            })
        except (Product.DoesNotExist, PackagingOption.DoesNotExist, ValueError):
            continue

    return {
        'cart_items': cart_items,
        'cart_total': total
    }
