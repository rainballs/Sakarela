from django.db import models
from django.urls import reverse
from store.models import Product as StoreProduct


# Create your models here.
class Product(models.Model):
    PRODUCT_TYPES = [
        ('kashkaval', 'Кашкавал'),
        ('sirene', 'Сирене'),
        ('yogurt', 'Йогурт'),
        ('milk', 'Мляко'),
        ('other', 'Други'),
    ]
    
    title = models.CharField(max_length=100)
    description = models.TextField()
    image = models.ImageField(upload_to='products/')
    badge = models.ImageField(upload_to='badges/', blank=True, null=True)
    type = models.CharField(max_length=20, choices=PRODUCT_TYPES, default='other', help_text="Тип на продукта")

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
    short_description = models.TextField(max_length=300, help_text="Brief description of the recipe")
    cook_time = models.PositiveIntegerField(help_text="Time in minutes")
    servings = models.PositiveIntegerField(default=4, help_text="Number of servings")
    appliance = models.CharField(max_length=200, help_text="Cooking equipment/appliances needed")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title


class RecipeIngredient(models.Model):
    recipe = models.ForeignKey(
        Recipe,
        on_delete=models.CASCADE,
        related_name='recipe_ingredients',
        help_text="The recipe this ingredient belongs to"
    )
    product = models.CharField(max_length=200, help_text="Name of the ingredient/product")
    amount = models.CharField(max_length=100, help_text="Amount/quantity of the ingredient")
    order = models.PositiveIntegerField(default=0, help_text="Order of the ingredient (1, 2, 3, etc.)")
    
    class Meta:
        ordering = ['order']
    
    def __str__(self):
        return f"{self.recipe.title} - {self.product}"


class RecipeStep(models.Model):
    recipe = models.ForeignKey(
        Recipe,
        on_delete=models.CASCADE,
        related_name='recipe_steps',
        help_text="The recipe this step belongs to"
    )
    step_name = models.CharField(max_length=100, help_text="Example: Step 1, Step 2, etc.")
    step_content = models.TextField(help_text="The content/instructions for this step")
    order = models.PositiveIntegerField(default=0, help_text="Order of the step (1, 2, 3, etc.)")
    
    class Meta:
        ordering = ['order']
    
    def __str__(self):
        return f"{self.recipe.title} - {self.step_name}"
