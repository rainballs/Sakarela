from django import forms

from .models import Order


class OrderForm(forms.ModelForm):
    full_name = forms.CharField(
        label="Име",
        widget=forms.TextInput(attrs={
            'placeholder': 'ВЪВЕДИ ИМЕ....',
            'class': 'form-control'
        })
    )
    
    last_name = forms.CharField(
        label="Фамилия",
        widget=forms.TextInput(attrs={
            'placeholder': 'ФАМИЛИЯ....',
            'class': 'form-control'
        })
    )
    
    email = forms.EmailField(
        label="Имейл адрес",
        widget=forms.EmailInput(attrs={
            'placeholder': 'ИМЕЙЛ АДРЕС....',
            'class': 'form-control'
        })
    )
    
    country = forms.CharField(
        label="Държава",
        widget=forms.TextInput(attrs={
            'placeholder': 'ДЪРЖАВА....',
            'class': 'form-control'
        })
    )
    
    state = forms.CharField(
        label="Област",
        widget=forms.TextInput(attrs={
            'placeholder': 'ОБЛАСТ....',
            'class': 'form-control'
        })
    )
    
    city = forms.CharField(
        label="Град",
        widget=forms.TextInput(attrs={
            'placeholder': 'ГРАД....',
            'class': 'form-control'
        })
    )
    
    address1 = forms.CharField(
        label="Адрес",
        widget=forms.TextInput(attrs={
            'placeholder': 'АДРЕС....',
            'class': 'form-control'
        })
    )
    
    address2 = forms.CharField(
        label="Допълнителен адрес",
        required=False,
        widget=forms.TextInput(attrs={
            'placeholder': 'ДОПЪЛНИТЕЛЕН АДРЕС....',
            'class': 'form-control'
        })
    )
    
    post_code = forms.CharField(
        label="Пощенски код",
        widget=forms.TextInput(attrs={
            'placeholder': 'ПОЩЕНСКИ КОД....',
            'class': 'form-control'
        })
    )
    
    payment_method = forms.ChoiceField(
        label="Начин на плащане",
        choices=Order.PAYMENT_CHOICES,
        widget=forms.RadioSelect(attrs={
            'class': 'payment-method-radio'
        }),
        required=True
    )

    class Meta:
        model = Order
        fields = [
            'full_name', 'last_name', 'email',
            'country', 'state', 'city',
            'address1', 'address2', 'post_code',
            'payment_method'
        ]
