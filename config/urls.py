from django.urls import path
from .views import index, live, ready
from django.contrib.auth.views import LogoutView
from django.views.generic import RedirectView
from delivery import planning_views as planning
from delivery import portal_views as portal
from delivery import print_views as printing

urlpatterns = [
    path("", RedirectView.as_view(url="/performance/", permanent=False), name="index"),
    path("login/", portal.DeliveryLoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("performance/", portal.performance, name="performance"),
    path("performance/map/", portal.region_map, name="region-map"),
    path("performance/print/", printing.preview, name="print-preview"),
    path("performance/print/pdf/", printing.download, name="print-download"),
    path("performance/customers/<uuid:customer_id>/", portal.customer_detail, name="employee-customer"),
    path("performance/contracts/<uuid:contract_id>/", portal.contract_detail, name="employee-contract"),
    path("performance/places/<uuid:presentation_id>/", portal.site_detail, name="employee-site"),
    path("performance/logos/<str:kind>/<uuid:object_id>/", portal.logo, name="performance-logo"),
    path("planning/accounts/", portal.account_list, name="accounts"),
    path("planning/accounts/new/", portal.account_new, name="account-new"),
    path("planning/accounts/<int:user_id>/", portal.account_edit, name="account-edit"),
    path("planning/accounts/<int:user_id>/password/", portal.account_password, name="account-password"),
    path("planning/", planning.customer_list, name="planning-home"),
    path("planning/customers/new/", planning.customer_edit, name="planning-customer-new"),
    path("planning/location-guess/", planning.location_guess, name="planning-location-guess"),
    path("planning/customers/<uuid:customer_id>/", planning.customer_detail, name="planning-customer-detail"),
    path("planning/customers/<uuid:customer_id>/edit/", planning.customer_edit, name="planning-customer-edit"),
    path("planning/customers/<uuid:customer_id>/delete/", planning.customer_delete, name="planning-customer-delete"),
    path("planning/customers/<uuid:customer_id>/contracts/new/", planning.contract_edit, name="planning-contract-new"),
    path("planning/customers/<uuid:customer_id>/contracts/<uuid:contract_id>/edit/", planning.contract_edit, name="planning-contract-edit"),
    path("planning/customers/<uuid:customer_id>/duplicates/", planning.duplicate_merge_search, name="planning-duplicate-search"),
    path("planning/customers/<uuid:customer_id>/duplicates/review/", planning.duplicate_merge_review, name="planning-duplicate-review"),
    path("planning/contracts/<uuid:contract_id>/", planning.contract_detail, name="planning-contract-detail"),
    path("planning/contracts/<uuid:contract_id>/end/", planning.contract_end, name="planning-contract-end"),
    path("planning/places/<uuid:site_id>/edit/", planning.site_edit, name="planning-site-edit"),
    path("planning/logos/<str:kind>/<uuid:object_id>/", planning.logo, name="planning-logo"),
    path("planning/products/new/", planning.product_add, name="planning-product-add"),
    path("planning/products/<uuid:product_id>/edit/", planning.product_add, name="planning-product-edit"),
    path("planning/products/<uuid:product_id>/delete/", planning.product_delete, name="planning-product-delete"),
    path("health/live/", live, name="health-live"),
    path("health/ready/", ready, name="health-ready"),
]
