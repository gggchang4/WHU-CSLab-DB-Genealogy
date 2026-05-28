from django.db.models import Count, Exists, OuterRef, Q
from django.http import JsonResponse
from django.views import View

from apps.genealogy.models import (
    Genealogy,
    Member,
    ParentChildRelation,
)
from apps.genealogy.services import fetch_descendant_map_viewport


class ApiAccessMixin:
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({"error": "Authentication required."}, status=401)
        return super().dispatch(request, *args, **kwargs)

    def get_genealogy(self):
        try:
            return Genealogy.objects.accessible_to(self.request.user).get(
                genealogy_id=self.kwargs["genealogy_id"]
            )
        except Genealogy.DoesNotExist:
            return None

    def genealogy_or_404(self):
        genealogy = self.get_genealogy()
        if genealogy is None:
            return None, JsonResponse({"error": "Genealogy not found."}, status=404)
        return genealogy, None


def _parse_int(value, *, default=None, min_value=None, max_value=None):
    if value in (None, ""):
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    if min_value is not None:
        parsed = max(parsed, min_value)
    if max_value is not None:
        parsed = min(parsed, max_value)
    return parsed


def _parse_float(value, *, default):
    if value in (None, ""):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _member_payload(member):
    return {
        "member_id": member.member_id,
        "full_name": member.full_name,
        "gender": member.gender,
        "birth_year": member.birth_year,
        "death_year": member.death_year,
        "generation_label": member.generation_label,
        "branch_name": member.branch_name,
    }


class ApiGenealogyListView(ApiAccessMixin, View):
    def get(self, request):
        genealogies = list(
            Genealogy.objects.accessible_to(request.user)
            .select_related("created_by")
            .order_by("title", "genealogy_id")
        )
        genealogy_ids = [genealogy.genealogy_id for genealogy in genealogies]
        member_counts = {
            row["genealogy_id"]: row["total"]
            for row in Member.objects.filter(genealogy_id__in=genealogy_ids)
            .values("genealogy_id")
            .annotate(total=Count("member_id"))
        }
        relation_counts = {
            row["genealogy_id"]: row["total"]
            for row in ParentChildRelation.objects.filter(genealogy_id__in=genealogy_ids)
            .values("genealogy_id")
            .annotate(total=Count("relation_id"))
        }
        editable_genealogy_ids = set(
            Genealogy.objects.editable_by(request.user)
            .filter(genealogy_id__in=genealogy_ids)
            .values_list("genealogy_id", flat=True)
        )

        payload = []
        for genealogy in genealogies:
            if genealogy.created_by_id == request.user.user_id:
                role = "owner"
            elif genealogy.genealogy_id in editable_genealogy_ids:
                role = "editor"
            else:
                role = "viewer"
            payload.append(
                {
                    "genealogy_id": genealogy.genealogy_id,
                    "title": genealogy.title,
                    "surname": genealogy.surname,
                    "compiled_at": genealogy.compiled_at,
                    "description": genealogy.description,
                    "owner_name": genealogy.created_by.display_name
                    or genealogy.created_by.username,
                    "member_count": member_counts.get(genealogy.genealogy_id, 0),
                    "relation_count": relation_counts.get(genealogy.genealogy_id, 0),
                    "role": role,
                }
            )

        return JsonResponse({"genealogies": payload})


class ApiMemberSearchView(ApiAccessMixin, View):
    def get(self, request, genealogy_id):
        genealogy, error_response = self.genealogy_or_404()
        if error_response is not None:
            return error_response

        query = request.GET.get("q", "").strip()
        limit = _parse_int(request.GET.get("limit"), default=12, min_value=1, max_value=30)
        members = Member.objects.filter(genealogy=genealogy)
        if query:
            filters = (
                Q(full_name__icontains=query)
                | Q(surname__icontains=query)
                | Q(given_name__icontains=query)
                | Q(branch_name__icontains=query)
            )
            if query.isdigit():
                filters |= Q(member_id=int(query))
            members = members.filter(filters)
        else:
            parent_link = ParentChildRelation.objects.filter(
                genealogy_id=genealogy.genealogy_id,
                child_member_id=OuterRef("member_id"),
            )
            child_link = ParentChildRelation.objects.filter(
                genealogy_id=genealogy.genealogy_id,
                parent_member_id=OuterRef("member_id"),
            )
            members = (
                members.annotate(
                    has_parent=Exists(parent_link),
                    has_child=Exists(child_link),
                )
                .filter(has_parent=False, has_child=True)
                .filter(Q(surname=genealogy.surname) | Q(surname=""))
            )

        members = members.order_by("birth_year", "member_id")[:limit]
        return JsonResponse({"members": [_member_payload(member) for member in members]})


class ApiDescendantMapViewportView(ApiAccessMixin, View):
    def get(self, request, genealogy_id):
        genealogy, error_response = self.genealogy_or_404()
        if error_response is not None:
            return error_response

        root_member_id = _parse_int(request.GET.get("root_member_id"), min_value=1)
        if root_member_id is None:
            return JsonResponse({"error": "root_member_id is required."}, status=400)

        if not Member.objects.filter(
            genealogy=genealogy,
            member_id=root_member_id,
        ).exists():
            return JsonResponse({"error": "Root member not found."}, status=404)

        max_depth = _parse_int(
            request.GET.get("max_depth"),
            default=5,
            min_value=1,
            max_value=30,
        )
        padding = _parse_float(request.GET.get("padding"), default=360)
        viewport = {
            "x_min": _parse_float(request.GET.get("x_min"), default=-600),
            "x_max": _parse_float(request.GET.get("x_max"), default=1800),
            "y_min": _parse_float(request.GET.get("y_min"), default=-900),
            "y_max": _parse_float(request.GET.get("y_max"), default=1400),
        }

        result = fetch_descendant_map_viewport(
            genealogy_id=genealogy.genealogy_id,
            root_member_id=root_member_id,
            max_depth=max_depth,
            padding=padding,
            **viewport,
        )
        if result is None:
            return JsonResponse({"error": "Tree data not found."}, status=404)

        return JsonResponse(result)
