from django import forms


class ContactForm(forms.Form):
    name = forms.CharField(
        label="Име, Фамилия",
        max_length=100,
        widget=forms.TextInput(attrs={'placeholder': 'Вашето име', 'required': True, 'autocomplete': 'name'})
    )
    email = forms.EmailField(
        label="E-mail",
        widget=forms.EmailInput(attrs={'placeholder': 'Вашият email', 'required': True, 'autocomplete': 'email'})
    )
    message = forms.CharField(
        label="Съобщение",
        widget=forms.Textarea(attrs={'placeholder': 'Вашето съобщение', 'required': True})
    )
