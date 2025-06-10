from django.db import models


# Create your models here.
class Product(models.Model):
    title = models.CharField(max_length=100)
    description = models.TextField()
    image = models.ImageField(upload_to='products/')
    badge = models.ImageField(upload_to='badges/', blank=True, null=True)

    ingredients = models.TextField()
    storage = models.CharField(max_length=255)

    # nutrition = models.TextField()

    def __str__(self):
        return self.title


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
    title = models.CharField(max_length=200)
    image = models.ImageField(upload_to='recipes/')
    ingredients = models.TextField(help_text="List of ingredients, one per line")
    cook_time = models.PositiveIntegerField(help_text="Time in minutes")
    steps = models.TextField(help_text="Step-by-step instructions")

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title
