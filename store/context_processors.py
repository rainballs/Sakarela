from store.models import Product, PackagingOption

def cart_items_context(request):
    cart = request.session.get('cart', {})
    cart_items = []
    total = 0

    for cart_key, qty in cart.items():
        try:
            product_id, packaging_id = cart_key.split('_')
            product = Product.objects.get(pk=product_id)
            packaging = PackagingOption.objects.get(pk=packaging_id)
            # Use packaging's current_price property for price
            price = packaging.current_price
            line_total = price * qty
            total += line_total
            cart_items.append({
                'product': product,
                'packaging': packaging,
                'quantity': qty,
                'line_total': line_total,
                'price': price
            })
        except (Product.DoesNotExist, PackagingOption.DoesNotExist, ValueError):
            continue

    return {
        'cart_items': cart_items,
        'cart_total': total
    }
