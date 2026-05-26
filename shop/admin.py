from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User, Group

from .models import Order, Product


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
	list_display = ("name", "price", "in_stock", "created_at")
	search_fields = ("name",)


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
	list_display = ("id", "customer_name", "customer", "status", "created_at")
	search_fields = ("customer_name", "customer__username", "billing_email")
	list_filter = ("status", "created_at")
	filter_horizontal = ("products",)


class CustomUserAdmin(BaseUserAdmin):
	"""Enhanced User admin to manage groups"""
	list_display = ("username", "email", "first_name", "last_name", "is_staff", "get_groups")
	
	def get_groups(self, obj):
		return ", ".join([group.name for group in obj.groups.all()])
	get_groups.short_description = "Groups"

	def get_fieldsets(self, request, obj=None):
		fieldsets = super().get_fieldsets(request, obj)
		if obj:  # Editing an existing user
			fieldsets = list(fieldsets)
			for i, (section_name, section) in enumerate(fieldsets):
				if section_name == "Permissions":
					fields = list(section["fields"])
					if "groups" not in fields:
						fields.append("groups")
					fieldsets[i] = (section_name, {**section, "fields": fields})
					break
		return fieldsets


# Unregister the default User admin if it exists
try:
	admin.site.unregister(User)
except admin.sites.NotRegistered:
	pass

# Register the custom User admin
admin.site.register(User, CustomUserAdmin)
