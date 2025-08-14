# Create your views here.
from django.conf import settings
from django.core.mail import EmailMessage
from django.shortcuts import get_object_or_404
from django.shortcuts import render

from sakarela.models import Product, Recipe
from .forms import ContactForm


def home(request):
    products = Product.objects.all().order_by('-id')  # Show latest products first
    return render(request, 'home.html', {'products': products})


def about(request):
    return render(request, 'about.html')


def products(request):
    # Get the type filter from URL parameters
    product_type = request.GET.get('type', '')
    
    # Filter products by type if specified
    if product_type:
        products = Product.objects.filter(type=product_type).order_by('title')
    else:
        products = Product.objects.all().order_by('type', 'title')
    
    # Get all available product types for the filter dropdown
    product_types = Product.PRODUCT_TYPES
    
    return render(request, 'products.html', {
        'products': products,
        'product_types': product_types,
        'selected_type': product_type
    })


def contact_view(request):
    form = ContactForm()
    success = False

    if request.method == 'POST':
        form = ContactForm(request.POST)
        if form.is_valid():
            subject = f"Съобщение от {form.cleaned_data['name']}"
            message = form.cleaned_data['message']
            from_email = form.cleaned_data['email']
            recipient_list = ['rainballs.niki@gmail.com']  # Your receiving email / Change for production in .env

            email = EmailMessage(
                subject=subject,
                body=message,
                from_email=settings.EMAIL_HOST_USER,
                to=recipient_list,
                reply_to=[form.cleaned_data['email']],
            )
            email.send(fail_silently=False)

            success = True
            form = ContactForm()
            # Reset form

    return render(request, 'contact.html', {'form': form, 'success': success})


def product_detail(request, pk):
    product = get_object_or_404(Product, pk=pk)
    other_products = Product.objects.exclude(pk=pk)[:4]
    # Grab only recipes for this product
    recipes = product.recipes.all()
    return render(request, 'product_detail.html', {
        'product': product,
        'other_products': other_products,
        'recipes': recipes,
    })


def recipe_list(request):
    # Get products that have recipes
    products_with_recipes = Product.objects.filter(recipes__isnull=False).distinct().prefetch_related('recipes')
    return render(request, 'recipe_list.html', {'products_with_recipes': products_with_recipes})


def recipe_detail(request, pk):
    recipe = get_object_or_404(Recipe, pk=pk)
    other_recipes = Recipe.objects.exclude(pk=pk).order_by('?')[:4]  # Random 4 other recipes
    return render(request, 'recipe_detail.html', {
        'recipe': recipe,
        'other_recipes': other_recipes
    })
