import base64
import json
from decimal import Decimal

from django.db import models
from django.db.models import F, Sum, ExpressionWrapper, DecimalField
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver


class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)

    class Meta:
        verbose_name_plural = "Categories"

    def __str__(self):
        return self.name


class Brand(models.Model):
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name


class Product(models.Model):
    name = models.CharField(max_length=255)
    image = models.ImageField(upload_to='store/products/')
    price = models.DecimalField(max_digits=10, decimal_places=2)
    sale_price = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    is_on_sale = models.BooleanField(default=False)
    is_in_stock = models.BooleanField(default=True)
    description = models.TextField()
    ingredients = models.TextField(blank=True)
    storage = models.CharField(max_length=255, blank=True)

    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='products'
    )
    brand = models.ForeignKey(
        Brand,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='products'
    )
    
    badge = models.CharField(max_length=100, blank=True, null=True, help_text="Label/Badge for the product (e.g., 'ОВЧЕ МЛЯКО', 'БДС', 'КОЗЕ МЛЯКО', 'КРАВЕ МЛЯКО', 'С ПОДПРАВКИ')")

    def __str__(self):
        return self.name


# store/models.py

class PackagingOption(models.Model):
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='packaging_options'
    )
    weight = models.FloatField(help_text="грамове")
    price = models.DecimalField(max_digits=10, decimal_places=2)
    sale_price = models.DecimalField(
        max_digits=10, decimal_places=2,
        blank=True, null=True,
        help_text="оставете празно, ако няма промо"
    )
    is_on_sale = models.BooleanField(
        default=False,
        help_text="Отбележете, за да активирате sale_price като текуща цена"
    )

    class Meta:
        unique_together = ('product', 'weight')
        ordering = ('weight',)

    def __str__(self):
        return f"{self.weight} g – {self.current_price} лв"

    @property
    def current_price(self):
        """
        Returns sale_price if is_on_sale, else regular price.
        """
        if self.is_on_sale and self.sale_price is not None:
            return self.sale_price
        return self.price


class Nutrition(models.Model):
    product = models.OneToOneField(Product, on_delete=models.CASCADE, related_name='nutrition')
    energy = models.CharField(max_length=50, help_text="Пример: 352kcal / 1462kJ")
    fat = models.DecimalField(max_digits=5, decimal_places=1)
    saturated_fat = models.DecimalField(max_digits=5, decimal_places=1)
    carbohydrates = models.DecimalField(max_digits=5, decimal_places=1)
    sugars = models.DecimalField(max_digits=5, decimal_places=1)
    protein = models.DecimalField(max_digits=5, decimal_places=1)
    salt = models.DecimalField(max_digits=5, decimal_places=1)

    def __str__(self):
        return f"Nutrition for {self.product.name}"


class Order(models.Model):
    PAYMENT_CHOICES = [
        ('cash', 'Наложен платеж'),
        ('card', 'Карта (онлайн)'),
    ]

    PAYMENT_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('paid', 'Paid'),
        ('failed', 'Failed'),
    ]

    full_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    email = models.EmailField()
    country = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    city = models.CharField(max_length=100)
    address1 = models.CharField(max_length=255)
    address2 = models.CharField(max_length=255, blank=True)
    post_code = models.CharField(max_length=10)
    payment_method = models.CharField(max_length=10, choices=PAYMENT_CHOICES)
    payment_status = models.CharField(
        max_length=10,
        choices=PAYMENT_STATUS_CHOICES,
        default='pending'
    )
    total = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Computed sum of all order items."
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    PAYMENT_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('paid', 'Paid'),
        ('failed', 'Failed'),
    ]
    transaction_id = models.CharField(max_length=100, blank=True, null=True)
    shipping_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    delivery_status = models.CharField(max_length=50, blank=True, null=True)
    delivery_tracking_number = models.CharField(max_length=100, blank=True, null=True)
    econt_shipment_num = models.CharField(max_length=100, blank=True, null=True)
    label_url = models.URLField(blank=True, null=True)

    def update_total(self):
        agg = self.order_items.aggregate(
            total=Sum(
                ExpressionWrapper(
                    F('price') * F('quantity'),
                    output_field=DecimalField(max_digits=12, decimal_places=2)
                )
            )
        )
        # if there are no items, Sum returns None
        self.total = agg['total'] or Decimal('0.00')
        # only update the total column
        super().save(update_fields=['total'])

    def get_total(self):
        """Return the current total ensuring it's up to date."""
        self.update_total()
        return self.total

    def cart_items_json(self):
        """Return order items serialized as compact JSON."""
        items = [
            {
                "Name": oi.product.name,
                "Quantity": oi.quantity,
                "UnitPrice": f"{oi.price:.2f}",
            }
            for oi in self.order_items.select_related("product")
        ]
        return json.dumps(items, separators=(",", ":"))

    def cart_items_base64(self):
        """Return base64-encoded JSON of cart items for myPOS."""
        return base64.b64encode(self.cart_items_json().encode("utf-8")).decode()

    @property
    def is_paid(self):
        """Helper property to check if order is paid"""
        return self.payment_status == 'paid'

    def __str__(self):
        return f"{self.full_name} {self.last_name} - {self.created_at.strftime('%Y-%m-%d')}"


class OrderItem(models.Model):
    order = models.ForeignKey(Order, related_name='order_items', on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField()
    price = models.DecimalField(max_digits=10, decimal_places=2)  # snapshot of price at time of order

    def subtotal(self):
        return self.quantity * self.price

    def __str__(self):
        return f"{self.quantity} x {self.product.name}"


@receiver([post_save, post_delete], sender=OrderItem)
def _recalc_order_total_on_item_change(sender, instance, **kwargs):
    instance.order.update_total()
