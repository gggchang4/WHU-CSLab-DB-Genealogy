from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count
from django.http import Http404
from django.urls import reverse_lazy
from django.views.generic import CreateView, DetailView, ListView, TemplateView

from apps.genealogy.forms import GenealogyForm, MemberForm
from apps.genealogy.models import Genealogy, GenealogyInvitation, InvitationStatus, Member


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


class GenealogyDetailView(LoginRequiredMixin, DetailView):
    model = Genealogy
    pk_url_kwarg = "genealogy_id"
    context_object_name = "genealogy"
    template_name = "genealogy/genealogy_detail.html"

    def get_queryset(self):
        return (
            Genealogy.objects.accessible_to(self.request.user)
            .select_related("created_by")
            .prefetch_related("collaborators__user")
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


class MemberListView(LoginRequiredMixin, ListView):
    model = Member
    context_object_name = "members"
    template_name = "genealogy/member_list.html"
    paginate_by = 20

    def get_genealogy(self):
        if hasattr(self, "_genealogy"):
            return self._genealogy
        try:
            self._genealogy = Genealogy.objects.accessible_to(self.request.user).get(
                genealogy_id=self.kwargs["genealogy_id"]
            )
            return self._genealogy
        except Genealogy.DoesNotExist as exc:
            raise Http404("Genealogy not found or not accessible.") from exc

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


class MemberCreateView(LoginRequiredMixin, CreateView):
    model = Member
    form_class = MemberForm
    template_name = "genealogy/member_form.html"

    def get_genealogy(self):
        if hasattr(self, "_genealogy"):
            return self._genealogy
        try:
            self._genealogy = Genealogy.objects.editable_by(self.request.user).get(
                genealogy_id=self.kwargs["genealogy_id"]
            )
            return self._genealogy
        except Genealogy.DoesNotExist as exc:
            raise Http404("Genealogy not found or not editable.") from exc

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
