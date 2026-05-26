from django.urls import path

from .views import (
    DashboardView,
    CheckoutView,
    CustomerOrderDetailView,
    CustomerOrderHistoryView,
    HomePageView,
    OrderCreateView,
    OrderDeleteView,
    OrderDetailView,
    OrderListView,
    OrderUpdateView,
    ProductListView,
    ProductDetailView,
    CustomerRegistrationView,
    LoginView,
    LogoutView,
)

urlpatterns = [
    path("", HomePageView.as_view(), name="home"),
    path("register/", CustomerRegistrationView.as_view(), name="register"),
    path("login/", LoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("internal/dashboard/", DashboardView.as_view(), name="dashboard"),
    path("products/", ProductListView.as_view(), name="product_list"),
    path("products/<int:pk>/", ProductDetailView.as_view(), name="product_detail"),
    path("checkout/<int:pk>/", CheckoutView.as_view(), name="checkout"),
    path("account/orders/", CustomerOrderHistoryView.as_view(), name="customer_order_history"),
    path("account/orders/<int:pk>/", CustomerOrderDetailView.as_view(), name="customer_order_detail"),
    path("orders/", OrderListView.as_view(), name="order_list"),
    path("orders/new/", OrderCreateView.as_view(), name="order_create"),
    path("orders/<int:pk>/", OrderDetailView.as_view(), name="order_detail"),
    path("orders/<int:pk>/edit/", OrderUpdateView.as_view(), name="order_update"),
    path("orders/<int:pk>/delete/", OrderDeleteView.as_view(), name="order_delete"),
]
