from django.contrib import admin

# Register your models here.
from .models import Product, Nutrition, Recipe


class NutritionInline(admin.StackedInline):
    model = Nutrition
    can_delete = False


class ProductAdmin(admin.ModelAdmin):
    inlines = [NutritionInline]


admin.site.register(Product, ProductAdmin)


@admin.register(Recipe)
class RecipeAdmin(admin.ModelAdmin):
    list_display = ('title', 'cook_time', 'created_at')
    search_fields = ('title', 'ingredients')
