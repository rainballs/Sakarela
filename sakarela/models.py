from django.db import models
from django.urls import reverse
from store.models import Product as StoreProduct


# Create your models here.
class Product(models.Model):
    title = models.CharField(max_length=100)
    description = models.TextField()
    image = models.ImageField(upload_to='products/')
    badge = models.ImageField(upload_to='badges/', blank=True, null=True)

    ingredients = models.TextField()
    storage = models.CharField(max_length=255)

    # nutrition = models.TextField()

    store_product = models.OneToOneField(
        StoreProduct,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='main_product',
        help_text="If set, shows a ‘Buy online’ button"
    )
    
    def __str__(self):
        return self.title
    
    def get_store_url(self):
        if not self.store_product:
            return None
        # assumes you have a URL pattern named 'store:product_detail'
        return reverse('store:product_detail', args=[self.store_product.pk])


class Nutrition(models.Model):
    product = models.OneToOneField(Product, on_delete=models.CASCADE, related_name='nutrition')
    energy = models.CharField(max_length=50, help_text="Example: 352kcal / 1462kJ")
    fat = models.DecimalField(max_digits=5, decimal_places=1)
    saturated_fat = models.DecimalField(max_digits=5, decimal_places=1)
    carbohydrates = models.DecimalField(max_digits=5, decimal_places=1)
    sugars = models.DecimalField(max_digits=5, decimal_places=1)
    protein = models.DecimalField(max_digits=5, decimal_places=1)
    salt = models.DecimalField(max_digits=5, decimal_places=1)

    def __str__(self):
        return f"Nutrition for {self.product.title}"


class Recipe(models.Model):
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='recipes',
        help_text="The product this recipe is for",
        default=1,
    )
    title = models.CharField(max_length=200)
    image = models.ImageField(upload_to='recipes/')
    ingredients = models.TextField(help_text="List of ingredients, one per line")
    cook_time = models.PositiveIntegerField(help_text="Time in minutes")
    steps = models.TextField(help_text="Step-by-step instructions")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title
