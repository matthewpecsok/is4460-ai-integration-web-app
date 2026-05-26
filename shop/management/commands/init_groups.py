from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType

from shop.models import Product, Order


class Command(BaseCommand):
	help = "Initialize user groups with appropriate permissions"

	def handle(self, *args, **options):
		# Create groups
		customer_group, customer_created = Group.objects.get_or_create(name="customer")
		employee_group, employee_created = Group.objects.get_or_create(name="employee")

		self.stdout.write(
			self.style.SUCCESS(f"Customer group {'created' if customer_created else 'already exists'}")
		)
		self.stdout.write(
			self.style.SUCCESS(f"Employee group {'created' if employee_created else 'already exists'}")
		)

		# Get content types
		product_ct = ContentType.objects.get_for_model(Product)
		order_ct = ContentType.objects.get_for_model(Order)

		# Get permissions
		product_permissions = Permission.objects.filter(content_type=product_ct)
		order_permissions = Permission.objects.filter(content_type=order_ct)

		# Assign permissions to customer group
		customer_group.permissions.set([
			Permission.objects.get(content_type=order_ct, codename="add_order"),
			Permission.objects.get(content_type=order_ct, codename="view_order"),
		])

		# Assign permissions to employee group
		employee_permissions = []
		for codename in ["add_product", "change_product", "delete_product", "view_product",
						"add_order", "change_order", "delete_order", "view_order"]:
			try:
				if codename.startswith("product"):
					employee_permissions.append(Permission.objects.get(content_type=product_ct, codename=codename))
				else:
					employee_permissions.append(Permission.objects.get(content_type=order_ct, codename=codename))
			except Permission.DoesNotExist:
				pass

		employee_group.permissions.set(employee_permissions)

		self.stdout.write(self.style.SUCCESS("Groups and permissions initialized successfully"))
