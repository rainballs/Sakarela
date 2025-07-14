from django.contrib import admin

# Register your models here.
from .models import Product, Nutrition, Recipe


class NutritionInline(admin.StackedInline):
    model = Nutrition
    can_delete = False


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    inlines = [NutritionInline]
    list_display   = ('title', 'store_product')
    raw_id_fields  = ('store_product',)


@admin.register(Recipe)
class RecipeAdmin(admin.ModelAdmin):
    list_display = ('title', 'cook_time', 'created_at')
    search_fields = ('title', 'ingredients')
