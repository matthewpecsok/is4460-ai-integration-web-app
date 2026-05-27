import json
import logging

import pytest
from django.urls import reverse
from django.contrib.auth.models import User, Group
from django.test import Client, override_settings

from .gemini import get_product_recommendation
from .models import Order, Product


class ListLogHandler(logging.Handler):
	def __init__(self, level=logging.NOTSET):
		super().__init__(level)
		self.records = []

	def emit(self, record):
		self.records.append(record)


class FakeGeminiResponse:
	def __init__(self, payload):
		self.payload = payload

	def __enter__(self):
		return self

	def __exit__(self, exc_type, exc_value, traceback):
		return False

	def read(self):
		return json.dumps(self.payload).encode("utf-8")


@pytest.mark.django_db
def test_homepage_loads(client):
	response = client.get(reverse("home"))

	assert response.status_code == 200
	assert "shop/home.html" in [t.name for t in response.templates]


@pytest.mark.django_db
def test_homepage_lists_products(client, product):
	response = client.get(reverse("home"))

	assert response.status_code == 200
	assert b"Rose Bouquet" in response.content
	assert b"Buy Now" in response.content


@pytest.mark.django_db
def test_dashboard_loads(employee_client):
	response = employee_client.get(reverse("dashboard"))

	assert response.status_code == 200
	assert "shop/dashboard.html" in [t.name for t in response.templates]
	assert b"Internal Monitoring Dashboard" in response.content


@pytest.fixture
def product(db):
	return Product.objects.create(
		name="Rose Bouquet",
		description="A dozen red roses.",
		price="39.99",
		in_stock=True,
	)


@pytest.fixture
def employee_user(db):
	"""Create an authenticated employee user"""
	employee_group, _ = Group.objects.get_or_create(name="employee")
	user = User.objects.create_user(username="employee_test", password="pass123")
	user.groups.add(employee_group)
	return user


@pytest.fixture
def employee_client(employee_user):
	"""Create a client logged in as an employee"""
	client = Client()
	client.login(username="employee_test", password="pass123")
	return client


@pytest.fixture
def customer_user(db):
	"""Create an authenticated customer user"""
	customer_group, _ = Group.objects.get_or_create(name="customer")
	user = User.objects.create_user(username="customer_test", password="pass123")
	user.groups.add(customer_group)
	return user


@pytest.fixture
def customer_client(customer_user):
	"""Create a client logged in as a customer"""
	client = Client()
	client.login(username="customer_test", password="pass123")
	return client


@pytest.mark.django_db
def test_list_products(client, product):
	response = client.get(reverse("product_list"))

	assert response.status_code == 200
	assert b"Rose Bouquet" in response.content


@pytest.mark.django_db
def test_product_list_chatbot_displays_recommendation(client, product, monkeypatch):
	def fake_recommendation(question, products):
		products = list(products)
		assert question == "I need an anniversary gift"
		assert products[0].name == "Rose Bouquet"
		return "Rose Bouquet is a strong fit for an anniversary."

	monkeypatch.setattr("shop.views.get_product_recommendation", fake_recommendation)

	response = client.post(
		reverse("product_list"),
		{"recommendation_prompt": "I need an anniversary gift"},
	)

	assert response.status_code == 200
	assert b"I need an anniversary gift" in response.content
	assert b"Rose Bouquet is a strong fit" in response.content


@pytest.mark.django_db
@override_settings(GEMINI_API_KEY="test-key", GEMINI_MAX_OUTPUT_TOKENS=900)
def test_gemini_uses_configured_output_token_limit(product, monkeypatch):
	captured = {}

	def fake_urlopen(request, timeout):
		captured["payload"] = json.loads(request.data.decode("utf-8"))
		captured["timeout"] = timeout
		return FakeGeminiResponse(
			{
				"candidates": [
					{
						"content": {"parts": [{"text": "Rose Bouquet fits."}]},
						"finishReason": "STOP",
					}
				]
			}
		)

	monkeypatch.setattr("shop.gemini.urlopen", fake_urlopen)

	response = get_product_recommendation("I need something cheerful", [product])

	assert response == "Rose Bouquet fits."
	assert captured["timeout"] == 10
	assert captured["payload"]["generationConfig"]["maxOutputTokens"] == 900


@pytest.mark.django_db
def test_retrieve_product_detail(client, product):
	response = client.get(reverse("product_detail", kwargs={"pk": product.pk}))

	assert response.status_code == 200
	assert b"A dozen red roses." in response.content


@pytest.fixture
def products(db):
	product_one = Product.objects.create(
		name="Tulip Bunch",
		description="Mixed color tulips.",
		price="19.99",
		in_stock=True,
	)
	product_two = Product.objects.create(
		name="Lily Arrangement",
		description="White lilies in a glass vase.",
		price="29.99",
		in_stock=True,
	)
	return product_one, product_two


@pytest.fixture
def order(products):
	product_one, _ = products
	o = Order.objects.create(customer_name="Alice")
	o.products.add(product_one)
	return o


@pytest.mark.django_db
def test_create_order_with_multiple_products(employee_client, products):
	product_one, product_two = products
	response = employee_client.post(
		reverse("order_create"),
		{
			"customer_name": "Bob",
			"products": [product_one.pk, product_two.pk],
		},
	)

	assert response.status_code == 302
	assert Order.objects.count() == 1
	created_order = Order.objects.get(customer_name="Bob")
	assert created_order.products.count() == 2
	assert response["Location"] == reverse("order_detail", kwargs={"pk": created_order.pk})


@pytest.mark.django_db
def test_checkout_requires_login(client, product):
	response = client.get(reverse("checkout", kwargs={"pk": product.pk}))

	assert response.status_code == 302
	assert reverse("login") in response["Location"]
	assert "next=" in response["Location"]


@pytest.mark.django_db
def test_login_redirects_to_checkout_next_url(client, product):
	user = User.objects.create_user(username="checkout_user", password="pass123")
	next_url = reverse("checkout", kwargs={"pk": product.pk})

	response = client.post(
		f"{reverse('login')}?next={next_url}",
		{
			"username": "checkout_user",
			"password": "pass123",
		},
	)

	assert response.status_code == 302
	assert response["Location"] == next_url


@pytest.mark.django_db
def test_customer_checkout_creates_order_with_billing(customer_client, customer_user, product):
	response = customer_client.post(
		reverse("checkout", kwargs={"pk": product.pk}),
		{
			"billing_name": "Customer Test",
			"billing_email": "customer@example.com",
			"billing_address": "123 Flower Lane",
			"billing_city": "Bloomfield",
			"billing_state": "UT",
			"billing_zip": "84101",
		},
	)

	assert response.status_code == 302
	created_order = Order.objects.get()
	assert created_order.customer == customer_user
	assert created_order.customer_name == customer_user.username
	assert created_order.billing_email == "customer@example.com"
	assert list(created_order.products.values_list("pk", flat=True)) == [product.pk]
	assert response["Location"] == reverse("customer_order_detail", kwargs={"pk": created_order.pk})


@pytest.mark.django_db
def test_checkout_requires_billing_details(customer_client, product):
	response = customer_client.post(
		reverse("checkout", kwargs={"pk": product.pk}),
		{
			"billing_name": "",
			"billing_email": "",
			"billing_address": "",
			"billing_city": "",
			"billing_state": "",
			"billing_zip": "",
		},
	)

	assert response.status_code == 200
	assert Order.objects.count() == 0


@pytest.mark.django_db
def test_customer_order_history_only_shows_current_customer(customer_client, customer_user, products):
	product_one, product_two = products
	other_customer = User.objects.create_user(username="other_customer", password="pass123")
	customer_order = Order.objects.create(customer=customer_user, customer_name="Customer Test")
	customer_order.products.add(product_one)
	other_order = Order.objects.create(customer=other_customer, customer_name="Other Customer")
	other_order.products.add(product_two)

	response = customer_client.get(reverse("customer_order_history"))

	assert response.status_code == 200
	assert b"Tulip Bunch" in response.content
	assert b"Lily Arrangement" not in response.content


@pytest.mark.django_db
def test_customer_can_view_own_order_receipt(customer_client, customer_user, product):
	order = Order.objects.create(
		customer=customer_user,
		customer_name="Customer Test",
		billing_email="customer@example.com",
	)
	order.products.add(product)

	response = customer_client.get(reverse("customer_order_detail", kwargs={"pk": order.pk}))

	assert response.status_code == 200
	assert b"Receipt" in response.content
	assert b"Rose Bouquet" in response.content
	assert b"customer@example.com" in response.content


@pytest.mark.django_db
def test_customer_cannot_view_another_customers_order(customer_client, product):
	other_customer = User.objects.create_user(username="other_customer", password="pass123")
	order = Order.objects.create(customer=other_customer, customer_name="Other Customer")
	order.products.add(product)

	response = customer_client.get(reverse("customer_order_detail", kwargs={"pk": order.pk}))

	assert response.status_code == 404


@pytest.mark.django_db
def test_list_orders(employee_client, order):
	response = employee_client.get(reverse("order_list"))

	assert response.status_code == 200
	assert b"Alice" in response.content


@pytest.mark.django_db
def test_retrieve_order_detail(employee_client, order):
	response = employee_client.get(reverse("order_detail", kwargs={"pk": order.pk}))

	assert response.status_code == 200
	assert b"Tulip Bunch" in response.content


@pytest.mark.django_db
def test_update_order_products(employee_client, order, products):
	_, product_two = products
	response = employee_client.post(
		reverse("order_update", kwargs={"pk": order.pk}),
		{
			"customer_name": "Alice Cooper",
			"products": [product_two.pk],
		},
	)

	assert response.status_code == 302
	order.refresh_from_db()
	assert order.customer_name == "Alice Cooper"
	assert list(order.products.values_list("pk", flat=True)) == [product_two.pk]


@pytest.mark.django_db
def test_delete_order(employee_client, order):
	response = employee_client.post(reverse("order_delete", kwargs={"pk": order.pk}))

	assert response.status_code == 302
	assert response["Location"] == reverse("order_list")
	assert not Order.objects.filter(pk=order.pk).exists()


# Authentication Tests

@pytest.mark.django_db
def test_registration_page_loads(client):
	"""Test that the registration page loads successfully"""
	response = client.get(reverse("register"))

	assert response.status_code == 200
	assert "shop/register.html" in [t.name for t in response.templates]


@pytest.mark.django_db
def test_customer_registration_creates_user(client):
	"""Test that customer registration creates a user and assigns to customer group"""
	response = client.post(
		reverse("register"),
		{
			"username": "testcustomer",
			"email": "customer@example.com",
			"first_name": "Test",
			"last_name": "Customer",
			"password1": "securepass123!",
			"password2": "securepass123!",
		},
	)

	assert response.status_code == 302
	assert response["Location"] == reverse("login")
	
	# Verify user was created
	user = User.objects.get(username="testcustomer")
	assert user.email == "customer@example.com"
	assert user.first_name == "Test"
	assert user.last_name == "Customer"
	
	# Verify user is in customer group
	assert user.groups.filter(name="customer").exists()


@pytest.mark.django_db
def test_registration_with_duplicate_username_fails(client):
	"""Test that registration with existing username fails"""
	User.objects.create_user(username="taken", password="pass123")
	
	response = client.post(
		reverse("register"),
		{
			"username": "taken",
			"email": "newuser@example.com",
			"first_name": "New",
			"last_name": "User",
			"password1": "securepass123!",
			"password2": "securepass123!",
		},
	)

	assert response.status_code == 200
	assert b"already exists" in response.content or b"username" in response.content


@pytest.mark.django_db
def test_registration_with_mismatched_passwords_fails(client):
	"""Test that registration with mismatched passwords fails"""
	response = client.post(
		reverse("register"),
		{
			"username": "testuser",
			"email": "test@example.com",
			"first_name": "Test",
			"last_name": "User",
			"password1": "securepass123!",
			"password2": "differentpass123!",
		},
	)

	assert response.status_code == 200
	assert "password" in response.content.decode().lower()
	assert User.objects.filter(username="testuser").count() == 0


@pytest.mark.django_db
def test_login_page_loads(client):
	"""Test that the login page loads successfully"""
	response = client.get(reverse("login"))

	assert response.status_code == 200
	assert "shop/login.html" in [t.name for t in response.templates]


@pytest.mark.django_db
def test_customer_login_succeeds_and_redirects(client):
	"""Test that customer can login and is redirected to product_list"""
	customer_group, _ = Group.objects.get_or_create(name="customer")
	user = User.objects.create_user(username="customer1", password="pass123")
	user.groups.add(customer_group)
	
	response = client.post(
		reverse("login"),
		{
			"username": "customer1",
			"password": "pass123",
		},
	)

	assert response.status_code == 302
	assert response["Location"] == reverse("product_list")
	
	# Verify session was created
	assert client.session.get("_auth_user_id") == str(user.id)


@pytest.mark.django_db
def test_employee_login_succeeds_and_redirects_to_dashboard(client):
	"""Test that employee can login and is redirected to dashboard"""
	employee_group, _ = Group.objects.get_or_create(name="employee")
	user = User.objects.create_user(username="employee1", password="pass123")
	user.groups.add(employee_group)
	
	response = client.post(
		reverse("login"),
		{
			"username": "employee1",
			"password": "pass123",
		},
	)

	assert response.status_code == 302
	assert response["Location"] == reverse("dashboard")
	
	# Verify session was created
	assert client.session.get("_auth_user_id") == str(user.id)


@pytest.mark.django_db
def test_login_with_invalid_credentials_fails(client):
	"""Test that login with invalid credentials fails"""
	User.objects.create_user(username="validuser", password="correctpass")
	
	response = client.post(
		reverse("login"),
		{
			"username": "validuser",
			"password": "wrongpass",
		},
	)

	assert response.status_code == 200
	assert b"Invalid" in response.content or b"invalid" in response.content.decode()


@pytest.mark.django_db
def test_login_with_nonexistent_user_fails(client):
	"""Test that login with nonexistent user fails"""
	response = client.post(
		reverse("login"),
		{
			"username": "nonexistent",
			"password": "anypass",
		},
	)

	assert response.status_code == 200
	assert b"Invalid" in response.content or b"invalid" in response.content.decode()


@pytest.mark.django_db
def test_logout_clears_session(client):
	"""Test that logout clears the user session"""
	user = User.objects.create_user(username="testuser", password="pass123")
	client.login(username="testuser", password="pass123")
	
	# Verify logged in
	assert client.session.get("_auth_user_id") == str(user.id)
	
	response = client.get(reverse("logout"))
	
	assert response.status_code == 302
	assert response["Location"] == reverse("login")
	
	# Verify session was cleared
	assert client.session.get("_auth_user_id") is None


@pytest.mark.django_db
def test_login_logs_success(client):
	"""Login success should emit an auth log event."""
	customer_group, _ = Group.objects.get_or_create(name="customer")
	user = User.objects.create_user(username="customer1", password="pass123")
	user.groups.add(customer_group)

	handler = ListLogHandler(logging.INFO)
	logger = logging.getLogger("flower_shop.auth")
	logger.addHandler(handler)
	logger.setLevel(logging.INFO)

	try:
		response = client.post(
			reverse("login"),
			{
				"username": "customer1",
				"password": "pass123",
			},
		)

		assert response.status_code == 302
		assert any(record.getMessage() == "login.success" for record in handler.records)

		record = next(record for record in handler.records if record.getMessage() == "login.success")
		assert record.payload["username"] == "customer1"
		assert record.payload["user_id"] == user.id
	finally:
		logger.removeHandler(handler)


@pytest.mark.django_db
def test_logout_logs_success(client):
	"""Logout should emit an auth log event."""
	user = User.objects.create_user(username="testuser", password="pass123")
	client.login(username="testuser", password="pass123")

	handler = ListLogHandler(logging.INFO)
	logger = logging.getLogger("flower_shop.auth")
	logger.addHandler(handler)
	logger.setLevel(logging.INFO)

	try:
		response = client.get(reverse("logout"))

		assert response.status_code == 302
		assert any(record.getMessage() == "logout.success" for record in handler.records)

		record = next(record for record in handler.records if record.getMessage() == "logout.success")
		assert record.payload["username"] == "testuser"
		assert record.payload["user_id"] == user.id
	finally:
		logger.removeHandler(handler)


@pytest.mark.django_db
def test_customer_can_view_products(customer_client, product):
	response = customer_client.get(reverse("product_list"))

	assert response.status_code == 200
	assert b"Rose Bouquet" in response.content


@pytest.mark.django_db
def test_customer_can_create_order(client):
	"""Test that customers can create an order"""
	customer_group, _ = Group.objects.get_or_create(name="customer")
	customer = User.objects.create_user(username="cust2", password="pass123")
	customer.groups.add(customer_group)
	
	product = Product.objects.create(
		name="Test Product",
		description="For testing.",
		price="25.00",
		in_stock=True,
	)
	
	client.login(username="cust2", password="pass123")
	
	response = client.post(
		reverse("order_create"),
		{
			"products": [product.pk],
			"billing_name": "Customer Test",
			"billing_email": "customer@example.com",
			"billing_address": "123 Flower Lane",
			"billing_city": "Bloomfield",
			"billing_state": "UT",
			"billing_zip": "84101",
		},
	)

	assert response.status_code == 302
	created_order = Order.objects.get(customer=customer)
	assert created_order.customer_name == "cust2"
	assert created_order.billing_email == "customer@example.com"
	assert list(created_order.products.values_list("pk", flat=True)) == [product.pk]
	assert response["Location"] == reverse("order_detail", kwargs={"pk": created_order.pk})


@pytest.mark.django_db
def test_order_list_requires_employee(client):
	"""Test that unauthenticated users cannot view order list"""
	response = client.get(reverse("order_list"))

	# Should redirect to login since not authenticated
	assert response.status_code == 302


@pytest.mark.django_db
def test_employee_can_view_order_list(client):
	"""Test that employee can view all orders"""
	employee_group, _ = Group.objects.get_or_create(name="employee")
	employee = User.objects.create_user(username="emp2", password="pass123")
	employee.groups.add(employee_group)
	
	# Create an order by a different user
	product = Product.objects.create(
		name="Product",
		description="Test",
		price="10.00",
		in_stock=True,
	)
	order = Order.objects.create(customer_name="Someone Else")
	order.products.add(product)
	
	client.login(username="emp2", password="pass123")
	
	response = client.get(reverse("order_list"))

	assert response.status_code == 200
	assert b"Someone Else" in response.content


@pytest.mark.django_db
def test_customer_can_view_own_orders_in_order_list(customer_client, customer_user, products):
	product_one, product_two = products
	other_customer = User.objects.create_user(username="other_customer", password="pass123")
	customer_order = Order.objects.create(customer=customer_user, customer_name="Customer Test")
	customer_order.products.add(product_one)
	other_order = Order.objects.create(customer=other_customer, customer_name="Other Customer")
	other_order.products.add(product_two)

	response = customer_client.get(reverse("order_list"))

	assert response.status_code == 200
	assert b"Tulip Bunch" in response.content
	assert b"Lily Arrangement" not in response.content


@pytest.mark.django_db
def test_customer_can_update_own_order(customer_client, customer_user, products):
	product_one, product_two = products
	order = Order.objects.create(
		customer=customer_user,
		customer_name="Customer Test",
		billing_name="Old Name",
		billing_email="old@example.com",
		billing_address="1 Old Street",
		billing_city="Oldtown",
		billing_state="UT",
		billing_zip="84000",
	)
	order.products.add(product_one)

	response = customer_client.post(
		reverse("order_update", kwargs={"pk": order.pk}),
		{
			"products": [product_two.pk],
			"billing_name": "Updated Customer",
			"billing_email": "updated@example.com",
			"billing_address": "123 Flower Lane",
			"billing_city": "Bloomfield",
			"billing_state": "UT",
			"billing_zip": "84101",
		},
	)

	assert response.status_code == 302
	order.refresh_from_db()
	assert order.customer == customer_user
	assert order.customer_name == customer_user.username
	assert order.billing_email == "updated@example.com"
	assert list(order.products.values_list("pk", flat=True)) == [product_two.pk]


@pytest.mark.django_db
def test_customer_cannot_update_another_customers_order(customer_client, product):
	other_customer = User.objects.create_user(username="other_customer", password="pass123")
	order = Order.objects.create(customer=other_customer, customer_name="Other Customer")
	order.products.add(product)

	response = customer_client.post(
		reverse("order_update", kwargs={"pk": order.pk}),
		{
			"products": [product.pk],
			"billing_name": "Updated Customer",
			"billing_email": "updated@example.com",
			"billing_address": "123 Flower Lane",
			"billing_city": "Bloomfield",
			"billing_state": "UT",
			"billing_zip": "84101",
		},
	)

	assert response.status_code == 404
	order.refresh_from_db()
	assert order.billing_email == ""


@pytest.mark.django_db
def test_customer_cannot_delete_order(customer_client, customer_user, product):
	order = Order.objects.create(customer=customer_user, customer_name="Customer Test")
	order.products.add(product)

	response = customer_client.post(reverse("order_delete", kwargs={"pk": order.pk}))

	assert response.status_code == 403
	assert Order.objects.filter(pk=order.pk).exists()


@pytest.mark.django_db
def test_admin_user_change_page_loads_with_groups(client):
	admin_user = User.objects.create_superuser(
		username="admin_user",
		email="admin@example.com",
		password="pass123",
	)
	employee_group, _ = Group.objects.get_or_create(name="employee")
	employee = User.objects.create_user(username="employee_to_edit", password="pass123")
	employee.groups.add(employee_group)
	client.login(username="admin_user", password="pass123")

	response = client.get(reverse("admin:auth_user_change", args=[employee.pk]))

	assert response.status_code == 200
	assert b"employee" in response.content


@pytest.mark.django_db
def test_dashboard_requires_employee(client):
	"""Test that unauthenticated users cannot view dashboard"""
	response = client.get(reverse("dashboard"))

	# Should redirect to login since not authenticated
	assert response.status_code == 302


@pytest.mark.django_db
def test_employee_can_view_dashboard(client):
	"""Test that employee can view the dashboard"""
	employee_group, _ = Group.objects.get_or_create(name="employee")
	employee = User.objects.create_user(username="emp3", password="pass123")
	employee.groups.add(employee_group)
	
	client.login(username="emp3", password="pass123")
	
	response = client.get(reverse("dashboard"))

	assert response.status_code == 200
	assert "shop/dashboard.html" in [t.name for t in response.templates]


@pytest.mark.django_db
def test_customer_cannot_view_dashboard(client):
	"""Test that customer cannot view the dashboard"""
	customer_group, _ = Group.objects.get_or_create(name="customer")
	customer = User.objects.create_user(username="cust3", password="pass123")
	customer.groups.add(customer_group)
	
	client.login(username="cust3", password="pass123")
	
	response = client.get(reverse("dashboard"))

	assert response.status_code == 403


@pytest.mark.django_db
def test_base_template_shows_logout_when_authenticated(client):
	"""Test that base template shows logout link for authenticated users"""
	user = User.objects.create_user(username="testuser2", password="pass123")
	client.login(username="testuser2", password="pass123")
	
	response = client.get(reverse("home"))

	assert response.status_code == 200
	assert b"testuser2" in response.content or b"Welcome" in response.content
	assert b"Logout" in response.content


@pytest.mark.django_db
def test_base_template_shows_login_when_not_authenticated(client):
	"""Test that base template shows login/register links for unauthenticated users"""
	response = client.get(reverse("home"))

	assert response.status_code == 200
	assert b"Login" in response.content
	assert b"Register" in response.content
