from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.db import connection
from django.db import transaction
from django.db.models import Count
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, TemplateView

from apps.genealogy.forms import (
    CollaboratorRoleForm,
    GenealogyForm,
    InvitationCreateForm,
    MarriageForm,
    MemberLookupForm,
    MemberForm,
    ParentChildRelationForm,
)
from apps.genealogy.models import (
    CollaboratorRole,
    Genealogy,
    GenealogyCollaborator,
    GenealogyInvitation,
    InvitationStatus,
    Marriage,
    Member,
    ParentChildRelation,
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


class GenealogyOwnerRequiredMixin(GenealogyAccessMixin):
    access_mode = "accessible"

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
                "can_edit": Genealogy.objects.editable_by(self.request.user)
                .filter(genealogy_id=genealogy.genealogy_id)
                .exists(),
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
                "can_edit": Genealogy.objects.editable_by(self.request.user)
                .filter(genealogy_id=genealogy.genealogy_id)
                .exists(),
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
        return context

    def get_success_url(self):
        return reverse_lazy(
            "genealogy:member-list",
            kwargs={"genealogy_id": self.kwargs["genealogy_id"]},
        )


class MemberQueryView(GenealogyAccessMixin, TemplateView):
    template_name = "genealogy/member_query.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        genealogy = self.get_genealogy()
        form = MemberLookupForm(
            self.request.GET or None,
            genealogy=genealogy,
        )
        query_result = None

        if self.request.GET.get("member_id") and form.is_valid():
            member = form.cleaned_data["member_id"]
            query_result = {
                "member": member,
                "parents": genealogy.parent_child_relations.filter(
                    child_member=member
                ).select_related("parent_member"),
                "children": genealogy.parent_child_relations.filter(
                    parent_member=member
                ).select_related("child_member"),
                "marriages": genealogy.marriages.filter(
                    member_a=member
                ).select_related("member_a", "member_b")
                | genealogy.marriages.filter(member_b=member).select_related(
                    "member_a", "member_b"
                ),
                "ancestors": self.fetch_ancestors(
                    genealogy_id=genealogy.genealogy_id,
                    member_id=member.member_id,
                ),
            }

        context.update(
            {
                "genealogy": genealogy,
                "lookup_form": form,
                "query_result": query_result,
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
            at.parent_role,
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
                "is_owner": genealogy.created_by_id == self.request.user.user_id,
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
        return (
            invitation.genealogy.created_by_id == invitation.inviter_user_id
            or invitation.genealogy.collaborators.filter(
                user_id=invitation.inviter_user_id
            ).exists()
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
                messages.error(request, "该邀请已失效，请联系当前族谱负责人重新邀请。")
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
