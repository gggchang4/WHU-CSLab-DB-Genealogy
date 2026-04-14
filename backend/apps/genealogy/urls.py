from django.urls import path

from apps.genealogy.views import (
    DashboardView,
    GenealogyCreateView,
    GenealogyDetailView,
    MemberCreateView,
    MemberListView,
)


app_name = "genealogy"


urlpatterns = [
    path("", DashboardView.as_view(), name="dashboard"),
    path("genealogies/new/", GenealogyCreateView.as_view(), name="create"),
    path("genealogies/<int:genealogy_id>/", GenealogyDetailView.as_view(), name="detail"),
    path("genealogies/<int:genealogy_id>/members/", MemberListView.as_view(), name="member-list"),
    path("genealogies/<int:genealogy_id>/members/new/", MemberCreateView.as_view(), name="member-create"),
]
