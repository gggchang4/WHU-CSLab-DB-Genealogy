from django.urls import path

from apps.genealogy.api import (
    ApiDescendantMapViewportView,
    ApiGenealogyListView,
    ApiMemberSearchView,
)

app_name = "genealogy_api"

urlpatterns = [
    path("genealogies/", ApiGenealogyListView.as_view(), name="genealogy-list"),
    path(
        "genealogies/<int:genealogy_id>/members/search/",
        ApiMemberSearchView.as_view(),
        name="member-search",
    ),
    path(
        "genealogies/<int:genealogy_id>/descendant-map/viewport/",
        ApiDescendantMapViewportView.as_view(),
        name="descendant-map-viewport",
    ),
]
