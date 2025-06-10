from django.shortcuts import get_object_or_404

from .models import Product


def cart_items_context(request):
    cart = request.session.get('cart', {})
    cart_items = []
    total = 0

    for product_id, qty in cart.items():
        product = get_object_or_404(Product, id=product_id)
        price = product.sale_price if product.is_on_sale else product.price
        line_total = price * qty
        total += line_total

        cart_items.append({
            'product': product,
            'qty': qty,
            'line_total': line_total
        })

    return {
        'cart_items': cart_items,
        'cart_total': total
    }
