from django.contrib import admin

# Register your models here.
from .models import Product, Nutrition, Recipe, RecipeStep, RecipeIngredient


class NutritionInline(admin.StackedInline):
    model = Nutrition
    can_delete = False


class RecipeIngredientInline(admin.TabularInline):
    model = RecipeIngredient
    extra = 1
    fields = ('product', 'amount', 'order')


class RecipeStepInline(admin.TabularInline):
    model = RecipeStep
    extra = 1
    fields = ('step_name', 'step_content', 'order')


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    inlines = [NutritionInline]
    list_display   = ('title', 'store_product')
    raw_id_fields  = ('store_product',)


@admin.register(Recipe)
class RecipeAdmin(admin.ModelAdmin):
    list_display = ('title', 'cook_time', 'servings', 'appliance', 'created_at')
    search_fields = ('title', 'short_description')
    inlines = [RecipeIngredientInline, RecipeStepInline]
