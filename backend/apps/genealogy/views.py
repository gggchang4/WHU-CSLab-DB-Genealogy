from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.db.models import Count, Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, TemplateView, UpdateView

from apps.genealogy.forms import (
    CollaboratorRoleForm,
    GenealogyForm,
    InvitationCreateForm,
    KinshipPathQueryForm,
    MarriageForm,
    MemberForm,
    MemberEventForm,
    MemberLookupForm,
    ParentChildRelationForm,
    TreePreviewForm,
)
from apps.genealogy.models import (
    CollaboratorRole,
    Genealogy,
    GenealogyCollaborator,
    GenealogyInvitation,
    InvitationStatus,
    Marriage,
    Member,
    MemberEvent,
    ParentChildRelation,
    user_can_access_genealogy,
    user_can_edit_genealogy,
)
from apps.genealogy.services import (
    fetch_descendant_tree,
    fetch_genealogy_analytics,
    fetch_root_member_candidates,
)


class GenealogyAccessMixin(LoginRequiredMixin):
    access_mode = "accessible"

    def get_genealogy_queryset(self):
        if self.access_mode == "editable":
            return Genealogy.objects.editable_by(self.request.user)
        return Genealogy.objects.accessible_to(self.request.user)

    def get_genealogy(self):
        if hasattr(self, "_genealogy"):
            return self._genealogy
        try:
            self._genealogy = self.get_genealogy_queryset().get(
                genealogy_id=self.kwargs["genealogy_id"]
            )
            return self._genealogy
        except Genealogy.DoesNotExist as exc:
            raise Http404("Genealogy not found or not accessible.") from exc

    def can_edit_genealogy(self, genealogy=None):
        genealogy = genealogy or self.get_genealogy()
        cache_attr = f"_can_edit_genealogy_{genealogy.genealogy_id}"
        if not hasattr(self, cache_attr):
            setattr(
                self,
                cache_attr,
                user_can_edit_genealogy(
                    genealogy_id=genealogy.genealogy_id,
                    user_id=self.request.user.user_id,
                ),
            )
        return getattr(self, cache_attr)

    def can_access_genealogy(self, genealogy=None):
        genealogy = genealogy or self.get_genealogy()
        cache_attr = f"_can_access_genealogy_{genealogy.genealogy_id}"
        if not hasattr(self, cache_attr):
            setattr(
                self,
                cache_attr,
                user_can_access_genealogy(
                    genealogy_id=genealogy.genealogy_id,
                    user_id=self.request.user.user_id,
                ),
            )
        return getattr(self, cache_attr)

    def is_genealogy_owner(self, genealogy=None):
        genealogy = genealogy or self.get_genealogy()
        return genealogy.created_by_id == self.request.user.user_id


class GenealogyOwnerRequiredMixin(GenealogyAccessMixin):
    def get_genealogy_queryset(self):
        return Genealogy.objects.filter(created_by=self.request.user)


class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = "genealogy/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user

        owned_genealogies = (
            Genealogy.objects.filter(created_by=user)
            .select_related("created_by")
            .annotate(member_count=Count("members", distinct=True))
            .order_by("title", "genealogy_id")
        )
        collaborative_genealogies = (
            Genealogy.objects.filter(collaborators__user=user)
            .select_related("created_by")
            .exclude(created_by=user)
            .annotate(member_count=Count("members", distinct=True))
            .distinct()
            .order_by("title", "genealogy_id")
        )
        pending_invitations = (
            GenealogyInvitation.objects.filter(
                invitee_user=user,
                status=InvitationStatus.PENDING,
            )
            .select_related("genealogy", "inviter_user")
            .order_by("-invited_at")
        )
        accessible_genealogies = Genealogy.objects.accessible_to(user)

        context.update(
            {
                "owned_genealogies": owned_genealogies,
                "collaborative_genealogies": collaborative_genealogies,
                "pending_invitations": pending_invitations,
                "stats": {
                    "genealogy_count": accessible_genealogies.count(),
                    "owned_count": owned_genealogies.count(),
                    "pending_invitation_count": pending_invitations.count(),
                    "member_count": accessible_genealogies.aggregate(
                        total=Count("members", distinct=True)
                    )["total"]
                    or 0,
                },
            }
        )
        return context


class GenealogyCreateView(LoginRequiredMixin, CreateView):
    model = Genealogy
    form_class = GenealogyForm
    template_name = "genealogy/genealogy_form.html"

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        messages.success(self.request, "族谱创建成功，可以继续录入成员信息。")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy(
            "genealogy:detail",
            kwargs={"genealogy_id": self.object.genealogy_id},
        )


class GenealogyDetailView(GenealogyAccessMixin, DetailView):
    model = Genealogy
    pk_url_kwarg = "genealogy_id"
    context_object_name = "genealogy"
    template_name = "genealogy/genealogy_detail.html"

    def get_queryset(self):
        return self.get_genealogy_queryset().select_related("created_by").prefetch_related(
            "collaborators__user"
        )

    def get_object(self, queryset=None):
        queryset = queryset or self.get_queryset()
        try:
            return queryset.get(genealogy_id=self.kwargs["genealogy_id"])
        except Genealogy.DoesNotExist as exc:
            raise Http404("Genealogy not found or not accessible.") from exc

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        genealogy = self.object
        context.update(
            {
                "member_count": genealogy.members.count(),
                "event_count": genealogy.member_events.count(),
                "marriage_count": genealogy.marriages.count(),
                "relation_count": genealogy.parent_child_relations.count(),
                "recent_members": genealogy.members.order_by("-created_at")[:8],
                "collaborators": genealogy.collaborators.select_related("user").order_by(
                    "joined_at"
                ),
                "can_edit": self.can_edit_genealogy(genealogy),
            }
        )
        return context


class MemberListView(GenealogyAccessMixin, ListView):
    model = Member
    context_object_name = "members"
    template_name = "genealogy/member_list.html"
    paginate_by = 20

    def get_queryset(self):
        genealogy = self.get_genealogy()
        queryset = genealogy.members.order_by("full_name", "member_id")
        search_query = self.request.GET.get("q", "").strip()
        if search_query:
            queryset = queryset.filter(full_name__icontains=search_query)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        genealogy = self.get_genealogy()
        context.update(
            {
                "genealogy": genealogy,
                "search_query": self.request.GET.get("q", "").strip(),
                "can_edit": self.can_edit_genealogy(genealogy),
            }
        )
        return context


class MemberCreateView(GenealogyAccessMixin, CreateView):
    model = Member
    form_class = MemberForm
    template_name = "genealogy/member_form.html"
    access_mode = "editable"

    def form_valid(self, form):
        genealogy = self.get_genealogy()
        form.instance.genealogy = genealogy
        form.instance.created_by = self.request.user
        messages.success(self.request, "成员创建成功。")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["genealogy"] = self.get_genealogy()
        context["form_mode"] = "create"
        return context

    def get_success_url(self):
        return reverse_lazy(
            "genealogy:member-list",
            kwargs={"genealogy_id": self.kwargs["genealogy_id"]},
        )


class MemberUpdateView(GenealogyAccessMixin, UpdateView):
    model = Member
    form_class = MemberForm
    template_name = "genealogy/member_form.html"
    pk_url_kwarg = "member_id"
    access_mode = "editable"

    def get_queryset(self):
        return Member.objects.filter(genealogy=self.get_genealogy())

    def form_valid(self, form):
        messages.success(self.request, "成员信息已更新。")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["genealogy"] = self.get_genealogy()
        context["form_mode"] = "edit"
        context["member"] = self.object
        return context

    def get_success_url(self):
        return reverse_lazy(
            "genealogy:member-detail",
            kwargs={
                "genealogy_id": self.kwargs["genealogy_id"],
                "member_id": self.object.member_id,
            },
        )


class MemberContextMixin(GenealogyAccessMixin):
    member_access_mode = "accessible"

    def get_genealogy_queryset(self):
        if self.member_access_mode == "editable":
            return Genealogy.objects.editable_by(self.request.user)
        return super().get_genealogy_queryset()

    def get_member(self):
        if hasattr(self, "_member"):
            return self._member
        self._member = get_object_or_404(
            Member.objects.select_related("genealogy", "created_by"),
            genealogy=self.get_genealogy(),
            member_id=self.kwargs["member_id"],
        )
        return self._member

    def build_member_context(self, **kwargs):
        genealogy = self.get_genealogy()
        member = self.get_member()
        marriages = genealogy.marriages.filter(
            Q(member_a=member) | Q(member_b=member)
        ).select_related("member_a", "member_b")
        return {
            "genealogy": genealogy,
            "member": member,
            "can_edit": self.can_edit_genealogy(genealogy),
            "parents": genealogy.parent_child_relations.filter(
                child_member=member
            ).select_related("parent_member"),
            "children": genealogy.parent_child_relations.filter(
                parent_member=member
            ).select_related("child_member"),
            "marriages": marriages,
            "events": member.events.order_by("-event_year", "-created_at", "-event_id"),
            "event_form": kwargs.get("event_form", MemberEventForm()),
        }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(self.build_member_context(**kwargs))
        return context


class MemberDeleteView(MemberContextMixin, View):
    member_access_mode = "editable"

    def post(self, request, *args, **kwargs):
        genealogy_id = self.get_genealogy().genealogy_id
        member_name = self.get_member().full_name
        self.get_member().delete()
        messages.success(request, f"成员已删除：{member_name}。")
        return redirect("genealogy:member-list", genealogy_id=genealogy_id)


class MemberDetailView(MemberContextMixin, TemplateView):
    template_name = "genealogy/member_detail.html"


class MemberEventCreateView(MemberContextMixin, TemplateView):
    template_name = "genealogy/member_detail.html"
    member_access_mode = "editable"

    def post(self, request, *args, **kwargs):
        genealogy = self.get_genealogy()
        member = self.get_member()
        event_form = MemberEventForm(request.POST)
        if event_form.is_valid():
            try:
                event = event_form.save(commit=False)
                event.genealogy = genealogy
                event.member = member
                event.recorded_by = request.user
                event.full_clean()
                event.save()
            except ValidationError as exc:
                event_form.add_error(None, str(exc))
            else:
                messages.success(request, "成员事件已新增。")
                return redirect(
                    "genealogy:member-detail",
                    genealogy_id=genealogy.genealogy_id,
                    member_id=member.member_id,
                )
        context = self.get_context_data(event_form=event_form)
        return self.render_to_response(context)


class MemberEventUpdateView(MemberContextMixin, TemplateView):
    template_name = "genealogy/member_event_form.html"
    member_access_mode = "editable"

    def get_event(self):
        if hasattr(self, "_event"):
            return self._event
        self._event = get_object_or_404(
            MemberEvent.objects.select_related("member"),
            event_id=self.kwargs["event_id"],
            genealogy=self.get_genealogy(),
            member=self.get_member(),
        )
        return self._event

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "genealogy": self.get_genealogy(),
                "member": self.get_member(),
                "event": self.get_event(),
                "form": kwargs.get("form", MemberEventForm(instance=self.get_event())),
            }
        )
        return context

    def post(self, request, *args, **kwargs):
        event = self.get_event()
        form = MemberEventForm(request.POST, instance=event)
        if form.is_valid():
            try:
                updated_event = form.save(commit=False)
                updated_event.genealogy = self.get_genealogy()
                updated_event.member = self.get_member()
                updated_event.recorded_by = event.recorded_by or request.user
                updated_event.full_clean()
                updated_event.save()
            except ValidationError as exc:
                form.add_error(None, str(exc))
            else:
                messages.success(request, "成员事件已更新。")
                return redirect(
                    "genealogy:member-detail",
                    genealogy_id=self.get_genealogy().genealogy_id,
                    member_id=self.get_member().member_id,
                )
        return self.render_to_response(self.get_context_data(form=form))


class MemberEventDeleteView(MemberContextMixin, View):
    member_access_mode = "editable"

    def post(self, request, *args, **kwargs):
        event = get_object_or_404(
            MemberEvent,
            event_id=kwargs["event_id"],
            genealogy=self.get_genealogy(),
            member=self.get_member(),
        )
        event.delete()
        messages.success(request, "成员事件已删除。")
        return redirect(
            "genealogy:member-detail",
            genealogy_id=self.get_genealogy().genealogy_id,
            member_id=self.get_member().member_id,
        )


class GenealogyAnalyticsView(GenealogyAccessMixin, TemplateView):
    template_name = "genealogy/genealogy_analytics.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        genealogy = self.get_genealogy()
        context.update(
            {
                "genealogy": genealogy,
                "can_edit": self.can_edit_genealogy(genealogy),
                "analytics": fetch_genealogy_analytics(genealogy.genealogy_id),
            }
        )
        return context


class TreePreviewView(GenealogyAccessMixin, TemplateView):
    template_name = "genealogy/tree_preview.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        genealogy = self.get_genealogy()
        form = kwargs.get("form") or TreePreviewForm(
            self.request.GET or None,
            genealogy=genealogy,
        )
        tree_result = None

        if self.request.GET and form.is_valid():
            root_member = form.cleaned_data["root_member_id"]
            if root_member is not None:
                tree_result = fetch_descendant_tree(
                    genealogy_id=genealogy.genealogy_id,
                    root_member_id=root_member.member_id,
                    max_depth=form.cleaned_data["max_depth"],
                )

        context.update(
            {
                "genealogy": genealogy,
                "can_edit": self.can_edit_genealogy(genealogy),
                "tree_form": form,
                "tree_result": tree_result,
                "root_candidates": fetch_root_member_candidates(genealogy.genealogy_id),
            }
        )
        return context


class MemberQueryView(GenealogyAccessMixin, TemplateView):
    template_name = "genealogy/member_query.html"
    kinship_path_max_depth = 64

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        genealogy = self.get_genealogy()
        query_type = self.request.GET.get("query")

        member_lookup_form = kwargs.get("member_lookup_form") or MemberLookupForm(
            self.request.GET if query_type == "member" else None,
            genealogy=genealogy,
        )
        kinship_path_form = kwargs.get("kinship_path_form") or KinshipPathQueryForm(
            self.request.GET if query_type == "path" else None,
            genealogy=genealogy,
        )

        member_query_result = None
        kinship_path_result = None

        if query_type == "member" and member_lookup_form.is_valid():
            member = member_lookup_form.cleaned_data["member_id"]
            member_query_result = {
                "member": member,
                "parents": genealogy.parent_child_relations.filter(
                    child_member=member
                ).select_related("parent_member"),
                "children": genealogy.parent_child_relations.filter(
                    parent_member=member
                ).select_related("child_member"),
                "marriages": genealogy.marriages.filter(
                    Q(member_a=member) | Q(member_b=member)
                ).select_related("member_a", "member_b"),
                "ancestors": self.fetch_ancestors(
                    genealogy_id=genealogy.genealogy_id,
                    member_id=member.member_id,
                ),
            }

        if query_type == "path" and kinship_path_form.is_valid():
            source_member = kinship_path_form.cleaned_data["source_member_id"]
            target_member = kinship_path_form.cleaned_data["target_member_id"]
            kinship_path_result = self.fetch_kinship_path(
                genealogy=genealogy,
                source_member=source_member,
                target_member=target_member,
                max_depth=self.kinship_path_max_depth,
            )

        context.update(
            {
                "genealogy": genealogy,
                "member_lookup_form": member_lookup_form,
                "kinship_path_form": kinship_path_form,
                "member_query_result": member_query_result,
                "kinship_path_result": kinship_path_result,
                "can_edit": self.can_edit_genealogy(genealogy),
            }
        )
        return context

    @staticmethod
    def fetch_ancestors(*, genealogy_id, member_id):
        sql = """
        WITH RECURSIVE ancestor_tree AS (
            SELECT
                pcr.parent_member_id AS ancestor_member_id,
                pcr.child_member_id AS source_member_id,
                pcr.parent_role,
                1 AS depth,
                ARRAY[pcr.child_member_id, pcr.parent_member_id] AS path
            FROM parent_child_relations pcr
            WHERE pcr.genealogy_id = %s
              AND pcr.child_member_id = %s

            UNION ALL

            SELECT
                pcr.parent_member_id AS ancestor_member_id,
                pcr.child_member_id AS source_member_id,
                pcr.parent_role,
                at.depth + 1 AS depth,
                at.path || pcr.parent_member_id
            FROM parent_child_relations pcr
            INNER JOIN ancestor_tree at
                ON pcr.child_member_id = at.ancestor_member_id
            WHERE pcr.genealogy_id = %s
              AND NOT pcr.parent_member_id = ANY(at.path)
        )
        SELECT
            at.depth,
            at.ancestor_member_id,
            m.full_name,
            m.gender,
            m.birth_year,
            m.death_year,
            CASE at.parent_role
                WHEN 'father' THEN '父亲'
                WHEN 'mother' THEN '母亲'
                ELSE at.parent_role
            END AS parent_role_display,
            at.source_member_id
        FROM ancestor_tree at
        INNER JOIN members m
            ON m.member_id = at.ancestor_member_id
        ORDER BY at.depth, at.ancestor_member_id
        """

        with connection.cursor() as cursor:
            cursor.execute(sql, [genealogy_id, member_id, genealogy_id])
            rows = cursor.fetchall()

        return [
            {
                "depth": row[0],
                "member_id": row[1],
                "full_name": row[2],
                "gender": row[3],
                "birth_year": row[4],
                "death_year": row[5],
                "parent_role": row[6],
                "source_member_id": row[7],
            }
            for row in rows
        ]

    @staticmethod
    def fetch_kinship_path(*, genealogy, source_member, target_member, max_depth):
        if source_member.member_id == target_member.member_id:
            return {
                "source_member": source_member,
                "target_member": target_member,
                "steps": [],
                "depth": 0,
                "found": True,
            }

        sql = """
        WITH RECURSIVE relation_edges AS (
            SELECT
                parent_member_id AS from_member_id,
                child_member_id AS to_member_id,
                '子女'::text AS relation_label
            FROM parent_child_relations
            WHERE genealogy_id = %s

            UNION ALL

            SELECT
                child_member_id AS from_member_id,
                parent_member_id AS to_member_id,
                CASE parent_role
                    WHEN 'father' THEN '父亲'
                    WHEN 'mother' THEN '母亲'
                    ELSE parent_role
                END AS relation_label
            FROM parent_child_relations
            WHERE genealogy_id = %s

            UNION ALL

            SELECT
                member_a_id AS from_member_id,
                member_b_id AS to_member_id,
                '配偶'::text AS relation_label
            FROM marriages
            WHERE genealogy_id = %s

            UNION ALL

            SELECT
                member_b_id AS from_member_id,
                member_a_id AS to_member_id,
                '配偶'::text AS relation_label
            FROM marriages
            WHERE genealogy_id = %s
        ),
        path_search AS (
            SELECT
                e.to_member_id AS current_member_id,
                ARRAY[%s, e.to_member_id]::bigint[] AS path_member_ids,
                ARRAY[e.relation_label]::text[] AS path_labels,
                1 AS depth
            FROM relation_edges e
            WHERE e.from_member_id = %s

            UNION ALL

            SELECT
                e.to_member_id AS current_member_id,
                ps.path_member_ids || e.to_member_id,
                ps.path_labels || e.relation_label,
                ps.depth + 1
            FROM path_search ps
            INNER JOIN relation_edges e
                ON e.from_member_id = ps.current_member_id
            WHERE ps.depth < %s
              AND NOT e.to_member_id = ANY(ps.path_member_ids)
        )
        SELECT path_member_ids, path_labels, depth
        FROM path_search
        WHERE current_member_id = %s
        ORDER BY depth
        LIMIT 1
        """

        with connection.cursor() as cursor:
            cursor.execute(
                sql,
                [
                    genealogy.genealogy_id,
                    genealogy.genealogy_id,
                    genealogy.genealogy_id,
                    genealogy.genealogy_id,
                    source_member.member_id,
                    source_member.member_id,
                    max_depth,
                    target_member.member_id,
                ],
            )
            row = cursor.fetchone()

        if row is None:
            return {
                "source_member": source_member,
                "target_member": target_member,
                "steps": [],
                "depth": None,
                "found": False,
            }

        path_member_ids, path_labels, depth = row
        member_map = {
            member.member_id: member
            for member in genealogy.members.filter(member_id__in=path_member_ids)
        }
        steps = []
        for index, relation_label in enumerate(path_labels):
            from_member_id = path_member_ids[index]
            to_member_id = path_member_ids[index + 1]
            steps.append(
                {
                    "from_member": member_map[from_member_id],
                    "to_member": member_map[to_member_id],
                    "relation_label": relation_label,
                }
            )

        return {
            "source_member": source_member,
            "target_member": target_member,
            "steps": steps,
            "depth": depth,
            "found": True,
        }


class RelationshipManageView(GenealogyAccessMixin, TemplateView):
    template_name = "genealogy/relationship_manage.html"
    access_mode = "editable"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        genealogy = self.get_genealogy()
        context.update(
            {
                "genealogy": genealogy,
                "parent_child_form": kwargs.get(
                    "parent_child_form",
                    ParentChildRelationForm(genealogy=genealogy),
                ),
                "marriage_form": kwargs.get(
                    "marriage_form",
                    MarriageForm(genealogy=genealogy),
                ),
                "parent_child_relations": genealogy.parent_child_relations.select_related(
                    "parent_member",
                    "child_member",
                ).order_by("-created_at", "-relation_id"),
                "marriages": genealogy.marriages.select_related(
                    "member_a",
                    "member_b",
                ).order_by("-created_at", "-marriage_id"),
            }
        )
        return context


class ParentChildRelationCreateView(RelationshipManageView):
    def post(self, request, *args, **kwargs):
        genealogy = self.get_genealogy()
        parent_child_form = ParentChildRelationForm(
            request.POST,
            genealogy=genealogy,
        )
        marriage_form = MarriageForm(genealogy=genealogy)

        if parent_child_form.is_valid():
            try:
                parent_child_form.save(created_by=request.user)
            except ValidationError as exc:
                parent_child_form.add_error(None, str(exc))
            else:
                messages.success(request, "亲子关系已创建。")
                return redirect("genealogy:relationships", genealogy_id=genealogy.genealogy_id)

        context = self.get_context_data(
            parent_child_form=parent_child_form,
            marriage_form=marriage_form,
        )
        return self.render_to_response(context)


class MarriageCreateView(RelationshipManageView):
    def post(self, request, *args, **kwargs):
        genealogy = self.get_genealogy()
        marriage_form = MarriageForm(
            request.POST,
            genealogy=genealogy,
        )
        parent_child_form = ParentChildRelationForm(genealogy=genealogy)

        if marriage_form.is_valid():
            try:
                marriage_form.save(created_by=request.user)
            except ValidationError as exc:
                marriage_form.add_error(None, str(exc))
            else:
                messages.success(request, "婚姻关系已创建。")
                return redirect("genealogy:relationships", genealogy_id=genealogy.genealogy_id)

        context = self.get_context_data(
            parent_child_form=parent_child_form,
            marriage_form=marriage_form,
        )
        return self.render_to_response(context)


class ParentChildRelationUpdateView(GenealogyAccessMixin, TemplateView):
    template_name = "genealogy/relationship_edit.html"
    access_mode = "editable"

    def get_relation(self):
        if hasattr(self, "_relation"):
            return self._relation
        self._relation = get_object_or_404(
            ParentChildRelation.objects.select_related("parent_member", "child_member"),
            relation_id=self.kwargs["relation_id"],
            genealogy=self.get_genealogy(),
        )
        return self._relation

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        genealogy = self.get_genealogy()
        relation = self.get_relation()
        context.update(
            {
                "genealogy": genealogy,
                "relation": relation,
                "relationship_type": "parent_child",
                "form": kwargs.get(
                    "form",
                    ParentChildRelationForm(
                        genealogy=genealogy,
                        instance=relation,
                    ),
                ),
            }
        )
        return context

    def post(self, request, *args, **kwargs):
        genealogy = self.get_genealogy()
        relation = self.get_relation()
        form = ParentChildRelationForm(
            request.POST,
            genealogy=genealogy,
            instance=relation,
        )
        if form.is_valid():
            try:
                form.save(created_by=request.user)
            except ValidationError as exc:
                form.add_error(None, str(exc))
            else:
                messages.success(request, "亲子关系已更新。")
                return redirect("genealogy:relationships", genealogy_id=genealogy.genealogy_id)
        return self.render_to_response(self.get_context_data(form=form))


class ParentChildRelationDeleteView(GenealogyAccessMixin, View):
    access_mode = "editable"

    def post(self, request, *args, **kwargs):
        genealogy = self.get_genealogy()
        relation = get_object_or_404(
            ParentChildRelation,
            relation_id=kwargs["relation_id"],
            genealogy=genealogy,
        )
        relation.delete()
        messages.success(request, "亲子关系已删除。")
        return redirect("genealogy:relationships", genealogy_id=genealogy.genealogy_id)


class MarriageUpdateView(GenealogyAccessMixin, TemplateView):
    template_name = "genealogy/relationship_edit.html"
    access_mode = "editable"

    def get_marriage(self):
        if hasattr(self, "_marriage"):
            return self._marriage
        self._marriage = get_object_or_404(
            Marriage.objects.select_related("member_a", "member_b"),
            marriage_id=self.kwargs["marriage_id"],
            genealogy=self.get_genealogy(),
        )
        return self._marriage

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        genealogy = self.get_genealogy()
        marriage = self.get_marriage()
        context.update(
            {
                "genealogy": genealogy,
                "marriage": marriage,
                "relationship_type": "marriage",
                "form": kwargs.get(
                    "form",
                    MarriageForm(
                        genealogy=genealogy,
                        instance=marriage,
                    ),
                ),
            }
        )
        return context

    def post(self, request, *args, **kwargs):
        genealogy = self.get_genealogy()
        marriage = self.get_marriage()
        form = MarriageForm(
            request.POST,
            genealogy=genealogy,
            instance=marriage,
        )
        if form.is_valid():
            try:
                form.save(created_by=request.user)
            except ValidationError as exc:
                form.add_error(None, str(exc))
            else:
                messages.success(request, "婚姻关系已更新。")
                return redirect("genealogy:relationships", genealogy_id=genealogy.genealogy_id)
        return self.render_to_response(self.get_context_data(form=form))


class MarriageDeleteView(GenealogyAccessMixin, View):
    access_mode = "editable"

    def post(self, request, *args, **kwargs):
        genealogy = self.get_genealogy()
        marriage = get_object_or_404(
            Marriage,
            marriage_id=kwargs["marriage_id"],
            genealogy=genealogy,
        )
        marriage.delete()
        messages.success(request, "婚姻关系已删除。")
        return redirect("genealogy:relationships", genealogy_id=genealogy.genealogy_id)


class CollaborationManageView(GenealogyAccessMixin, TemplateView):
    template_name = "genealogy/collaboration_manage.html"
    access_mode = "editable"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        genealogy = self.get_genealogy()
        context.update(
            {
                "genealogy": genealogy,
                "invite_form": kwargs.get(
                    "invite_form",
                    InvitationCreateForm(
                        genealogy=genealogy,
                        inviter_user=self.request.user,
                    ),
                ),
                "pending_sent_invitations": genealogy.invitations.filter(
                    status=InvitationStatus.PENDING
                )
                .select_related("invitee_user", "inviter_user")
                .order_by("-invited_at"),
                "historical_invitations": genealogy.invitations.exclude(
                    status=InvitationStatus.PENDING
                )
                .select_related("invitee_user", "inviter_user")
                .order_by("-responded_at", "-invited_at")[:10],
                "collaborators": genealogy.collaborators.select_related("user").order_by(
                    "joined_at", "collaborator_id"
                ),
                "role_choices": CollaboratorRole.choices,
                "is_owner": self.is_genealogy_owner(genealogy),
            }
        )
        return context


class InvitationCreateView(CollaborationManageView):
    access_mode = "editable"

    def post(self, request, *args, **kwargs):
        genealogy = self.get_genealogy()
        form = InvitationCreateForm(
            request.POST,
            genealogy=genealogy,
            inviter_user=request.user,
        )
        if form.is_valid():
            form.save()
            messages.success(request, "邀请已发送。")
            return redirect("genealogy:collaboration", genealogy_id=genealogy.genealogy_id)
        context = self.get_context_data(invite_form=form)
        return self.render_to_response(context)


class InvitationRespondView(LoginRequiredMixin, View):
    target_status = None

    @staticmethod
    def inviter_is_still_authorized(invitation):
        return user_can_edit_genealogy(
            genealogy_id=invitation.genealogy_id,
            user_id=invitation.inviter_user_id,
        )

    def post(self, request, *args, **kwargs):
        invitation = get_object_or_404(
            GenealogyInvitation.objects.select_related(
                "genealogy",
                "invitee_user",
                "inviter_user",
            ),
            invitation_id=kwargs["invitation_id"],
            invitee_user=request.user,
            status=InvitationStatus.PENDING,
        )

        with transaction.atomic():
            if (
                self.target_status == InvitationStatus.ACCEPTED
                and not self.inviter_is_still_authorized(invitation)
            ):
                messages.error(
                    request,
                    "该邀请已失效，请联系当前族谱负责人重新邀请。",
                )
                return redirect("genealogy:dashboard")

            invitation.status = self.target_status
            invitation.responded_at = timezone.now()
            invitation.full_clean()
            invitation.save(update_fields=["status", "responded_at"])

            if self.target_status == InvitationStatus.ACCEPTED:
                GenealogyCollaborator.objects.create(
                    genealogy=invitation.genealogy,
                    user=request.user,
                    source_invitation=invitation,
                    role=CollaboratorRole.EDITOR,
                    added_by=request.user,
                )
                messages.success(request, "已接受邀请，你现在可以参与该族谱协作。")
            else:
                messages.success(request, "已拒绝邀请。")

        return redirect("genealogy:dashboard")


class InvitationAcceptView(InvitationRespondView):
    target_status = InvitationStatus.ACCEPTED


class InvitationDeclineView(InvitationRespondView):
    target_status = InvitationStatus.DECLINED


class InvitationRevokeView(GenealogyAccessMixin, View):
    access_mode = "editable"

    def post(self, request, *args, **kwargs):
        genealogy = self.get_genealogy()
        invitation = get_object_or_404(
            GenealogyInvitation,
            invitation_id=kwargs["invitation_id"],
            genealogy=genealogy,
            status=InvitationStatus.PENDING,
        )
        invitation.status = InvitationStatus.REVOKED
        invitation.responded_at = timezone.now()
        invitation.full_clean()
        invitation.save(update_fields=["status", "responded_at"])
        messages.success(request, "邀请已撤销。")
        return redirect("genealogy:collaboration", genealogy_id=genealogy.genealogy_id)


class CollaboratorRoleUpdateView(GenealogyOwnerRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        genealogy = self.get_genealogy()
        collaborator = get_object_or_404(
            GenealogyCollaborator.objects.select_related("user"),
            collaborator_id=kwargs["collaborator_id"],
            genealogy=genealogy,
        )
        form = CollaboratorRoleForm(request.POST)
        if form.is_valid():
            collaborator.role = form.cleaned_data["role"]
            collaborator.full_clean()
            collaborator.save(update_fields=["role"])
            messages.success(request, "协作者权限已更新。")
        else:
            messages.error(request, "协作者权限更新失败。")
        return redirect("genealogy:collaboration", genealogy_id=genealogy.genealogy_id)


class CollaboratorRemoveView(GenealogyOwnerRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        genealogy = self.get_genealogy()
        collaborator = get_object_or_404(
            GenealogyCollaborator.objects.select_related("user"),
            collaborator_id=kwargs["collaborator_id"],
            genealogy=genealogy,
        )
        removed_name = collaborator.user.display_name or collaborator.user.username
        genealogy.invitations.filter(
            inviter_user=collaborator.user,
            status=InvitationStatus.PENDING,
        ).update(
            status=InvitationStatus.REVOKED,
            responded_at=timezone.now(),
        )
        collaborator.delete()
        messages.success(request, f"已移除协作者：{removed_name}。")
        return redirect("genealogy:collaboration", genealogy_id=genealogy.genealogy_id)
