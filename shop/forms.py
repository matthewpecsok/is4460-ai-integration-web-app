from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm

from .models import Order, Product


class OrderForm(forms.ModelForm):
    products = forms.ModelMultipleChoiceField(
        queryset=Product.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        required=True,
    )

    class Meta:
        model = Order
        fields = [
            "customer_name",
            "products",
            "billing_name",
            "billing_email",
            "billing_address",
            "billing_city",
            "billing_state",
            "billing_zip",
        ]


class CustomerCheckoutForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.required = True

    class Meta:
        model = Order
        fields = [
            "billing_name",
            "billing_email",
            "billing_address",
            "billing_city",
            "billing_state",
            "billing_zip",
        ]
        labels = {
            "billing_name": "Name on billing account",
            "billing_email": "Email for receipt",
            "billing_address": "Street address",
            "billing_city": "City",
            "billing_state": "State",
            "billing_zip": "ZIP code",
        }
        widgets = {
            "billing_name": forms.TextInput(attrs={"autocomplete": "name"}),
            "billing_email": forms.EmailInput(attrs={"autocomplete": "email"}),
            "billing_address": forms.TextInput(attrs={"autocomplete": "billing street-address"}),
            "billing_city": forms.TextInput(attrs={"autocomplete": "billing address-level2"}),
            "billing_state": forms.TextInput(attrs={"autocomplete": "billing address-level1", "maxlength": "2"}),
            "billing_zip": forms.TextInput(attrs={"autocomplete": "billing postal-code"}),
        }


class CustomerOrderForm(CustomerCheckoutForm):
    products = forms.ModelMultipleChoiceField(
        queryset=Product.objects.filter(in_stock=True).order_by("name"),
        widget=forms.CheckboxSelectMultiple,
        required=True,
    )

    class Meta(CustomerCheckoutForm.Meta):
        fields = ["products", *CustomerCheckoutForm.Meta.fields]
        labels = {
            **CustomerCheckoutForm.Meta.labels,
            "products": "Products",
        }


class CustomerRegistrationForm(UserCreationForm):
    email = forms.EmailField(required=True)
    first_name = forms.CharField(max_length=30, required=True)
    last_name = forms.CharField(max_length=30, required=True)

    class Meta:
        model = User
        fields = ["username", "email", "first_name", "last_name", "password1", "password2"]

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        user.first_name = self.cleaned_data["first_name"]
        user.last_name = self.cleaned_data["last_name"]
        if commit:
            user.save()
            # Assign user to customer group
            from django.contrib.auth.models import Group
            customer_group, created = Group.objects.get_or_create(name="customer")
            user.groups.add(customer_group)
        return user
