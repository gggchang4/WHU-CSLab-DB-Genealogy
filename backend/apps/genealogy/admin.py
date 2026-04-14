from django.contrib import admin

from apps.genealogy.models import (
    Genealogy,
    GenealogyCollaborator,
    GenealogyInvitation,
    Marriage,
    Member,
    MemberEvent,
    ParentChildRelation,
)


@admin.register(Genealogy)
class GenealogyAdmin(admin.ModelAdmin):
    list_display = ("genealogy_id", "title", "surname", "created_by", "compiled_at")
    search_fields = ("title", "surname")
    list_filter = ("surname",)


@admin.register(Member)
class MemberAdmin(admin.ModelAdmin):
    list_display = ("member_id", "full_name", "genealogy", "gender", "birth_year", "death_year", "is_living")
    search_fields = ("full_name", "surname", "given_name")
    list_filter = ("gender", "is_living", "genealogy")


@admin.register(GenealogyInvitation)
class GenealogyInvitationAdmin(admin.ModelAdmin):
    list_display = ("invitation_id", "genealogy", "inviter_user", "invitee_user", "status", "invited_at")
    list_filter = ("status", "genealogy")
    search_fields = ("genealogy__title", "inviter_user__username", "invitee_user__username")


@admin.register(GenealogyCollaborator)
class GenealogyCollaboratorAdmin(admin.ModelAdmin):
    list_display = ("collaborator_id", "genealogy", "user", "role", "joined_at")
    list_filter = ("role", "genealogy")
    search_fields = ("genealogy__title", "user__username", "user__display_name")


@admin.register(MemberEvent)
class MemberEventAdmin(admin.ModelAdmin):
    list_display = ("event_id", "member", "event_type", "event_year", "genealogy")
    list_filter = ("event_type", "genealogy")
    search_fields = ("member__full_name", "place_text", "description")


@admin.register(ParentChildRelation)
class ParentChildRelationAdmin(admin.ModelAdmin):
    list_display = ("relation_id", "genealogy", "parent_member", "child_member", "parent_role")
    list_filter = ("parent_role", "genealogy")
    search_fields = ("parent_member__full_name", "child_member__full_name")


@admin.register(Marriage)
class MarriageAdmin(admin.ModelAdmin):
    list_display = ("marriage_id", "genealogy", "member_a", "member_b", "status", "start_year", "end_year")
    list_filter = ("status", "genealogy")
    search_fields = ("member_a__full_name", "member_b__full_name")
