from django.urls import path
from django.views.generic import TemplateView

from . import views

app_name = 'store'

urlpatterns = [
    path('', views.store_home, name='store_home'),
    path('product/<int:pk>/', views.product_detail, name='product_detail'),

    path('where-to-buy/', views.where_to_buy, name='where_to_buy'),

    path('cart/', views.view_cart, name='cart'),
    path('cart/add/<int:product_id>/', views.add_to_cart, name='add_to_cart'),
    path('cart/remove/<int:product_id>/', views.remove_from_cart, name='remove_from_cart'),
    path('cart/update/<int:product_id>/<str:action>/', views.update_cart_quantity, name='update_cart_quantity'),

    path('payment/initiate/<int:order_id>/', views.mypos_payment, name='mypos_payment'),
    path('payment/callback/', views.payment_callback, name='payment_callback'),
    path('payment/result/', views.payment_result, name='payment_result'),

    path('order/start/', views.order_start, name='order_start'),
    path('order/', views.order_info, name='order_info'),
    path('order-summary/<int:pk>/', views.order_summary, name='order_summary'),
    path('card-payment/', TemplateView.as_view(template_name="store/card_payment.html"), name='card_payment'),
    # path('order/<int:order_id>/confirm/', views.confirm_order, name='confirm_order'),
    path("econt-cities/", views.econt_city_suggestions, name="econt_cities"),
    # path("shipping/econt/<int:order_id>/", views.econt_redirect, name="econt_redirect"),
    # Test
    # path("test-econt/", views.test_econt_label, name="test_econt"),

    # Use order_summary as the detail view for order confirmation
    # path('order/<int:order_id>/', views.order_summary, name='order_detail'),

]
