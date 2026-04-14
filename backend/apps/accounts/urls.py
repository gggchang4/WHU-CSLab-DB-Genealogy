from django.contrib.auth.views import LogoutView
from django.urls import path

from apps.accounts.views import UserLoginView, UserRegisterView


app_name = "accounts"


urlpatterns = [
    path("login/", UserLoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("register/", UserRegisterView.as_view(), name="register"),
]
