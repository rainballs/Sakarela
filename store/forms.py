from django import forms

from .models import Order


class OrderForm(forms.ModelForm):
    payment_method = forms.ChoiceField(
        label="Начин на плащане",
        choices=Order.PAYMENT_CHOICES,
        widget=forms.RadioSelect,
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
        widgets = {
            'payment_method': forms.RadioSelect(choices=Order.PAYMENT_CHOICES)
        }
