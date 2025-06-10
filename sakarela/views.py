# Create your views here.
from django.core.mail import send_mail
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
    products = Product.objects.all()
    return render(request, 'products.html', {'products': products})


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

            send_mail(subject, message, from_email, recipient_list)
            success = True
            form = ContactForm()  # Reset form

    return render(request, 'contact.html', {'form': form, 'success': success})


def product_detail(request, pk):
    product = get_object_or_404(Product, pk=pk)
    other_products = Product.objects.exclude(pk=pk)[:4]  # Adjust limit as needed
    return render(request, 'product_detail.html', {
        'product': product,
        'other_products': other_products,
    })


def recipe_list(request):
    recipes = Recipe.objects.order_by('-created_at')
    return render(request, 'recipe_list.html', {'recipes': recipes})


def recipe_detail(request, pk):
    recipe = get_object_or_404(Recipe, pk=pk)
    return render(request, 'recipe_detail.html', {'recipe': recipe})
