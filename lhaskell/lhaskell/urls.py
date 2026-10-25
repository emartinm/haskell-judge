"""URL configuration: everything is served under /haskell/ (see nginx in the README)."""

from django.contrib import admin
from django.urls import include, path

admin.site.site_header = "Learn Haskell"
admin.site.site_title = "Learn Haskell"
admin.site.index_title = "Administración"

urlpatterns = [
    path("haskell/admin/", admin.site.urls),
    path("haskell/", include("judge.urls")),
]
