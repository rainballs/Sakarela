from django.contrib import admin

from .models import Product, Nutrition, Order, OrderItem, Category, Brand, PackagingOption, Store
from django import forms
from django.templatetags.static import static
from django.utils.html import format_html


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

    # Don’t specify `fields` at all – let Django choose
    # just make the weight fields read-only so we can see them
    readonly_fields = ("unit_weight_g", "line_weight_kg")


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    # what you see in the list page
    list_display = (
        "id",
        "full_name",
        "last_name",
        "email",
        "city",
        "address1",
        "payment_method",
        "payment_status",
        "total",
        "total_weight_kg",  # show total weight here
        "created_at",
    )

    list_filter = ("payment_method", "payment_status", "created_at")
    search_fields = (
        "full_name",
        "last_name",
        "email",
        "city",
        "address1",
        "company_name",
        "company_bulstat",
    )

    inlines = [OrderItemInline]

    # keep fieldsets *simple* and with no duplicates
    fieldsets = (
        ("Клиент", {
            "fields": ("full_name", "last_name", "email", "phone")
        }),
        ("Адрес за доставка", {
            "fields": ("country", "state", "city", "address1", "address2", "post_code")
        }),
        ("Фактура към фирма", {
            "fields": (
                "is_company",
                "company_name",
                "company_mol",
                "company_bulstat",
                "company_vat_number",
                "company_address",
            )
        }),
        ("Поръчка и тегло", {
            "fields": ("total", "total_weight_kg")
        }),
        ("Плащане и доставка", {
            "fields": (
                "payment_method",
                "payment_status",
                "shipping_cost",
                "delivery_status",
                "delivery_tracking_number",
                "econt_shipment_num",
                "label_url",
                "transaction_id",
            )
        }),
        ("Системни", {
            "fields": ("created_at", "updated_at"),
        }),
    )

    # these fields are calculated / system-managed
    readonly_fields = ("total", "total_weight_kg", "created_at", "updated_at")


class StoreAdminForm(forms.ModelForm):
    class Meta:
        model = Store
        fields = "__all__"

    class Media:
        js = ("admin/map_picker.js",)  # your existing JS
        css = {"all": ("admin/map_picker.css",)}  # optional


@admin.register(Store)
class StoreAdmin(admin.ModelAdmin):
    form = StoreAdminForm
    readonly_fields = ("map_picker",)

    fieldsets = (
        (None, {"fields": ("name", "city", "address", "map_url", "working_hours", "logo", "show_on_map")}),
        ("Координати за картата", {"fields": ("map_x_pct", "map_y_pct", "map_picker")}),
    )

    def map_picker(self, obj=None):
        url = static("map/map_sakarela.png")  # reuse the same image
        return format_html(
            """
            <div id="adminMapPicker"
                 style="max-width:700px;position:relative;aspect-ratio:1600/900;
                        background:url('{}') center/contain no-repeat;
                        border:1px solid #eee;border-radius:12px;"></div>
            <p style="color:#666">Кликнете върху картата, за да зададете <b>map_x_pct</b> и <b>map_y_pct</b>.</p>
            """,
            url
        )

    map_picker.short_description = "Избор от карта"


admin.site.register(Product, ProductAdmin)
