from django.contrib import admin

from .models import Product, Nutrition, Order, OrderItem, Category, Brand, PackagingOption


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)


@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)


class NutritionInline(admin.StackedInline):
    model = Nutrition
    extra = 0


class PackagingInline(admin.TabularInline):
    model = PackagingOption
    extra = 1


# Register your models here.
class ProductAdmin(admin.ModelAdmin):
    list_display = ['name', 'price', 'sale_price', 'is_on_sale', 'is_in_stock']
    search_fields = ['name']
    list_filter = ['is_on_sale', 'is_in_stock']
    list_filter += ['category', 'brand']
    inlines = [NutritionInline, PackagingInline]


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'full_name', 'last_name', 'email',
        'country', 'city', 'address1',
        'payment_method', 'created_at', 'total',
    )
    readonly_fields = (
        'created_at', 'updated_at', 'total',
    )
    inlines = [OrderItemInline]
    list_filter = ('payment_method', 'created_at')
    search_fields = ('full_name', 'email', 'post_code')
    ordering = ('-created_at',)

    fieldsets = (
        ("Customer data", {'fields': ('full_name', 'last_name', 'email')}),
        ("Address", {'fields': ('country', 'state', 'city', 'address1', 'address2', 'post_code')}),
        ("Payment", {'fields': ('payment_method',)}),
        ("System info", {'fields': ('created_at', 'updated_at', 'total')}),
    )


admin.site.register(Product, ProductAdmin)
