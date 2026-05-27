import json
import logging
from collections import Counter, deque
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.urls import reverse, reverse_lazy
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils import timezone
from django.views.generic import CreateView, DeleteView, DetailView, ListView, TemplateView, UpdateView, View
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.shortcuts import get_object_or_404, redirect

logger = logging.getLogger("flower_shop.auth")

from .forms import CustomerCheckoutForm, CustomerOrderForm, CustomerRegistrationForm, OrderForm
from .gemini import GeminiNotConfigured, GeminiRecommendationError, get_product_recommendation
from .models import Order, Product


def is_employee(user):
	return user.is_authenticated and user.groups.filter(name="employee").exists()


def is_customer(user):
	return user.is_authenticated and user.groups.filter(name="customer").exists()


class IsEmployeeMixin(UserPassesTestMixin):
	"""Mixin to check if user is in employee group"""
	def test_func(self):
		return is_employee(self.request.user)


class IsCustomerMixin(UserPassesTestMixin):
	"""Mixin to check if user is in customer group"""
	def test_func(self):
		return is_customer(self.request.user)


class OrderAccessMixin(LoginRequiredMixin, UserPassesTestMixin):
	login_url = "login"

	def test_func(self):
		return is_employee(self.request.user) or is_customer(self.request.user)

	def user_is_employee(self):
		return is_employee(self.request.user)

	def get_queryset(self):
		queryset = Order.objects.prefetch_related("products").order_by("-created_at")
		if self.user_is_employee():
			return queryset
		return queryset.filter(customer=self.request.user)

	def get_form_class(self):
		if self.user_is_employee():
			return OrderForm
		return CustomerOrderForm

	def get_customer_name(self):
		return self.request.user.get_full_name() or self.request.user.username

	def get_context_data(self, **kwargs):
		context = super().get_context_data(**kwargs)
		context["can_manage_orders"] = self.user_is_employee()
		context["can_edit_order"] = True
		context["can_delete_order"] = self.user_is_employee()
		context["cancel_url"] = reverse("order_list")
		return context


class HomePageView(TemplateView):
	template_name = "shop/home.html"

	def get_context_data(self, **kwargs):
		context = super().get_context_data(**kwargs)
		context["products"] = Product.objects.order_by("name")
		return context


class ProductListView(ListView):
	model = Product
	context_object_name = "products"

	def get_queryset(self):
		return Product.objects.order_by("name")

	def post(self, request, *args, **kwargs):
		self.object_list = self.get_queryset()
		products = list(self.object_list)
		context = self.get_context_data()
		question = request.POST.get("recommendation_prompt", "").strip()
		context["recommendation_prompt"] = question

		if not question:
			context["recommendation_error"] = "Ask a question to get a product recommendation."
		else:
			try:
				context["recommendation_response"] = get_product_recommendation(question, products)
				#context["recommendation_response"] = context["recommendation_response"]+"hi"
			except GeminiNotConfigured:
				context["recommendation_error"] = "Product recommendations need a Gemini API key before they can answer."
			except GeminiRecommendationError:
				context["recommendation_error"] = "Product recommendations are unavailable right now. Please try again..."

		return self.render_to_response(context)

	def get_context_data(self, **kwargs):
		context = super().get_context_data(**kwargs)
		context.setdefault("recommendation_prompt", "")
		context.setdefault("recommendation_response", "")
		context.setdefault("recommendation_error", "")
		return context


class ProductDetailView(DetailView):
	model = Product

class ProductDetailView(DetailView):
	model = Product



class OrderListView(OrderAccessMixin, ListView):
	model = Order
	context_object_name = "orders"


class OrderDetailView(OrderAccessMixin, DetailView):
	model = Order


class OrderCreateView(OrderAccessMixin, CreateView):
	model = Order
	
	def form_valid(self, form):
		form.instance.customer = self.request.user
		if not self.user_is_employee():
			form.instance.customer_name = self.get_customer_name()
			form.instance.status = Order.STATUS_PURCHASED
		return super().form_valid(form)

	def get_success_url(self):
		return reverse("order_detail", kwargs={"pk": self.object.pk})


class CheckoutView(LoginRequiredMixin, CreateView):
	model = Order
	form_class = CustomerCheckoutForm
	template_name = "shop/checkout.html"
	login_url = "login"

	def dispatch(self, request, *args, **kwargs):
		self.product = get_object_or_404(Product, pk=kwargs["pk"], in_stock=True)
		return super().dispatch(request, *args, **kwargs)

	def get_initial(self):
		initial = super().get_initial()
		initial["billing_name"] = self.request.user.get_full_name() or self.request.user.username
		initial["billing_email"] = self.request.user.email
		return initial

	def get_context_data(self, **kwargs):
		context = super().get_context_data(**kwargs)
		context["product"] = self.product
		return context

	def form_valid(self, form):
		order = form.save(commit=False)
		order.customer = self.request.user
		order.customer_name = self.request.user.get_full_name() or self.request.user.username
		order.status = Order.STATUS_PURCHASED
		order.save()
		order.products.add(self.product)
		self.object = order
		return redirect(self.get_success_url())

	def get_success_url(self):
		return reverse("customer_order_detail", kwargs={"pk": self.object.pk})


class CustomerOrderHistoryView(LoginRequiredMixin, ListView):
	model = Order
	template_name = "shop/customer_order_history.html"
	context_object_name = "orders"
	login_url = "login"

	def get_queryset(self):
		return (
			Order.objects.filter(customer=self.request.user)
			.prefetch_related("products")
			.order_by("-created_at")
		)


class CustomerOrderDetailView(LoginRequiredMixin, DetailView):
	model = Order
	template_name = "shop/order_detail.html"
	login_url = "login"

	def get_queryset(self):
		return Order.objects.filter(customer=self.request.user).prefetch_related("products")

	def get_context_data(self, **kwargs):
		context = super().get_context_data(**kwargs)
		context["can_manage_orders"] = False
		context["is_customer_receipt"] = True
		return context


class OrderUpdateView(OrderAccessMixin, UpdateView):
	model = Order

	def form_valid(self, form):
		if not self.user_is_employee():
			form.instance.customer = self.request.user
			form.instance.customer_name = self.get_customer_name()
			form.instance.status = Order.STATUS_PURCHASED
		return super().form_valid(form)


class OrderDeleteView(IsEmployeeMixin, DeleteView):
	model = Order
	success_url = reverse_lazy("order_list")


class DashboardView(IsEmployeeMixin, TemplateView):
	template_name = "shop/dashboard.html"
	log_limit = 50

	def get_context_data(self, **kwargs):
		context = super().get_context_data(**kwargs)
		recent_logs = self._read_recent_logs()
		level_counts = Counter(log.get("level", "INFO") for log in recent_logs)
		since = timezone.now() - timedelta(hours=24)

		context["metrics"] = {
			"product_count": Product.objects.count(),
			"out_of_stock_count": Product.objects.filter(in_stock=False).count(),
			"order_count": Order.objects.count(),
			"orders_last_24h": Order.objects.filter(created_at__gte=since).count(),
		}
		context["log_counts"] = {
			"INFO": level_counts.get("INFO", 0),
			"WARNING": level_counts.get("WARNING", 0),
			"ERROR": level_counts.get("ERROR", 0),
		}
		context["recent_logs"] = recent_logs
		return context

	def _read_recent_logs(self):
		log_path = Path(settings.LOG_FILE_PATH)
		if not log_path.exists():
			return []

		lines = deque(maxlen=self.log_limit)
		with log_path.open("r", encoding="utf-8") as log_file:
			for line in log_file:
				lines.append(line.strip())

		entries = []
		for line in reversed(lines):
			if not line:
				continue
			try:
				parsed = json.loads(line)
			except json.JSONDecodeError:
				continue

			payload = parsed.get("payload", {})
			entries.append(
				{
					"timestamp": parsed.get("timestamp", ""),
					"level": parsed.get("level", ""),
					"message": parsed.get("message", ""),
					"method": payload.get("method", ""),
					"path": payload.get("path", ""),
					"status_code": payload.get("status_code", ""),
					"duration_ms": payload.get("duration_ms", ""),
				}
			)

		return entries


class CustomerRegistrationView(CreateView):
	form_class = CustomerRegistrationForm
	template_name = "shop/register.html"
	success_url = reverse_lazy("login")


class LoginView(TemplateView):
	template_name = "shop/login.html"

	def post(self, request, *args, **kwargs):
		username = request.POST.get("username")
		password = request.POST.get("password")
		next_url = request.POST.get("next") or request.GET.get("next")
		user = authenticate(request, username=username, password=password)
		log_payload = {
			"username": username,
			"remote_addr": request.META.get("REMOTE_ADDR", ""),
			"user_agent": request.META.get("HTTP_USER_AGENT", ""),
		}

		if user is not None:
			log_payload["user_id"] = user.pk
			logger.info("login.success", extra={"payload": log_payload})
			login(request, user)
			if next_url and url_has_allowed_host_and_scheme(
				next_url,
				allowed_hosts={request.get_host()},
				require_https=request.is_secure(),
			):
				return redirect(next_url)
			# Redirect based on group membership
			if user.groups.filter(name="employee").exists():
				return redirect("dashboard")
			else:
				return redirect("product_list")
		else:
			logger.warning("login.failed", extra={"payload": log_payload})
			context = self.get_context_data()
			context["error"] = "Invalid username or password"
			return self.render_to_response(context)


class LogoutView(View):
	def get(self, request, *args, **kwargs):
		user = getattr(request, "user", None)
		log_payload = {
			"remote_addr": request.META.get("REMOTE_ADDR", ""),
			"user_agent": request.META.get("HTTP_USER_AGENT", ""),
		}
		if user and user.is_authenticated:
			log_payload["username"] = user.username
			log_payload["user_id"] = user.pk
			logger.info("logout.success", extra={"payload": log_payload})
		logout(request)
		return redirect("login")
