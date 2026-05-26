from decimal import Decimal

from django.db import models
from django.urls import reverse
from django.contrib.auth.models import User


class Product(models.Model):
	name = models.CharField(max_length=120)
	description = models.TextField(blank=True)
	price = models.DecimalField(max_digits=10, decimal_places=2)
	in_stock = models.BooleanField(default=True)
	created_at = models.DateTimeField(auto_now_add=True)

	def __str__(self):
		return self.name

	def get_absolute_url(self):
		return reverse("product_detail", kwargs={"pk": self.pk})


class Order(models.Model):
	STATUS_PURCHASED = "purchased"
	STATUS_CHOICES = [
		(STATUS_PURCHASED, "Purchased"),
	]

	customer = models.ForeignKey(User, on_delete=models.CASCADE, related_name="orders", null=True, blank=True)
	customer_name = models.CharField(max_length=120)
	products = models.ManyToManyField(Product, related_name="orders", blank=False)
	billing_name = models.CharField(max_length=120, blank=True, default="")
	billing_email = models.EmailField(blank=True, default="")
	billing_address = models.CharField(max_length=255, blank=True, default="")
	billing_city = models.CharField(max_length=100, blank=True, default="")
	billing_state = models.CharField(max_length=2, blank=True, default="")
	billing_zip = models.CharField(max_length=12, blank=True, default="")
	status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PURCHASED)
	created_at = models.DateTimeField(auto_now_add=True)

	def __str__(self):
		return f"Order #{self.pk} for {self.customer_name}"

	def get_absolute_url(self):
		return reverse("order_detail", kwargs={"pk": self.pk})

	@property
	def total(self):
		return sum((product.price for product in self.products.all()), Decimal("0.00"))
