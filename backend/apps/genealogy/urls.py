from django.urls import path

from apps.genealogy.views import (
    CollaborationManageView,
    CollaboratorRemoveView,
    CollaboratorRoleUpdateView,
    DashboardView,
    GenealogyCreateView,
    GenealogyDetailView,
    InvitationAcceptView,
    InvitationCreateView,
    InvitationDeclineView,
    InvitationRevokeView,
    MarriageCreateView,
    MarriageDeleteView,
    MarriageUpdateView,
    MemberCreateView,
    MemberListView,
    MemberQueryView,
    ParentChildRelationCreateView,
    ParentChildRelationDeleteView,
    ParentChildRelationUpdateView,
    RelationshipManageView,
)


app_name = "genealogy"


urlpatterns = [
    path("", DashboardView.as_view(), name="dashboard"),
    path("genealogies/new/", GenealogyCreateView.as_view(), name="create"),
    path("genealogies/<int:genealogy_id>/", GenealogyDetailView.as_view(), name="detail"),
    path("genealogies/<int:genealogy_id>/members/", MemberListView.as_view(), name="member-list"),
    path("genealogies/<int:genealogy_id>/members/new/", MemberCreateView.as_view(), name="member-create"),
    path("genealogies/<int:genealogy_id>/queries/member/", MemberQueryView.as_view(), name="member-query"),
    path("genealogies/<int:genealogy_id>/relationships/", RelationshipManageView.as_view(), name="relationships"),
    path("genealogies/<int:genealogy_id>/relationships/parent-child/new/", ParentChildRelationCreateView.as_view(), name="parent-child-create"),
    path("genealogies/<int:genealogy_id>/relationships/parent-child/<int:relation_id>/edit/", ParentChildRelationUpdateView.as_view(), name="parent-child-update"),
    path("genealogies/<int:genealogy_id>/relationships/parent-child/<int:relation_id>/delete/", ParentChildRelationDeleteView.as_view(), name="parent-child-delete"),
    path("genealogies/<int:genealogy_id>/relationships/marriages/new/", MarriageCreateView.as_view(), name="marriage-create"),
    path("genealogies/<int:genealogy_id>/relationships/marriages/<int:marriage_id>/edit/", MarriageUpdateView.as_view(), name="marriage-update"),
    path("genealogies/<int:genealogy_id>/relationships/marriages/<int:marriage_id>/delete/", MarriageDeleteView.as_view(), name="marriage-delete"),
    path("genealogies/<int:genealogy_id>/collaboration/", CollaborationManageView.as_view(), name="collaboration"),
    path("genealogies/<int:genealogy_id>/collaboration/invite/", InvitationCreateView.as_view(), name="invitation-create"),
    path("genealogies/<int:genealogy_id>/collaboration/invitations/<int:invitation_id>/revoke/", InvitationRevokeView.as_view(), name="invitation-revoke"),
    path("invitations/<int:invitation_id>/accept/", InvitationAcceptView.as_view(), name="invitation-accept"),
    path("invitations/<int:invitation_id>/decline/", InvitationDeclineView.as_view(), name="invitation-decline"),
    path("genealogies/<int:genealogy_id>/collaboration/collaborators/<int:collaborator_id>/role/", CollaboratorRoleUpdateView.as_view(), name="collaborator-role-update"),
    path("genealogies/<int:genealogy_id>/collaboration/collaborators/<int:collaborator_id>/remove/", CollaboratorRemoveView.as_view(), name="collaborator-remove"),
]
