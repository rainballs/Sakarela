from django.conf import settings
from django.conf.urls.static import static
from django.urls import path

from . import views

urlpatterns = [
                  path('', views.home, name='home'),
                  path('about/', views.about, name='about'),
                  path('products/', views.products, name='products'),
                  path('contact/', views.contact_view, name='contact'),
                  path('products/<int:pk>/', views.product_detail, name='product_detail'),
                  path('recipes/', views.recipe_list, name='recipe_list'),
                  path('recipes/<int:pk>/', views.recipe_detail, name='recipe_detail'),
              ] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
