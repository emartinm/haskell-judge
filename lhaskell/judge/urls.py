"""URLs of the judge (mounted under /haskell/)."""

from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy

from . import views

app_name = "judge"
urlpatterns = [
    path("", views.index, name="index"),
    path("help/", views.help_page, name="help"),
    path("collection/", views.show_collections, name="collections"),
    path("collection/<int:collection_id>", views.show_collection, name="collection"),
    path("problem/<int:problem_id>", views.show_problem, name="problem"),
    path("submit/<int:problem_id>", views.submit, name="submit"),
    path("submission/", views.show_submissions, name="submissions"),
    path("submission/<int:submission_id>", views.show_submission, name="submission"),
    path("submission/<int:submission_id>/download", views.download_submission, name="download_submission"),
    path("ranking/", views.show_rankings, name="rankings"),
    path("ranking/<int:collection_id>", views.show_ranking, name="ranking"),
    path("ranking/<int:collection_id>/download", views.download_ranking, name="download_ranking"),
    path("statistics/", views.show_statistics, name="statistics"),
    path("login/", auth_views.LoginView.as_view(template_name="judge/login.html"), name="login"),
    path("logout/", auth_views.LogoutView.as_view(template_name="judge/logout.html"), name="logout"),
    path(
        "password_change/",
        auth_views.PasswordChangeView.as_view(
            template_name="judge/password_change.html", success_url=reverse_lazy("judge:password_change_done")
        ),
        name="password_change",
    ),
    path("password_change_done/", views.password_change_done, name="password_change_done"),
]
