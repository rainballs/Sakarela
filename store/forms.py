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

    # ↓↓↓ NEW: phone field with pattern and mobile-friendly input ↓↓↓
    phone = forms.CharField(  # ← NEW
        label="Телефон",  # ← NEW
        required=False,  # keep False if model has blank=True/null=True; make True after backfill  # ← NEW
        widget=forms.TextInput(attrs={  # ← NEW
            'placeholder': 'Телефон (напр. +359888123456 или 0888123456)',  # ← NEW
            'class': 'form-control',  # ← NEW
            'inputmode': 'tel',  # ← NEW (mobile keypad)
            'autocomplete': 'tel',  # ← NEW
            'maxlength': '16',  # ← NEW
            # Accepts +359XXXXXXXXX or 0XXXXXXXXX (Bulgarian-style)
            'pattern': r'^(?:\+359\d{9}|0\d{9})$',  # ← NEW (mirrors model RegexValidator)
            'title': 'Въведете валиден телефон: +359XXXXXXXXX или 0XXXXXXXXX'  # ← NEW
        })
    )  # ← NEW
    # ↑↑↑ NEW ↑↑↑

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
    # ---------- NEW: фирма / фактура полета ----------

    is_company = forms.BooleanField(
        label="Желая фактура към фирма",
        required=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'company-toggle'
        })
    )

    company_name = forms.CharField(
        label="Фирма",
        required=False,
        widget=forms.TextInput(attrs={
            'placeholder': 'ФИРМА....',
            'class': 'form-control'
        })
    )

    company_mol = forms.CharField(
        label="МОЛ",
        required=False,
        widget=forms.TextInput(attrs={
            'placeholder': 'МОЛ....',
            'class': 'form-control'
        })
    )

    company_bulstat = forms.CharField(
        label="БУЛСТАТ / ЕИК",
        required=False,
        widget=forms.TextInput(attrs={
            'placeholder': 'БУЛСТАТ / ЕИК....',
            'class': 'form-control'
        })
    )
    company_vat_number = forms.CharField(
        label="ДДС номер",
        required=False,
        widget=forms.TextInput(attrs={
            'placeholder': 'ДДС НОМЕР....',
            'class': 'form-control'
        })
    )

    company_address = forms.CharField(
        label="Адрес за фактуриране",
        required=False,
        widget=forms.TextInput(attrs={
            'placeholder': 'АДРЕС ЗА ФАКТУРИРАНЕ....',
            'class': 'form-control'
        })
    )

    class Meta:
        model = Order
        fields = [
            'full_name', 'last_name', 'email', 'phone',
            'country', 'state', 'city',
            'address1', 'address2', 'post_code',
            'payment_method',

            # 👇 NEW FIELDS MUST BE HERE
            'is_company',
            'company_name',
            'company_mol',
            'company_bulstat',
            'company_address',
        ]

    def clean(self):
        """
        Make company fields required only when 'is_company' is checked.
        """
        cleaned_data = super().clean()
        is_company = cleaned_data.get("is_company")

        if is_company:
            required_fields = {
                "company_name": "Фирма",
                "company_mol": "МОЛ",
                "company_bulstat": "БУЛСТАТ / ЕИК",
                "company_address": "Адрес за фактуриране",
            }
            for field_name, label in required_fields.items():
                if not cleaned_data.get(field_name):
                    self.add_error(field_name, f"{label} е задължително поле.")
        return cleaned_data
