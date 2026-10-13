from django.contrib import admin
from django.urls import include, path

admin.site.site_header = "Auveria Bank - Staff Admin"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", include("apps.api.urls")),
]
