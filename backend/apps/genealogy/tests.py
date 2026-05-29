from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import DatabaseError, transaction
from django.db.models import Count
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.genealogy.coursework import generate_course_dataset
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
)
from apps.genealogy.services import fetch_descendant_map_viewport

User = get_user_model()


class GenealogyAccessTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="owner",
            display_name="Owner",
            email="owner@example.com",
            password="StrongPass123!",
        )
        self.collaborator = User.objects.create_user(
            username="collab",
            display_name="Collaborator",
            email="collab@example.com",
            password="StrongPass123!",
        )
        self.stranger = User.objects.create_user(
            username="stranger",
            display_name="Stranger",
            email="stranger@example.com",
            password="StrongPass123!",
        )
        self.genealogy = Genealogy.objects.create(
            title="Ouyang Genealogy",
            surname="Ouyang",
            created_by=self.owner,
        )
        invitation = GenealogyInvitation.objects.create(
            genealogy=self.genealogy,
            inviter_user=self.owner,
            invitee_user=self.collaborator,
            status=InvitationStatus.ACCEPTED,
        )
        GenealogyCollaborator.objects.create(
            genealogy=self.genealogy,
            user=self.collaborator,
            source_invitation=invitation,
            role=CollaboratorRole.EDITOR,
            added_by=self.owner,
        )

    def test_dashboard_only_lists_accessible_genealogies(self):
        other_genealogy = Genealogy.objects.create(
            title="Wang Genealogy",
            surname="Wang",
            created_by=self.stranger,
        )

        self.client.force_login(self.collaborator)
        response = self.client.get(reverse("genealogy:dashboard"))

        self.assertContains(response, self.genealogy.title)
        self.assertNotContains(response, other_genealogy.title)

    def test_detail_rejects_unrelated_user(self):
        self.client.force_login(self.stranger)
        response = self.client.get(
            reverse(
                "genealogy:detail",
                kwargs={"genealogy_id": self.genealogy.genealogy_id},
            )
        )

        self.assertEqual(response.status_code, 404)

    def test_create_genealogy_sets_owner_to_current_user(self):
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("genealogy:create"),
            data={
                "title": "Li Genealogy",
                "surname": "Li",
                "compiled_at": 2026,
                "description": "course demo",
            },
        )

        created = Genealogy.objects.get(title="Li Genealogy")
        self.assertRedirects(
            response,
            reverse("genealogy:detail", kwargs={"genealogy_id": created.genealogy_id}),
        )
        self.assertEqual(created.created_by, self.owner)

    def test_member_list_rejects_unrelated_user(self):
        self.client.force_login(self.stranger)
        response = self.client.get(
            reverse(
                "genealogy:member-list",
                kwargs={"genealogy_id": self.genealogy.genealogy_id},
            )
        )

        self.assertEqual(response.status_code, 404)

    def test_member_search_filters_results(self):
        Member.objects.create(
            genealogy=self.genealogy,
            full_name="Member Alpha",
            created_by=self.owner,
        )
        Member.objects.create(
            genealogy=self.genealogy,
            full_name="Member Beta",
            created_by=self.owner,
        )

        self.client.force_login(self.collaborator)
        response = self.client.get(
            reverse(
                "genealogy:member-list",
                kwargs={"genealogy_id": self.genealogy.genealogy_id},
            ),
            data={"q": "Alpha"},
        )

        self.assertContains(response, "Member Alpha")
        self.assertNotContains(response, "Member Beta")

    def test_member_create_sets_genealogy_and_creator(self):
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse(
                "genealogy:member-create",
                kwargs={"genealogy_id": self.genealogy.genealogy_id},
            ),
            data={
                "full_name": "Member Gamma",
                "surname": "Ouyang",
                "given_name": "Gamma",
                "gender": "male",
                "birth_year": 1007,
                "death_year": 1072,
                "is_living": "",
                "generation_label": "",
                "seniority_text": "",
                "branch_name": "main",
                "biography": "demo",
            },
        )

        created = Member.objects.get(full_name="Member Gamma")
        self.assertRedirects(
            response,
            reverse(
                "genealogy:member-list",
                kwargs={"genealogy_id": self.genealogy.genealogy_id},
            ),
        )
        self.assertEqual(created.genealogy, self.genealogy)
        self.assertEqual(created.created_by, self.owner)

    def test_editor_can_update_genealogy_basic_info(self):
        self.client.force_login(self.collaborator)
        response = self.client.post(
            reverse(
                "genealogy:update",
                kwargs={"genealogy_id": self.genealogy.genealogy_id},
            ),
            data={
                "title": "Updated Ouyang Genealogy",
                "surname": "Ouyang",
                "compiled_at": 2025,
                "description": "updated by editor",
            },
        )

        self.genealogy.refresh_from_db()
        self.assertRedirects(
            response,
            reverse(
                "genealogy:detail",
                kwargs={"genealogy_id": self.genealogy.genealogy_id},
            ),
        )
        self.assertEqual(self.genealogy.title, "Updated Ouyang Genealogy")
        self.assertEqual(self.genealogy.compiled_at, 2025)

    def test_owner_can_delete_genealogy(self):
        genealogy_id = self.genealogy.genealogy_id

        self.client.force_login(self.owner)
        response = self.client.post(
            reverse(
                "genealogy:delete",
                kwargs={"genealogy_id": genealogy_id},
            )
        )

        self.assertRedirects(response, reverse("genealogy:dashboard"))
        self.assertFalse(
            Genealogy.objects.filter(genealogy_id=genealogy_id).exists()
        )

    def test_collaborator_cannot_delete_genealogy(self):
        self.client.force_login(self.collaborator)
        response = self.client.post(
            reverse(
                "genealogy:delete",
                kwargs={"genealogy_id": self.genealogy.genealogy_id},
            )
        )

        self.assertEqual(response.status_code, 404)
        self.assertTrue(
            Genealogy.objects.filter(
                genealogy_id=self.genealogy.genealogy_id
            ).exists()
        )


class CollaborationFlowTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="owner2",
            display_name="Owner 2",
            email="owner2@example.com",
            password="StrongPass123!",
        )
        self.editor = User.objects.create_user(
            username="editor2",
            display_name="Editor 2",
            email="editor2@example.com",
            password="StrongPass123!",
        )
        self.invitee = User.objects.create_user(
            username="invitee2",
            display_name="Invitee 2",
            email="invitee2@example.com",
            password="StrongPass123!",
        )
        self.viewer = User.objects.create_user(
            username="viewer2",
            display_name="Viewer 2",
            email="viewer2@example.com",
            password="StrongPass123!",
        )
        self.genealogy = Genealogy.objects.create(
            title="Li Collaboration",
            surname="Li",
            created_by=self.owner,
        )
        accepted_invitation = GenealogyInvitation.objects.create(
            genealogy=self.genealogy,
            inviter_user=self.owner,
            invitee_user=self.editor,
            status=InvitationStatus.ACCEPTED,
        )
        self.editor_collaborator = GenealogyCollaborator.objects.create(
            genealogy=self.genealogy,
            user=self.editor,
            source_invitation=accepted_invitation,
            role=CollaboratorRole.EDITOR,
            added_by=self.owner,
        )
        viewer_invitation = GenealogyInvitation.objects.create(
            genealogy=self.genealogy,
            inviter_user=self.owner,
            invitee_user=self.viewer,
            status=InvitationStatus.ACCEPTED,
        )
        self.viewer_collaborator = GenealogyCollaborator.objects.create(
            genealogy=self.genealogy,
            user=self.viewer,
            source_invitation=viewer_invitation,
            role=CollaboratorRole.VIEWER,
            added_by=self.owner,
        )

    def test_editor_can_send_invitation(self):
        self.client.force_login(self.editor)
        response = self.client.post(
            reverse(
                "genealogy:invitation-create",
                kwargs={"genealogy_id": self.genealogy.genealogy_id},
            ),
            data={
                "invitee_username": self.invitee.username,
                "message": "editor invite",
            },
        )

        invitation = GenealogyInvitation.objects.get(invitee_user=self.invitee)
        self.assertRedirects(
            response,
            reverse(
                "genealogy:collaboration",
                kwargs={"genealogy_id": self.genealogy.genealogy_id},
            ),
        )
        self.assertEqual(invitation.inviter_user, self.editor)

    def test_invitee_can_accept_invitation_and_become_collaborator(self):
        invitation = GenealogyInvitation.objects.create(
            genealogy=self.genealogy,
            inviter_user=self.owner,
            invitee_user=self.invitee,
            status=InvitationStatus.PENDING,
        )

        self.client.force_login(self.invitee)
        response = self.client.post(
            reverse(
                "genealogy:invitation-accept",
                kwargs={"invitation_id": invitation.invitation_id},
            )
        )

        invitation.refresh_from_db()
        self.assertRedirects(response, reverse("genealogy:dashboard"))
        self.assertEqual(invitation.status, InvitationStatus.ACCEPTED)
        self.assertTrue(
            GenealogyCollaborator.objects.filter(
                genealogy=self.genealogy,
                user=self.invitee,
                source_invitation=invitation,
            ).exists()
        )

    def test_viewer_cannot_send_invitation(self):
        self.client.force_login(self.viewer)
        response = self.client.post(
            reverse(
                "genealogy:invitation-create",
                kwargs={"genealogy_id": self.genealogy.genealogy_id},
            ),
            data={
                "invitee_username": self.invitee.username,
                "message": "viewer invite",
            },
        )

        self.assertEqual(response.status_code, 404)
        self.assertFalse(
            GenealogyInvitation.objects.filter(
                genealogy=self.genealogy,
                inviter_user=self.viewer,
                invitee_user=self.invitee,
                message="viewer invite",
            ).exists()
        )

    def test_viewer_invitation_fails_model_validation(self):
        invitation = GenealogyInvitation(
            genealogy=self.genealogy,
            inviter_user=self.viewer,
            invitee_user=self.invitee,
            message="viewer invite",
        )

        with self.assertRaises(ValidationError):
            invitation.full_clean()

    def test_owner_can_remove_collaborator_and_revoke_pending_invites(self):
        pending_invitation = GenealogyInvitation.objects.create(
            genealogy=self.genealogy,
            inviter_user=self.editor,
            invitee_user=self.invitee,
            status=InvitationStatus.PENDING,
        )

        self.client.force_login(self.owner)
        response = self.client.post(
            reverse(
                "genealogy:collaborator-remove",
                kwargs={
                    "genealogy_id": self.genealogy.genealogy_id,
                    "collaborator_id": self.editor_collaborator.collaborator_id,
                },
            )
        )

        self.assertRedirects(
            response,
            reverse(
                "genealogy:collaboration",
                kwargs={"genealogy_id": self.genealogy.genealogy_id},
            ),
        )
        self.assertFalse(
            GenealogyCollaborator.objects.filter(
                collaborator_id=self.editor_collaborator.collaborator_id
            ).exists()
        )
        pending_invitation.refresh_from_db()
        self.assertEqual(pending_invitation.status, InvitationStatus.REVOKED)


class RelationshipManagementTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="rel_owner",
            display_name="Rel Owner",
            email="rel_owner@example.com",
            password="StrongPass123!",
        )
        self.editor = User.objects.create_user(
            username="rel_editor",
            display_name="Rel Editor",
            email="rel_editor@example.com",
            password="StrongPass123!",
        )
        self.viewer = User.objects.create_user(
            username="rel_viewer",
            display_name="Rel Viewer",
            email="rel_viewer@example.com",
            password="StrongPass123!",
        )
        self.stranger = User.objects.create_user(
            username="rel_stranger",
            display_name="Rel Stranger",
            email="rel_stranger@example.com",
            password="StrongPass123!",
        )
        self.genealogy = Genealogy.objects.create(
            title="Relation Demo",
            surname="Demo",
            created_by=self.owner,
        )
        editor_invitation = GenealogyInvitation.objects.create(
            genealogy=self.genealogy,
            inviter_user=self.owner,
            invitee_user=self.editor,
            status=InvitationStatus.ACCEPTED,
        )
        viewer_invitation = GenealogyInvitation.objects.create(
            genealogy=self.genealogy,
            inviter_user=self.owner,
            invitee_user=self.viewer,
            status=InvitationStatus.ACCEPTED,
        )
        GenealogyCollaborator.objects.create(
            genealogy=self.genealogy,
            user=self.editor,
            source_invitation=editor_invitation,
            role=CollaboratorRole.EDITOR,
            added_by=self.owner,
        )
        GenealogyCollaborator.objects.create(
            genealogy=self.genealogy,
            user=self.viewer,
            source_invitation=viewer_invitation,
            role=CollaboratorRole.VIEWER,
            added_by=self.owner,
        )
        self.grandparent = Member.objects.create(
            genealogy=self.genealogy,
            full_name="Grandparent Member",
            gender="male",
            birth_year=1940,
            created_by=self.owner,
        )
        self.parent = Member.objects.create(
            genealogy=self.genealogy,
            full_name="Parent Member",
            gender="male",
            birth_year=1970,
            created_by=self.owner,
        )
        self.mother = Member.objects.create(
            genealogy=self.genealogy,
            full_name="Mother Member",
            gender="female",
            birth_year=1972,
            created_by=self.owner,
        )
        self.child = Member.objects.create(
            genealogy=self.genealogy,
            full_name="Child Member",
            gender="female",
            birth_year=2000,
            created_by=self.owner,
        )
        self.spouse = Member.objects.create(
            genealogy=self.genealogy,
            full_name="Spouse Member",
            gender="female",
            birth_year=1973,
            created_by=self.owner,
        )
        self.isolated = Member.objects.create(
            genealogy=self.genealogy,
            full_name="Isolated Member",
            gender="unknown",
            created_by=self.owner,
        )

    def test_editor_can_access_relationship_page(self):
        self.client.force_login(self.editor)
        response = self.client.get(
            reverse(
                "genealogy:relationships",
                kwargs={"genealogy_id": self.genealogy.genealogy_id},
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.genealogy.title)

    def test_relationship_page_paginates_large_relation_lists(self):
        for index in range(55):
            child = Member.objects.create(
                genealogy=self.genealogy,
                full_name=f"Paged Child {index}",
                gender="unknown",
                birth_year=2000,
                created_by=self.owner,
            )
            ParentChildRelation.objects.create(
                genealogy=self.genealogy,
                parent_member=self.parent,
                child_member=child,
                parent_role="father",
                created_by=self.owner,
            )
            member_a = Member.objects.create(
                genealogy=self.genealogy,
                full_name=f"Paged Spouse A {index}",
                gender="unknown",
                created_by=self.owner,
            )
            member_b = Member.objects.create(
                genealogy=self.genealogy,
                full_name=f"Paged Spouse B {index}",
                gender="unknown",
                created_by=self.owner,
            )
            Marriage.objects.create(
                genealogy=self.genealogy,
                member_a=member_a,
                member_b=member_b,
                status="married",
                created_by=self.owner,
            )

        self.client.force_login(self.owner)
        response = self.client.get(
            reverse(
                "genealogy:relationships",
                kwargs={"genealogy_id": self.genealogy.genealogy_id},
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["parent_child_page_obj"].paginator.count, 55)
        self.assertEqual(len(response.context["parent_child_relations"]), 50)
        self.assertEqual(response.context["marriage_page_obj"].paginator.count, 55)
        self.assertEqual(len(response.context["marriages"]), 50)
        self.assertContains(response, "下一页")

        response = self.client.get(
            reverse(
                "genealogy:relationships",
                kwargs={"genealogy_id": self.genealogy.genealogy_id},
            ),
            data={"parent_child_page": 2, "marriage_page": 2},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["parent_child_page_obj"].number, 2)
        self.assertEqual(len(response.context["parent_child_relations"]), 5)
        self.assertEqual(response.context["marriage_page_obj"].number, 2)
        self.assertEqual(len(response.context["marriages"]), 5)

    def test_viewer_can_access_relationship_page_read_only(self):
        relation = ParentChildRelation.objects.create(
            genealogy=self.genealogy,
            parent_member=self.parent,
            child_member=self.child,
            parent_role="father",
            created_by=self.owner,
        )

        self.client.force_login(self.viewer)
        response = self.client.get(
            reverse(
                "genealogy:relationships",
                kwargs={"genealogy_id": self.genealogy.genealogy_id},
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["can_edit"])
        self.assertContains(response, self.genealogy.title)
        self.assertContains(response, self.parent.full_name)
        self.assertNotContains(
            response,
            reverse(
                "genealogy:parent-child-create",
                kwargs={"genealogy_id": self.genealogy.genealogy_id},
            ),
        )
        self.assertNotContains(
            response,
            reverse(
                "genealogy:parent-child-update",
                kwargs={
                    "genealogy_id": self.genealogy.genealogy_id,
                    "relation_id": relation.relation_id,
                },
            ),
        )

    def test_owner_can_create_parent_child_relation(self):
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse(
                "genealogy:parent-child-create",
                kwargs={"genealogy_id": self.genealogy.genealogy_id},
            ),
            data={
                "parent_member_id": self.parent.member_id,
                "child_member_id": self.child.member_id,
                "parent_role": "father",
            },
        )

        relation = ParentChildRelation.objects.get(
            genealogy=self.genealogy,
            parent_member=self.parent,
            child_member=self.child,
        )
        self.assertRedirects(
            response,
            reverse(
                "genealogy:relationships",
                kwargs={"genealogy_id": self.genealogy.genealogy_id},
            ),
        )
        self.assertEqual(relation.created_by, self.owner)

    def test_viewer_cannot_create_parent_child_relation(self):
        self.client.force_login(self.viewer)
        response = self.client.post(
            reverse(
                "genealogy:parent-child-create",
                kwargs={"genealogy_id": self.genealogy.genealogy_id},
            ),
            data={
                "parent_member_id": self.parent.member_id,
                "child_member_id": self.child.member_id,
                "parent_role": "father",
            },
        )

        self.assertEqual(response.status_code, 404)
        self.assertFalse(
            ParentChildRelation.objects.filter(
                genealogy=self.genealogy,
                parent_member=self.parent,
                child_member=self.child,
            ).exists()
        )

    def test_editor_can_update_parent_child_relation(self):
        relation = ParentChildRelation.objects.create(
            genealogy=self.genealogy,
            parent_member=self.parent,
            child_member=self.child,
            parent_role="father",
            created_by=self.owner,
        )

        self.client.force_login(self.editor)
        response = self.client.post(
            reverse(
                "genealogy:parent-child-update",
                kwargs={
                    "genealogy_id": self.genealogy.genealogy_id,
                    "relation_id": relation.relation_id,
                },
            ),
            data={
                "parent_member_id": self.mother.member_id,
                "child_member_id": self.child.member_id,
                "parent_role": "mother",
            },
        )

        relation.refresh_from_db()
        self.assertRedirects(
            response,
            reverse(
                "genealogy:relationships",
                kwargs={"genealogy_id": self.genealogy.genealogy_id},
            ),
        )
        self.assertEqual(relation.parent_member, self.mother)
        self.assertEqual(relation.parent_role, "mother")
        self.assertEqual(relation.created_by, self.owner)

    def test_editor_can_delete_parent_child_relation(self):
        relation = ParentChildRelation.objects.create(
            genealogy=self.genealogy,
            parent_member=self.parent,
            child_member=self.child,
            parent_role="father",
            created_by=self.owner,
        )

        self.client.force_login(self.editor)
        response = self.client.post(
            reverse(
                "genealogy:parent-child-delete",
                kwargs={
                    "genealogy_id": self.genealogy.genealogy_id,
                    "relation_id": relation.relation_id,
                },
            )
        )

        self.assertRedirects(
            response,
            reverse(
                "genealogy:relationships",
                kwargs={"genealogy_id": self.genealogy.genealogy_id},
            ),
        )
        self.assertFalse(
            ParentChildRelation.objects.filter(relation_id=relation.relation_id).exists()
        )

    def test_viewer_cannot_update_parent_child_relation(self):
        relation = ParentChildRelation.objects.create(
            genealogy=self.genealogy,
            parent_member=self.parent,
            child_member=self.child,
            parent_role="father",
            created_by=self.owner,
        )

        self.client.force_login(self.viewer)
        response = self.client.post(
            reverse(
                "genealogy:parent-child-update",
                kwargs={
                    "genealogy_id": self.genealogy.genealogy_id,
                    "relation_id": relation.relation_id,
                },
            ),
            data={
                "parent_member_id": self.mother.member_id,
                "child_member_id": self.child.member_id,
                "parent_role": "mother",
            },
        )

        self.assertEqual(response.status_code, 404)

    def test_editor_can_create_marriage_and_order_is_canonical(self):
        self.client.force_login(self.editor)
        response = self.client.post(
            reverse(
                "genealogy:marriage-create",
                kwargs={"genealogy_id": self.genealogy.genealogy_id},
            ),
            data={
                "member_a_id": self.spouse.member_id,
                "member_b_id": self.parent.member_id,
                "status": "married",
                "start_year": 1995,
                "end_year": "",
                "description": "relationship test",
            },
        )

        marriage = Marriage.objects.get(genealogy=self.genealogy)
        self.assertRedirects(
            response,
            reverse(
                "genealogy:relationships",
                kwargs={"genealogy_id": self.genealogy.genealogy_id},
            ),
        )
        self.assertLess(marriage.member_a_id, marriage.member_b_id)
        self.assertEqual(
            {marriage.member_a_id, marriage.member_b_id},
            {self.parent.member_id, self.spouse.member_id},
        )

    def test_owner_can_update_marriage(self):
        marriage = Marriage.objects.create(
            genealogy=self.genealogy,
            member_a=self.parent,
            member_b=self.spouse,
            status="married",
            start_year=1995,
            created_by=self.owner,
        )

        self.client.force_login(self.owner)
        response = self.client.post(
            reverse(
                "genealogy:marriage-update",
                kwargs={
                    "genealogy_id": self.genealogy.genealogy_id,
                    "marriage_id": marriage.marriage_id,
                },
            ),
            data={
                "member_a_id": self.parent.member_id,
                "member_b_id": self.spouse.member_id,
                "status": "divorced",
                "start_year": 1995,
                "end_year": 2010,
                "description": "updated status",
            },
        )

        marriage.refresh_from_db()
        self.assertRedirects(
            response,
            reverse(
                "genealogy:relationships",
                kwargs={"genealogy_id": self.genealogy.genealogy_id},
            ),
        )
        self.assertEqual(marriage.status, "divorced")
        self.assertEqual(marriage.end_year, 2010)
        self.assertEqual(marriage.created_by, self.owner)

    def test_editor_can_delete_marriage(self):
        marriage = Marriage.objects.create(
            genealogy=self.genealogy,
            member_a=self.parent,
            member_b=self.spouse,
            status="married",
            start_year=1995,
            created_by=self.owner,
        )

        self.client.force_login(self.editor)
        response = self.client.post(
            reverse(
                "genealogy:marriage-delete",
                kwargs={
                    "genealogy_id": self.genealogy.genealogy_id,
                    "marriage_id": marriage.marriage_id,
                },
            )
        )

        self.assertRedirects(
            response,
            reverse(
                "genealogy:relationships",
                kwargs={"genealogy_id": self.genealogy.genealogy_id},
            ),
        )
        self.assertFalse(Marriage.objects.filter(marriage_id=marriage.marriage_id).exists())

    def test_stranger_cannot_create_marriage(self):
        self.client.force_login(self.stranger)
        response = self.client.post(
            reverse(
                "genealogy:marriage-create",
                kwargs={"genealogy_id": self.genealogy.genealogy_id},
            ),
            data={
                "member_a_id": self.parent.member_id,
                "member_b_id": self.spouse.member_id,
                "status": "married",
                "start_year": 1995,
                "end_year": "",
                "description": "",
            },
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(Marriage.objects.count(), 0)

    def test_member_query_returns_ancestor_chain(self):
        ParentChildRelation.objects.create(
            genealogy=self.genealogy,
            parent_member=self.grandparent,
            child_member=self.parent,
            parent_role="father",
            created_by=self.owner,
        )
        ParentChildRelation.objects.create(
            genealogy=self.genealogy,
            parent_member=self.parent,
            child_member=self.child,
            parent_role="father",
            created_by=self.owner,
        )
        Marriage.objects.create(
            genealogy=self.genealogy,
            member_a=self.parent,
            member_b=self.spouse,
            status="married",
            start_year=1995,
            created_by=self.owner,
        )

        self.client.force_login(self.viewer)
        response = self.client.get(
            reverse(
                "genealogy:member-query",
                kwargs={"genealogy_id": self.genealogy.genealogy_id},
            ),
            data={"query": "member", "member_id": self.child.member_id},
        )

        self.assertEqual(response.status_code, 200)
        result = response.context["member_query_result"]
        self.assertEqual(result["member"], self.child)
        self.assertEqual(len(result["ancestors"]), 2)
        self.assertEqual(result["ancestors"][0]["full_name"], "Parent Member")
        self.assertEqual(result["ancestors"][1]["full_name"], "Grandparent Member")
        self.assertEqual(result["current_spouses"], [])
        self.assertEqual(len(result["children"]), 0)
        self.assertIn("SELECT", result["member_family_sql"])
        self.assertEqual(result["ancestor_tree"]["root"]["member_id"], self.child.member_id)
        self.assertEqual(
            result["ancestor_tree"]["root"]["parents"][0]["full_name"],
            "Parent Member",
        )

        spouse_response = self.client.get(
            reverse(
                "genealogy:member-query",
                kwargs={"genealogy_id": self.genealogy.genealogy_id},
            ),
            data={"query": "member", "member_id": self.parent.member_id},
        )
        spouse_result = spouse_response.context["member_query_result"]
        self.assertEqual(spouse_result["current_spouses"][0]["full_name"], "Spouse Member")
        self.assertEqual(spouse_result["children"][0]["full_name"], "Child Member")

    def test_member_query_rejects_member_outside_genealogy(self):
        external_genealogy = Genealogy.objects.create(
            title="External",
            surname="Ext",
            created_by=self.owner,
        )
        external_member = Member.objects.create(
            genealogy=external_genealogy,
            full_name="External Member",
            created_by=self.owner,
        )

        self.client.force_login(self.viewer)
        response = self.client.get(
            reverse(
                "genealogy:member-query",
                kwargs={"genealogy_id": self.genealogy.genealogy_id},
            ),
            data={"query": "member", "member_id": external_member.member_id},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("member_id", response.context["member_lookup_form"].errors)
        self.assertIsNone(response.context["member_query_result"])

    def test_kinship_path_query_returns_shortest_path(self):
        ParentChildRelation.objects.create(
            genealogy=self.genealogy,
            parent_member=self.parent,
            child_member=self.child,
            parent_role="father",
            created_by=self.owner,
        )
        Marriage.objects.create(
            genealogy=self.genealogy,
            member_a=self.parent,
            member_b=self.spouse,
            status="married",
            start_year=1995,
            created_by=self.owner,
        )

        self.client.force_login(self.viewer)
        response = self.client.get(
            reverse(
                "genealogy:member-query",
                kwargs={"genealogy_id": self.genealogy.genealogy_id},
            ),
            data={
                "query": "path",
                "source_member_id": self.child.member_id,
                "target_member_id": self.spouse.member_id,
            },
        )

        self.assertEqual(response.status_code, 200)
        result = response.context["kinship_path_result"]
        self.assertTrue(result["found"])
        self.assertEqual(result["depth"], 2)
        self.assertEqual(result["steps"][0]["from_member"], self.child)
        self.assertEqual(result["steps"][0]["to_member"], self.parent)
        self.assertEqual(result["steps"][0]["relation_label"], "父亲")
        self.assertEqual(result["steps"][1]["to_member"], self.spouse)
        self.assertEqual(result["steps"][1]["relation_label"], "配偶")

    def test_kinship_path_query_handles_disconnected_members(self):
        self.client.force_login(self.viewer)
        response = self.client.get(
            reverse(
                "genealogy:member-query",
                kwargs={"genealogy_id": self.genealogy.genealogy_id},
            ),
            data={
                "query": "path",
                "source_member_id": self.child.member_id,
                "target_member_id": self.isolated.member_id,
            },
        )

        self.assertEqual(response.status_code, 200)
        result = response.context["kinship_path_result"]
        self.assertFalse(result["found"])
        self.assertIsNone(result["depth"])
        self.assertEqual(result["steps"], [])


class MemberArchiveAndAnalyticsTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="archive_owner",
            display_name="Archive Owner",
            email="archive_owner@example.com",
            password="StrongPass123!",
        )
        self.editor = User.objects.create_user(
            username="archive_editor",
            display_name="Archive Editor",
            email="archive_editor@example.com",
            password="StrongPass123!",
        )
        self.viewer = User.objects.create_user(
            username="archive_viewer",
            display_name="Archive Viewer",
            email="archive_viewer@example.com",
            password="StrongPass123!",
        )
        self.genealogy = Genealogy.objects.create(
            title="Archive Demo",
            surname="Demo",
            created_by=self.owner,
        )
        editor_invitation = GenealogyInvitation.objects.create(
            genealogy=self.genealogy,
            inviter_user=self.owner,
            invitee_user=self.editor,
            status=InvitationStatus.ACCEPTED,
        )
        viewer_invitation = GenealogyInvitation.objects.create(
            genealogy=self.genealogy,
            inviter_user=self.owner,
            invitee_user=self.viewer,
            status=InvitationStatus.ACCEPTED,
        )
        GenealogyCollaborator.objects.create(
            genealogy=self.genealogy,
            user=self.editor,
            source_invitation=editor_invitation,
            role=CollaboratorRole.EDITOR,
            added_by=self.owner,
        )
        GenealogyCollaborator.objects.create(
            genealogy=self.genealogy,
            user=self.viewer,
            source_invitation=viewer_invitation,
            role=CollaboratorRole.VIEWER,
            added_by=self.owner,
        )
        self.root = Member.objects.create(
            genealogy=self.genealogy,
            full_name="Root Member",
            gender="male",
            birth_year=1930,
            death_year=2000,
            is_living=False,
            created_by=self.owner,
        )
        self.child = Member.objects.create(
            genealogy=self.genealogy,
            full_name="Child Member",
            gender="male",
            birth_year=1960,
            death_year=2020,
            is_living=False,
            created_by=self.owner,
        )
        self.spouse = Member.objects.create(
            genealogy=self.genealogy,
            full_name="Spouse Member",
            gender="female",
            birth_year=1965,
            is_living=True,
            created_by=self.owner,
        )
        self.peer = Member.objects.create(
            genealogy=self.genealogy,
            full_name="Peer Member",
            gender="female",
            birth_year=1970,
            death_year=2010,
            is_living=False,
            created_by=self.owner,
        )
        self.grandchild = Member.objects.create(
            genealogy=self.genealogy,
            full_name="Grandchild Member",
            gender="female",
            birth_year=1990,
            is_living=True,
            created_by=self.owner,
        )
        self.unmarried_old_male = Member.objects.create(
            genealogy=self.genealogy,
            full_name="Old Single Member",
            gender="male",
            birth_year=1950,
            is_living=True,
            created_by=self.owner,
        )
        self.disposable_member = Member.objects.create(
            genealogy=self.genealogy,
            full_name="Disposable Member",
            gender="unknown",
            is_living=True,
            created_by=self.owner,
        )
        ParentChildRelation.objects.create(
            genealogy=self.genealogy,
            parent_member=self.root,
            child_member=self.child,
            parent_role="father",
            created_by=self.owner,
        )
        ParentChildRelation.objects.create(
            genealogy=self.genealogy,
            parent_member=self.root,
            child_member=self.peer,
            parent_role="father",
            created_by=self.owner,
        )
        ParentChildRelation.objects.create(
            genealogy=self.genealogy,
            parent_member=self.child,
            child_member=self.grandchild,
            parent_role="father",
            created_by=self.owner,
        )
        Marriage.objects.create(
            genealogy=self.genealogy,
            member_a=self.child,
            member_b=self.spouse,
            status="married",
            start_year=1988,
            created_by=self.owner,
        )

    def test_viewer_can_access_member_detail(self):
        self.client.force_login(self.viewer)
        response = self.client.get(
            reverse(
                "genealogy:member-detail",
                kwargs={
                    "genealogy_id": self.genealogy.genealogy_id,
                    "member_id": self.child.member_id,
                },
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["member"], self.child)

    def test_editor_can_update_member(self):
        self.client.force_login(self.editor)
        response = self.client.post(
            reverse(
                "genealogy:member-update",
                kwargs={
                    "genealogy_id": self.genealogy.genealogy_id,
                    "member_id": self.disposable_member.member_id,
                },
            ),
            data={
                "full_name": "Disposable Member Updated",
                "surname": "Demo",
                "given_name": "Updated",
                "gender": "female",
                "birth_year": 1988,
                "death_year": "",
                "is_living": "on",
                "generation_label": "景",
                "seniority_text": "长女",
                "branch_name": "West Branch",
                "biography": "updated profile",
            },
        )

        self.disposable_member.refresh_from_db()
        self.assertRedirects(
            response,
            reverse(
                "genealogy:member-detail",
                kwargs={
                    "genealogy_id": self.genealogy.genealogy_id,
                    "member_id": self.disposable_member.member_id,
                },
            ),
        )
        self.assertEqual(self.disposable_member.full_name, "Disposable Member Updated")
        self.assertEqual(self.disposable_member.branch_name, "West Branch")

    def test_editor_can_delete_member(self):
        self.client.force_login(self.editor)
        response = self.client.post(
            reverse(
                "genealogy:member-delete",
                kwargs={
                    "genealogy_id": self.genealogy.genealogy_id,
                    "member_id": self.disposable_member.member_id,
                },
            )
        )

        self.assertRedirects(
            response,
            reverse(
                "genealogy:member-list",
                kwargs={"genealogy_id": self.genealogy.genealogy_id},
            ),
        )
        self.assertFalse(
            Member.objects.filter(member_id=self.disposable_member.member_id).exists()
        )

    def test_viewer_cannot_delete_member(self):
        self.client.force_login(self.viewer)
        response = self.client.post(
            reverse(
                "genealogy:member-delete",
                kwargs={
                    "genealogy_id": self.genealogy.genealogy_id,
                    "member_id": self.disposable_member.member_id,
                },
            )
        )

        self.assertEqual(response.status_code, 404)
        self.assertTrue(
            Member.objects.filter(member_id=self.disposable_member.member_id).exists()
        )

    def test_editor_can_create_update_and_delete_member_event(self):
        self.client.force_login(self.editor)
        create_response = self.client.post(
            reverse(
                "genealogy:member-event-create",
                kwargs={
                    "genealogy_id": self.genealogy.genealogy_id,
                    "member_id": self.child.member_id,
                },
            ),
            data={
                "event_type": "occupation",
                "event_year": 1995,
                "place_text": "Wuhan",
                "description": "served as local teacher",
            },
        )

        event = MemberEvent.objects.get(member=self.child)
        self.assertRedirects(
            create_response,
            reverse(
                "genealogy:member-detail",
                kwargs={
                    "genealogy_id": self.genealogy.genealogy_id,
                    "member_id": self.child.member_id,
                },
            ),
        )
        self.assertEqual(event.recorded_by, self.editor)

        update_response = self.client.post(
            reverse(
                "genealogy:member-event-update",
                kwargs={
                    "genealogy_id": self.genealogy.genealogy_id,
                    "member_id": self.child.member_id,
                    "event_id": event.event_id,
                },
            ),
            data={
                "event_type": "achievement",
                "event_year": 1998,
                "place_text": "Beijing",
                "description": "earned county honor",
            },
        )

        event.refresh_from_db()
        self.assertRedirects(
            update_response,
            reverse(
                "genealogy:member-detail",
                kwargs={
                    "genealogy_id": self.genealogy.genealogy_id,
                    "member_id": self.child.member_id,
                },
            ),
        )
        self.assertEqual(event.event_type, "achievement")
        self.assertEqual(event.place_text, "Beijing")

        delete_response = self.client.post(
            reverse(
                "genealogy:member-event-delete",
                kwargs={
                    "genealogy_id": self.genealogy.genealogy_id,
                    "member_id": self.child.member_id,
                    "event_id": event.event_id,
                },
            )
        )

        self.assertRedirects(
            delete_response,
            reverse(
                "genealogy:member-detail",
                kwargs={
                    "genealogy_id": self.genealogy.genealogy_id,
                    "member_id": self.child.member_id,
                },
            ),
        )
        self.assertFalse(MemberEvent.objects.filter(event_id=event.event_id).exists())

    def test_viewer_cannot_create_member_event(self):
        self.client.force_login(self.viewer)
        response = self.client.post(
            reverse(
                "genealogy:member-event-create",
                kwargs={
                    "genealogy_id": self.genealogy.genealogy_id,
                    "member_id": self.child.member_id,
                },
            ),
            data={
                "event_type": "migration",
                "event_year": 1980,
                "place_text": "Hubei",
                "description": "moved residence",
            },
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(MemberEvent.objects.count(), 0)

    def test_analytics_page_returns_expected_statistics(self):
        self.client.force_login(self.viewer)
        response = self.client.get(
            reverse(
                "genealogy:analytics",
                kwargs={"genealogy_id": self.genealogy.genealogy_id},
            )
        )

        self.assertEqual(response.status_code, 200)
        analytics = response.context["analytics"]
        self.assertEqual(analytics["gender_summary"]["total_members"], 7)
        self.assertEqual(analytics["gender_summary"]["male_members"], 3)
        self.assertEqual(analytics["gender_summary"]["female_members"], 3)
        self.assertEqual(analytics["gender_summary"]["unknown_gender_members"], 1)
        self.assertEqual(analytics["generation_lifespan"]["generation_depth"], 1)
        self.assertEqual(
            analytics["unmarried_males_over_50"][0]["full_name"],
            "Old Single Member",
        )
        early_birth_names = {row["full_name"] for row in analytics["early_birth_members"]}
        self.assertIn("Child Member", early_birth_names)

    def test_tree_preview_returns_descendant_tree(self):
        self.client.force_login(self.viewer)
        response = self.client.get(
            reverse(
                "genealogy:tree-preview",
                kwargs={"genealogy_id": self.genealogy.genealogy_id},
            ),
            data={
                "root_member_id": self.root.member_id,
                "max_depth": 4,
            },
        )

        self.assertEqual(response.status_code, 200)
        tree_result = response.context["tree_result"]
        self.assertEqual(tree_result["root"]["member_id"], self.root.member_id)
        flat_names = {row["full_name"] for row in tree_result["flat_nodes"]}
        self.assertIn("Child Member", flat_names)
        self.assertIn("Grandchild Member", flat_names)
        self.assertNotIn("Old Single Member", flat_names)
        self.assertEqual(response.context["selected_root_member"], self.root)

    def test_branch_export_view_returns_zip_archive(self):
        self.client.force_login(self.viewer)
        response = self.client.post(
            reverse(
                "genealogy:export-branch",
                kwargs={"genealogy_id": self.genealogy.genealogy_id},
            ),
            data={"root_member_id": self.root.member_id},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/zip")
        self.assertIn(
            f"genealogy-{self.genealogy.genealogy_id}-branch-{self.root.member_id}.zip",
            response["Content-Disposition"],
        )
        with ZipFile(BytesIO(response.content)) as archive:
            archive_names = set(archive.namelist())
            self.assertSetEqual(
                archive_names,
                {
                    "branch_members.csv",
                    "branch_parent_child_relations.csv",
                    "branch_marriages.csv",
                },
            )
            members_csv = archive.read("branch_members.csv").decode("utf-8")
            relations_csv = archive.read(
                "branch_parent_child_relations.csv"
            ).decode("utf-8")

        self.assertIn("Root Member", members_csv)
        self.assertIn("Grandchild Member", members_csv)
        self.assertIn(str(self.root.member_id), relations_csv)

    def test_tree_preview_rejects_member_outside_genealogy(self):
        external_genealogy = Genealogy.objects.create(
            title="External Tree",
            surname="Ext",
            created_by=self.owner,
        )
        external_member = Member.objects.create(
            genealogy=external_genealogy,
            full_name="External Root",
            created_by=self.owner,
        )

        self.client.force_login(self.viewer)
        response = self.client.get(
            reverse(
                "genealogy:tree-preview",
                kwargs={"genealogy_id": self.genealogy.genealogy_id},
            ),
            data={
                "root_member_id": external_member.member_id,
                "max_depth": 4,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("root_member_id", response.context["tree_form"].errors)
        self.assertIsNone(response.context["tree_result"])

    def test_tree_preview_accepts_course_depth_limit(self):
        self.client.force_login(self.viewer)
        response = self.client.get(
            reverse(
                "genealogy:tree-preview",
                kwargs={"genealogy_id": self.genealogy.genealogy_id},
            ),
            data={
                "root_member_id": self.root.member_id,
                "max_depth": 30,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["tree_form"].errors)
        self.assertIsNotNone(response.context["tree_result"])

    def test_genealogy_api_requires_login(self):
        response = self.client.get(reverse("genealogy_api:genealogy-list"))

        self.assertEqual(response.status_code, 401)

    def test_genealogy_api_returns_accessible_genealogies(self):
        self.client.force_login(self.viewer)
        response = self.client.get(reverse("genealogy_api:genealogy-list"))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload["genealogies"]), 1)
        self.assertEqual(
            payload["genealogies"][0]["genealogy_id"],
            self.genealogy.genealogy_id,
        )
        self.assertEqual(payload["genealogies"][0]["role"], "viewer")

    def test_member_search_api_finds_root_candidates(self):
        self.client.force_login(self.viewer)
        response = self.client.get(
            reverse(
                "genealogy_api:member-search",
                kwargs={"genealogy_id": self.genealogy.genealogy_id},
            ),
            data={"q": "Root"},
        )

        self.assertEqual(response.status_code, 200)
        member_ids = {member["member_id"] for member in response.json()["members"]}
        self.assertIn(self.root.member_id, member_ids)

    def test_member_search_api_defaults_to_bloodline_roots(self):
        external_mother = Member.objects.create(
            genealogy=self.genealogy,
            full_name="External Mother",
            surname="External",
            gender="female",
            birth_year=1935,
            created_by=self.owner,
        )
        ParentChildRelation.objects.create(
            genealogy=self.genealogy,
            parent_member=external_mother,
            child_member=self.child,
            parent_role="mother",
            created_by=self.owner,
        )

        self.client.force_login(self.viewer)
        response = self.client.get(
            reverse(
                "genealogy_api:member-search",
                kwargs={"genealogy_id": self.genealogy.genealogy_id},
            )
        )

        self.assertEqual(response.status_code, 200)
        member_ids = {member["member_id"] for member in response.json()["members"]}
        self.assertIn(self.root.member_id, member_ids)
        self.assertNotIn(external_mother.member_id, member_ids)

    def test_descendant_map_viewport_returns_partial_tree(self):
        self.client.force_login(self.viewer)
        response = self.client.get(
            reverse(
                "genealogy_api:descendant-map-viewport",
                kwargs={"genealogy_id": self.genealogy.genealogy_id},
            ),
            data={
                "root_member_id": self.root.member_id,
                "max_depth": 4,
                "x_min": -10,
                "x_max": 10,
                "y_min": -10,
                "y_max": 10,
                "padding": 0,
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["total_node_count"], 4)
        self.assertTrue(payload["has_more"])
        self.assertEqual(
            [node["member_id"] for node in payload["nodes"]],
            [self.root.member_id],
        )
        self.assertEqual(payload["edges"], [])

    def test_descendant_map_viewport_returns_edges_and_hidden_child_flags(self):
        hidden_child = Member.objects.create(
            genealogy=self.genealogy,
            full_name="Hidden Young Member",
            gender="male",
            birth_year=2020,
            is_living=True,
            created_by=self.owner,
        )
        ParentChildRelation.objects.create(
            genealogy=self.genealogy,
            parent_member=self.grandchild,
            child_member=hidden_child,
            parent_role="mother",
            created_by=self.owner,
        )

        self.client.force_login(self.viewer)
        response = self.client.get(
            reverse(
                "genealogy_api:descendant-map-viewport",
                kwargs={"genealogy_id": self.genealogy.genealogy_id},
            ),
            data={
                "root_member_id": self.root.member_id,
                "max_depth": 2,
                "x_min": -500,
                "x_max": 1200,
                "y_min": -500,
                "y_max": 1200,
                "padding": 0,
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        edge_pairs = {(edge["source"], edge["target"]) for edge in payload["edges"]}
        self.assertIn((self.root.member_id, self.child.member_id), edge_pairs)
        self.assertIn((self.root.member_id, self.peer.member_id), edge_pairs)
        self.assertIn((self.child.member_id, self.grandchild.member_id), edge_pairs)
        grandchild_node = next(
            node
            for node in payload["nodes"]
            if node["member_id"] == self.grandchild.member_id
        )
        self.assertTrue(grandchild_node["has_hidden_children"])

    def test_descendant_map_viewport_rejects_member_outside_genealogy(self):
        external_genealogy = Genealogy.objects.create(
            title="External API Tree",
            surname="Ext",
            created_by=self.owner,
        )
        external_member = Member.objects.create(
            genealogy=external_genealogy,
            full_name="External API Root",
            created_by=self.owner,
        )

        self.client.force_login(self.viewer)
        response = self.client.get(
            reverse(
                "genealogy_api:descendant-map-viewport",
                kwargs={"genealogy_id": self.genealogy.genealogy_id},
            ),
            data={"root_member_id": external_member.member_id, "max_depth": 4},
        )

        self.assertEqual(response.status_code, 404)

    def test_descendant_map_layout_is_stable_and_cycle_safe(self):
        cycle_root = Member.objects.create(
            genealogy=self.genealogy,
            full_name="Cycle Root",
            gender="male",
            is_living=True,
            created_by=self.owner,
        )
        cycle_child = Member.objects.create(
            genealogy=self.genealogy,
            full_name="Cycle Child",
            gender="male",
            is_living=True,
            created_by=self.owner,
        )
        cycle_grandchild = Member.objects.create(
            genealogy=self.genealogy,
            full_name="Cycle Grandchild",
            gender="female",
            is_living=True,
            created_by=self.owner,
        )
        ParentChildRelation.objects.create(
            genealogy=self.genealogy,
            parent_member=cycle_root,
            child_member=cycle_child,
            parent_role="father",
            created_by=self.owner,
        )
        ParentChildRelation.objects.create(
            genealogy=self.genealogy,
            parent_member=cycle_child,
            child_member=cycle_grandchild,
            parent_role="father",
            created_by=self.owner,
        )
        with self.assertRaises(DatabaseError), transaction.atomic():
            ParentChildRelation.objects.create(
                genealogy=self.genealogy,
                parent_member=cycle_grandchild,
                child_member=cycle_root,
                parent_role="mother",
                created_by=self.owner,
            )

        first = fetch_descendant_map_viewport(
            genealogy_id=self.genealogy.genealogy_id,
            root_member_id=cycle_root.member_id,
            max_depth=30,
            x_min=-1000,
            x_max=3000,
            y_min=-1000,
            y_max=3000,
            padding=0,
        )
        second = fetch_descendant_map_viewport(
            genealogy_id=self.genealogy.genealogy_id,
            root_member_id=cycle_root.member_id,
            max_depth=30,
            x_min=-1000,
            x_max=3000,
            y_min=-1000,
            y_max=3000,
            padding=0,
        )

        self.assertIsNotNone(first)
        self.assertEqual(first["nodes"], second["nodes"])
        member_ids = {node["member_id"] for node in first["nodes"]}
        self.assertEqual(
            member_ids,
            {
                cycle_root.member_id,
                cycle_child.member_id,
                cycle_grandchild.member_id,
            },
        )

    def test_prepare_coursework_artifacts_creates_sample_and_manifest_only(self):
        with TemporaryDirectory() as temp_dir:
            call_command("prepare_coursework_artifacts", output_dir=temp_dir)

            output_dir = Path(temp_dir)
            sample_csv = output_dir / "sample-import" / "members.csv"
            manifest = output_dir / "artifact-manifest.md"

            self.assertTrue(sample_csv.exists())
            self.assertTrue(manifest.exists())
            self.assertIn(
                "full_name,surname,given_name",
                sample_csv.read_text(encoding="utf-8"),
            )
            manifest_text = manifest.read_text(encoding="utf-8")
            self.assertIn("Password: omitted intentionally", manifest_text)
            self.assertIn("Genealogy ID: `not selected`", manifest_text)
            self.assertFalse((output_dir / "branch-export").exists())
            self.assertFalse((output_dir / "benchmarks" / "parent_lookup.md").exists())

    def test_prepare_coursework_artifacts_rejects_missing_genealogy(self):
        with TemporaryDirectory() as temp_dir:
            with self.assertRaisesMessage(CommandError, "Genealogy 999999 does not exist"):
                call_command(
                    "prepare_coursework_artifacts",
                    output_dir=temp_dir,
                    genealogy_id=999999,
                )

    def test_export_and_benchmark_reject_missing_root_member(self):
        with TemporaryDirectory() as temp_dir:
            with self.assertRaisesMessage(CommandError, "Root member 999999"):
                call_command(
                    "export_branch_copy",
                    genealogy_id=self.genealogy.genealogy_id,
                    root_member_id=999999,
                    output_dir=temp_dir,
                )

            with self.assertRaisesMessage(CommandError, "Root member 999999"):
                call_command(
                    "benchmark_parent_lookup",
                    genealogy_id=self.genealogy.genealogy_id,
                    root_member_id=999999,
                    output=str(Path(temp_dir) / "parent_lookup.md"),
                )

    def test_prepare_coursework_artifacts_can_create_smoke_outputs(self):
        with TemporaryDirectory() as temp_dir:
            call_command(
                "prepare_coursework_artifacts",
                output_dir=temp_dir,
                create_smoke_data=True,
                smoke_total_members=12,
                smoke_generations=5,
                smoke_batch_size=6,
            )

            output_dir = Path(temp_dir)
            self.assertTrue((output_dir / "sample-import" / "members.csv").exists())
            self.assertTrue((output_dir / "branch-export" / "branch_members.csv").exists())
            self.assertTrue(
                (
                    output_dir
                    / "branch-export"
                    / "branch_parent_child_relations.csv"
                ).exists()
            )
            self.assertTrue((output_dir / "branch-export" / "branch_marriages.csv").exists())
            self.assertTrue((output_dir / "benchmarks" / "parent_lookup.md").exists())
            manifest_text = (output_dir / "artifact-manifest.md").read_text(
                encoding="utf-8"
            )
            self.assertIn("Smoke Data", manifest_text)
            self.assertIn("Parent lookup benchmark", manifest_text)


class CourseDatasetGenerationTests(TestCase):
    def test_generator_clears_existing_and_avoids_parent_child_isolates(self):
        stale_owner = User.objects.create_user(
            username="stale_owner",
            display_name="Stale Owner",
            email="stale-owner@example.com",
            password="StrongPass123!",
        )
        stale_genealogy = Genealogy.objects.create(
            title="Stale Genealogy",
            surname="Stale",
            created_by=stale_owner,
        )

        result = generate_course_dataset(
            genealogy_count=2,
            total_members=80,
            large_members=40,
            generations=10,
            batch_size=25,
            username="course_test_operator",
            title_prefix="Course Genealogy",
            surname_prefix="Course",
            seed=20260416,
            clear_existing=True,
        )

        genealogy_ids = [item["genealogy_id"] for item in result["results"]]
        generated_member_ids = set(
            Member.objects.filter(genealogy_id__in=genealogy_ids).values_list(
                "member_id",
                flat=True,
            )
        )
        connected_parent_ids = set(
            ParentChildRelation.objects.filter(
                genealogy_id__in=genealogy_ids,
            ).values_list("parent_member_id", flat=True)
        )
        connected_child_ids = set(
            ParentChildRelation.objects.filter(
                genealogy_id__in=genealogy_ids,
            ).values_list("child_member_id", flat=True)
        )

        self.assertFalse(
            Genealogy.objects.filter(genealogy_id=stale_genealogy.genealogy_id).exists()
        )
        self.assertEqual(result["genealogy_count"], 2)
        self.assertEqual(result["total_members"], 80)
        self.assertSetEqual(
            generated_member_ids - (connected_parent_ids | connected_child_ids),
            set(),
        )
        max_father_children = (
            ParentChildRelation.objects.filter(
                genealogy_id__in=genealogy_ids,
                parent_role="father",
            )
            .values("parent_member_id")
            .annotate(child_count=Count("child_member_id"))
            .order_by("-child_count")
            .first()["child_count"]
        )
        self.assertLessEqual(max_father_children, 6)
        generated_names = list(
            Member.objects.filter(genealogy_id__in=genealogy_ids).values_list(
                "full_name",
                flat=True,
            )
        )
        self.assertTrue(all(len(name) == 3 for name in generated_names))


class BackendEndpointSmokeTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="smoke_owner",
            display_name="Smoke Owner",
            email="smoke-owner@example.com",
            password="StrongPass123!",
        )
        self.editor = User.objects.create_user(
            username="smoke_editor",
            display_name="Smoke Editor",
            email="smoke-editor@example.com",
            password="StrongPass123!",
        )
        self.viewer = User.objects.create_user(
            username="smoke_viewer",
            display_name="Smoke Viewer",
            email="smoke-viewer@example.com",
            password="StrongPass123!",
        )
        self.invitee = User.objects.create_user(
            username="smoke_invitee",
            display_name="Smoke Invitee",
            email="smoke-invitee@example.com",
            password="StrongPass123!",
        )
        self.genealogy = Genealogy.objects.create(
            title="Smoke Genealogy",
            surname="Smoke",
            compiled_at=2026,
            description="Backend endpoint smoke fixture",
            created_by=self.owner,
        )
        editor_invitation = GenealogyInvitation.objects.create(
            genealogy=self.genealogy,
            inviter_user=self.owner,
            invitee_user=self.editor,
            status=InvitationStatus.ACCEPTED,
        )
        self.editor_collaborator = GenealogyCollaborator.objects.create(
            genealogy=self.genealogy,
            user=self.editor,
            source_invitation=editor_invitation,
            role=CollaboratorRole.EDITOR,
            added_by=self.owner,
        )
        viewer_invitation = GenealogyInvitation.objects.create(
            genealogy=self.genealogy,
            inviter_user=self.owner,
            invitee_user=self.viewer,
            status=InvitationStatus.ACCEPTED,
        )
        GenealogyCollaborator.objects.create(
            genealogy=self.genealogy,
            user=self.viewer,
            source_invitation=viewer_invitation,
            role=CollaboratorRole.VIEWER,
            added_by=self.owner,
        )
        self.father = self.create_member(
            "Smoke Father",
            gender="male",
            birth_year=1940,
            death_year=2010,
            is_living=False,
        )
        self.mother = self.create_member(
            "Smoke Mother",
            gender="female",
            birth_year=1942,
            death_year=2015,
            is_living=False,
        )
        self.child = self.create_member(
            "Smoke Child",
            gender="male",
            birth_year=1970,
        )
        self.spouse = self.create_member(
            "Smoke Spouse",
            gender="female",
            birth_year=1972,
        )
        self.grandchild = self.create_member(
            "Smoke Grandchild",
            gender="female",
            birth_year=2000,
        )
        self.father_relation = ParentChildRelation.objects.create(
            genealogy=self.genealogy,
            parent_member=self.father,
            child_member=self.child,
            parent_role="father",
            created_by=self.owner,
        )
        ParentChildRelation.objects.create(
            genealogy=self.genealogy,
            parent_member=self.mother,
            child_member=self.child,
            parent_role="mother",
            created_by=self.owner,
        )
        self.child_relation = ParentChildRelation.objects.create(
            genealogy=self.genealogy,
            parent_member=self.child,
            child_member=self.grandchild,
            parent_role="father",
            created_by=self.owner,
        )
        self.marriage = Marriage.objects.create(
            genealogy=self.genealogy,
            member_a=self.child,
            member_b=self.spouse,
            status="married",
            start_year=1995,
            created_by=self.owner,
        )
        self.event = MemberEvent.objects.create(
            genealogy=self.genealogy,
            member=self.child,
            event_type="residence",
            event_year=1990,
            place_text="Wuhan",
            description="Smoke event",
            recorded_by=self.owner,
        )

    def create_member(
        self,
        full_name,
        *,
        gender="unknown",
        birth_year=None,
        death_year=None,
        is_living=True,
    ):
        return Member.objects.create(
            genealogy=self.genealogy,
            full_name=full_name,
            surname="Smoke",
            given_name=full_name.replace("Smoke ", ""),
            gender=gender,
            birth_year=birth_year,
            death_year=death_year,
            is_living=is_living,
            branch_name="main",
            created_by=self.owner,
        )

    def member_form_data(self, full_name, **overrides):
        data = {
            "full_name": full_name,
            "surname": "Smoke",
            "given_name": full_name.replace("Smoke ", ""),
            "gender": "male",
            "birth_year": 1988,
            "death_year": "",
            "is_living": "on",
            "generation_label": "",
            "seniority_text": "",
            "branch_name": "main",
            "biography": "smoke",
        }
        data.update(overrides)
        return data

    def assert_not_server_error(self, response, label):
        self.assertLess(
            response.status_code,
            500,
            f"{label} returned HTTP {response.status_code}",
        )

    def test_public_and_authenticated_get_routes_do_not_error(self):
        public_routes = [
            ("health", reverse("healthcheck")),
            ("login", reverse("accounts:login")),
            ("register", reverse("accounts:register")),
            ("admin", "/admin/"),
        ]
        for label, url in public_routes:
            with self.subTest(label=label):
                self.assert_not_server_error(self.client.get(url), label)

        self.client.force_login(self.owner)
        authenticated_routes = [
            ("dashboard", reverse("genealogy:dashboard")),
            ("spa", reverse("genealogy:spa")),
            (
                "spa-catchall",
                reverse("genealogy:spa-catchall", kwargs={"spa_path": "genealogies/1/map"}),
            ),
            ("genealogy-create", reverse("genealogy:create")),
            (
                "genealogy-detail",
                reverse("genealogy:detail", kwargs={"genealogy_id": self.genealogy.genealogy_id}),
            ),
            (
                "genealogy-update",
                reverse("genealogy:update", kwargs={"genealogy_id": self.genealogy.genealogy_id}),
            ),
            (
                "genealogy-analytics",
                reverse(
                    "genealogy:analytics",
                    kwargs={"genealogy_id": self.genealogy.genealogy_id},
                ),
            ),
            (
                "tree-preview",
                reverse(
                    "genealogy:tree-preview",
                    kwargs={"genealogy_id": self.genealogy.genealogy_id},
                )
                + f"?root_member_id={self.father.member_id}&max_depth=4",
            ),
            (
                "member-list",
                reverse(
                    "genealogy:member-list",
                    kwargs={"genealogy_id": self.genealogy.genealogy_id},
                )
                + "?q=Smoke",
            ),
            (
                "member-create",
                reverse(
                    "genealogy:member-create",
                    kwargs={"genealogy_id": self.genealogy.genealogy_id},
                ),
            ),
            (
                "member-detail",
                reverse(
                    "genealogy:member-detail",
                    kwargs={
                        "genealogy_id": self.genealogy.genealogy_id,
                        "member_id": self.child.member_id,
                    },
                ),
            ),
            (
                "member-update",
                reverse(
                    "genealogy:member-update",
                    kwargs={
                        "genealogy_id": self.genealogy.genealogy_id,
                        "member_id": self.child.member_id,
                    },
                ),
            ),
            (
                "member-event-create",
                reverse(
                    "genealogy:member-event-create",
                    kwargs={
                        "genealogy_id": self.genealogy.genealogy_id,
                        "member_id": self.child.member_id,
                    },
                ),
            ),
            (
                "member-event-update",
                reverse(
                    "genealogy:member-event-update",
                    kwargs={
                        "genealogy_id": self.genealogy.genealogy_id,
                        "member_id": self.child.member_id,
                        "event_id": self.event.event_id,
                    },
                ),
            ),
            (
                "member-query",
                reverse(
                    "genealogy:member-query",
                    kwargs={"genealogy_id": self.genealogy.genealogy_id},
                )
                + f"?query=member&member_id={self.child.member_id}",
            ),
            (
                "kinship-query",
                reverse(
                    "genealogy:member-query",
                    kwargs={"genealogy_id": self.genealogy.genealogy_id},
                )
                + (
                    f"?query=path&source_member_id={self.father.member_id}"
                    f"&target_member_id={self.grandchild.member_id}"
                ),
            ),
            (
                "relationships",
                reverse(
                    "genealogy:relationships",
                    kwargs={"genealogy_id": self.genealogy.genealogy_id},
                ),
            ),
            (
                "parent-child-update",
                reverse(
                    "genealogy:parent-child-update",
                    kwargs={
                        "genealogy_id": self.genealogy.genealogy_id,
                        "relation_id": self.father_relation.relation_id,
                    },
                ),
            ),
            (
                "marriage-update",
                reverse(
                    "genealogy:marriage-update",
                    kwargs={
                        "genealogy_id": self.genealogy.genealogy_id,
                        "marriage_id": self.marriage.marriage_id,
                    },
                ),
            ),
            (
                "collaboration",
                reverse(
                    "genealogy:collaboration",
                    kwargs={"genealogy_id": self.genealogy.genealogy_id},
                ),
            ),
        ]
        for label, url in authenticated_routes:
            with self.subTest(label=label):
                self.assert_not_server_error(self.client.get(url), label)

    def test_json_api_routes_do_not_error(self):
        self.assertEqual(self.client.get(reverse("genealogy_api:genealogy-list")).status_code, 401)

        self.client.force_login(self.viewer)
        api_routes = [
            ("genealogy-list", reverse("genealogy_api:genealogy-list"), {}),
            (
                "member-search",
                reverse(
                    "genealogy_api:member-search",
                    kwargs={"genealogy_id": self.genealogy.genealogy_id},
                ),
                {"q": "Smoke", "limit": 5},
            ),
            (
                "descendant-map-viewport",
                reverse(
                    "genealogy_api:descendant-map-viewport",
                    kwargs={"genealogy_id": self.genealogy.genealogy_id},
                ),
                {
                    "root_member_id": self.father.member_id,
                    "max_depth": 4,
                    "x_min": -1000,
                    "x_max": 2000,
                    "y_min": -1000,
                    "y_max": 2000,
                    "padding": 0,
                },
            ),
            (
                "parent-lookup-benchmark",
                reverse(
                    "genealogy_api:parent-lookup-benchmark",
                    kwargs={"genealogy_id": self.genealogy.genealogy_id},
                ),
                {"root_member_id": self.father.member_id},
            ),
        ]
        for label, url, data in api_routes:
            with self.subTest(label=label):
                response = self.client.get(url, data=data)
                self.assert_not_server_error(response, label)
                self.assertEqual(response.status_code, 200)

        missing_root_response = self.client.get(
            reverse(
                "genealogy_api:descendant-map-viewport",
                kwargs={"genealogy_id": self.genealogy.genealogy_id},
            )
        )
        self.assertEqual(missing_root_response.status_code, 400)

    def test_mutating_routes_accept_valid_posts_without_server_error(self):
        login_client = Client()
        response = login_client.post(
            reverse("accounts:login"),
            data={"username": self.owner.username, "password": "StrongPass123!"},
        )
        self.assert_not_server_error(response, "login-post")
        self.assertEqual(response.status_code, 302)

        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("genealogy:create"),
            data={
                "title": "Smoke Created Genealogy",
                "surname": "Smoke",
                "compiled_at": 2026,
                "description": "created by smoke",
            },
        )
        self.assert_not_server_error(response, "genealogy-create-post")
        self.assertEqual(response.status_code, 302)

        response = self.client.post(
            reverse("genealogy:update", kwargs={"genealogy_id": self.genealogy.genealogy_id}),
            data={
                "title": "Smoke Genealogy Updated",
                "surname": "Smoke",
                "compiled_at": 2026,
                "description": "updated by smoke",
            },
        )
        self.assert_not_server_error(response, "genealogy-update-post")
        self.assertEqual(response.status_code, 302)

        response = self.client.post(
            reverse(
                "genealogy:member-create",
                kwargs={"genealogy_id": self.genealogy.genealogy_id},
            ),
            data=self.member_form_data("Smoke Created Member"),
        )
        self.assert_not_server_error(response, "member-create-post")
        self.assertEqual(response.status_code, 302)

        response = self.client.post(
            reverse(
                "genealogy:member-update",
                kwargs={
                    "genealogy_id": self.genealogy.genealogy_id,
                    "member_id": self.child.member_id,
                },
            ),
            data=self.member_form_data(
                "Smoke Child Updated",
                gender="male",
                birth_year=1970,
                biography="updated",
            ),
        )
        self.assert_not_server_error(response, "member-update-post")
        self.assertEqual(response.status_code, 302)

        response = self.client.post(
            reverse(
                "genealogy:member-event-create",
                kwargs={
                    "genealogy_id": self.genealogy.genealogy_id,
                    "member_id": self.child.member_id,
                },
            ),
            data={
                "event_type": "achievement",
                "event_year": 2001,
                "place_text": "Wuhan",
                "description": "created by smoke",
            },
        )
        self.assert_not_server_error(response, "member-event-create-post")
        self.assertEqual(response.status_code, 302)

        response = self.client.post(
            reverse(
                "genealogy:member-event-update",
                kwargs={
                    "genealogy_id": self.genealogy.genealogy_id,
                    "member_id": self.child.member_id,
                    "event_id": self.event.event_id,
                },
            ),
            data={
                "event_type": "residence",
                "event_year": 1991,
                "place_text": "Wuhan",
                "description": "updated by smoke",
            },
        )
        self.assert_not_server_error(response, "member-event-update-post")
        self.assertEqual(response.status_code, 302)

        temp_event = MemberEvent.objects.create(
            genealogy=self.genealogy,
            member=self.child,
            event_type="other",
            event_year=2002,
            recorded_by=self.owner,
        )
        response = self.client.post(
            reverse(
                "genealogy:member-event-delete",
                kwargs={
                    "genealogy_id": self.genealogy.genealogy_id,
                    "member_id": self.child.member_id,
                    "event_id": temp_event.event_id,
                },
            )
        )
        self.assert_not_server_error(response, "member-event-delete-post")
        self.assertEqual(response.status_code, 302)

        new_parent = self.create_member("Smoke New Parent", gender="male", birth_year=1955)
        new_child = self.create_member("Smoke New Child", gender="female", birth_year=1985)
        response = self.client.post(
            reverse(
                "genealogy:parent-child-create",
                kwargs={"genealogy_id": self.genealogy.genealogy_id},
            ),
            data={
                "parent_member_id": new_parent.member_id,
                "child_member_id": new_child.member_id,
                "parent_role": "father",
            },
        )
        self.assert_not_server_error(response, "parent-child-create-post")
        self.assertEqual(response.status_code, 302)

        response = self.client.post(
            reverse(
                "genealogy:parent-child-update",
                kwargs={
                    "genealogy_id": self.genealogy.genealogy_id,
                    "relation_id": self.father_relation.relation_id,
                },
            ),
            data={
                "parent_member_id": self.father.member_id,
                "child_member_id": self.child.member_id,
                "parent_role": "father",
            },
        )
        self.assert_not_server_error(response, "parent-child-update-post")
        self.assertEqual(response.status_code, 302)

        delete_parent = self.create_member("Smoke Delete Parent", gender="male", birth_year=1958)
        delete_child = self.create_member("Smoke Delete Child", gender="female", birth_year=1990)
        delete_relation = ParentChildRelation.objects.create(
            genealogy=self.genealogy,
            parent_member=delete_parent,
            child_member=delete_child,
            parent_role="father",
            created_by=self.owner,
        )
        response = self.client.post(
            reverse(
                "genealogy:parent-child-delete",
                kwargs={
                    "genealogy_id": self.genealogy.genealogy_id,
                    "relation_id": delete_relation.relation_id,
                },
            )
        )
        self.assert_not_server_error(response, "parent-child-delete-post")
        self.assertEqual(response.status_code, 302)

        member_a = self.create_member("Smoke Marriage A", gender="male", birth_year=1980)
        member_b = self.create_member("Smoke Marriage B", gender="female", birth_year=1981)
        response = self.client.post(
            reverse(
                "genealogy:marriage-create",
                kwargs={"genealogy_id": self.genealogy.genealogy_id},
            ),
            data={
                "member_a_id": member_a.member_id,
                "member_b_id": member_b.member_id,
                "status": "married",
                "start_year": 2005,
                "end_year": "",
                "description": "created by smoke",
            },
        )
        self.assert_not_server_error(response, "marriage-create-post")
        self.assertEqual(response.status_code, 302)

        response = self.client.post(
            reverse(
                "genealogy:marriage-update",
                kwargs={
                    "genealogy_id": self.genealogy.genealogy_id,
                    "marriage_id": self.marriage.marriage_id,
                },
            ),
            data={
                "member_a_id": self.child.member_id,
                "member_b_id": self.spouse.member_id,
                "status": "married",
                "start_year": 1996,
                "end_year": "",
                "description": "updated by smoke",
            },
        )
        self.assert_not_server_error(response, "marriage-update-post")
        self.assertEqual(response.status_code, 302)

        delete_marriage_a = self.create_member(
            "Smoke Delete Marriage A",
            gender="male",
            birth_year=1982,
        )
        delete_marriage_b = self.create_member(
            "Smoke Delete Marriage B",
            gender="female",
            birth_year=1983,
        )
        delete_marriage = Marriage.objects.create(
            genealogy=self.genealogy,
            member_a=delete_marriage_a,
            member_b=delete_marriage_b,
            status="married",
            created_by=self.owner,
        )
        response = self.client.post(
            reverse(
                "genealogy:marriage-delete",
                kwargs={
                    "genealogy_id": self.genealogy.genealogy_id,
                    "marriage_id": delete_marriage.marriage_id,
                },
            )
        )
        self.assert_not_server_error(response, "marriage-delete-post")
        self.assertEqual(response.status_code, 302)

        response = self.client.post(
            reverse(
                "genealogy:invitation-create",
                kwargs={"genealogy_id": self.genealogy.genealogy_id},
            ),
            data={"invitee_username": self.invitee.username, "message": "join smoke"},
        )
        self.assert_not_server_error(response, "invitation-create-post")
        self.assertEqual(response.status_code, 302)

        revoke_user = User.objects.create_user(
            username="smoke_revoke",
            display_name="Smoke Revoke",
            email="smoke-revoke@example.com",
            password="StrongPass123!",
        )
        revoke_invitation = GenealogyInvitation.objects.create(
            genealogy=self.genealogy,
            inviter_user=self.owner,
            invitee_user=revoke_user,
            status=InvitationStatus.PENDING,
        )
        response = self.client.post(
            reverse(
                "genealogy:invitation-revoke",
                kwargs={
                    "genealogy_id": self.genealogy.genealogy_id,
                    "invitation_id": revoke_invitation.invitation_id,
                },
            )
        )
        self.assert_not_server_error(response, "invitation-revoke-post")
        self.assertEqual(response.status_code, 302)

        accept_user = User.objects.create_user(
            username="smoke_accept",
            display_name="Smoke Accept",
            email="smoke-accept@example.com",
            password="StrongPass123!",
        )
        accept_invitation = GenealogyInvitation.objects.create(
            genealogy=self.genealogy,
            inviter_user=self.owner,
            invitee_user=accept_user,
            status=InvitationStatus.PENDING,
        )
        self.client.force_login(accept_user)
        response = self.client.post(
            reverse(
                "genealogy:invitation-accept",
                kwargs={"invitation_id": accept_invitation.invitation_id},
            )
        )
        self.assert_not_server_error(response, "invitation-accept-post")
        self.assertEqual(response.status_code, 302)

        decline_user = User.objects.create_user(
            username="smoke_decline",
            display_name="Smoke Decline",
            email="smoke-decline@example.com",
            password="StrongPass123!",
        )
        decline_invitation = GenealogyInvitation.objects.create(
            genealogy=self.genealogy,
            inviter_user=self.owner,
            invitee_user=decline_user,
            status=InvitationStatus.PENDING,
        )
        self.client.force_login(decline_user)
        response = self.client.post(
            reverse(
                "genealogy:invitation-decline",
                kwargs={"invitation_id": decline_invitation.invitation_id},
            )
        )
        self.assert_not_server_error(response, "invitation-decline-post")
        self.assertEqual(response.status_code, 302)

        self.client.force_login(self.owner)
        response = self.client.post(
            reverse(
                "genealogy:collaborator-role-update",
                kwargs={
                    "genealogy_id": self.genealogy.genealogy_id,
                    "collaborator_id": self.editor_collaborator.collaborator_id,
                },
            ),
            data={"role": CollaboratorRole.VIEWER},
        )
        self.assert_not_server_error(response, "collaborator-role-update-post")
        self.assertEqual(response.status_code, 302)

        removable_user = User.objects.create_user(
            username="smoke_removable",
            display_name="Smoke Removable",
            email="smoke-removable@example.com",
            password="StrongPass123!",
        )
        removable_invitation = GenealogyInvitation.objects.create(
            genealogy=self.genealogy,
            inviter_user=self.owner,
            invitee_user=removable_user,
            status=InvitationStatus.ACCEPTED,
        )
        removable_collaborator = GenealogyCollaborator.objects.create(
            genealogy=self.genealogy,
            user=removable_user,
            source_invitation=removable_invitation,
            role=CollaboratorRole.EDITOR,
            added_by=self.owner,
        )
        response = self.client.post(
            reverse(
                "genealogy:collaborator-remove",
                kwargs={
                    "genealogy_id": self.genealogy.genealogy_id,
                    "collaborator_id": removable_collaborator.collaborator_id,
                },
            )
        )
        self.assert_not_server_error(response, "collaborator-remove-post")
        self.assertEqual(response.status_code, 302)

        delete_member = self.create_member("Smoke Delete Member", gender="male", birth_year=1999)
        response = self.client.post(
            reverse(
                "genealogy:member-delete",
                kwargs={
                    "genealogy_id": self.genealogy.genealogy_id,
                    "member_id": delete_member.member_id,
                },
            )
        )
        self.assert_not_server_error(response, "member-delete-post")
        self.assertEqual(response.status_code, 302)

        delete_genealogy = Genealogy.objects.create(
            title="Smoke Delete Genealogy",
            surname="Smoke",
            created_by=self.owner,
        )
        response = self.client.post(
            reverse(
                "genealogy:delete",
                kwargs={"genealogy_id": delete_genealogy.genealogy_id},
            )
        )
        self.assert_not_server_error(response, "genealogy-delete-post")
        self.assertEqual(response.status_code, 302)

        response = self.client.post(reverse("accounts:logout"))
        self.assert_not_server_error(response, "logout-post")
        self.assertEqual(response.status_code, 302)

    @override_settings(
        CSRF_TRUSTED_ORIGINS=["http://127.0.0.1:5173", "http://localhost:5173"]
    )
    def test_registration_accepts_vite_dev_origin_with_csrf(self):
        client = Client(enforce_csrf_checks=True, HTTP_HOST="127.0.0.1:5173")
        get_response = client.get(
            reverse("accounts:register"),
            HTTP_ORIGIN="http://127.0.0.1:5173",
        )
        self.assertEqual(get_response.status_code, 200)
        csrf_token = client.cookies["csrftoken"].value

        response = client.post(
            reverse("accounts:register"),
            data={
                "csrfmiddlewaretoken": csrf_token,
                "username": "smoke_vite_signup",
                "display_name": "Smoke Vite Signup",
                "email": "smoke-vite-signup@example.com",
                "password1": "StrongPass12345!",
                "password2": "StrongPass12345!",
            },
            HTTP_ORIGIN="http://127.0.0.1:5173",
        )

        self.assert_not_server_error(response, "register-vite-origin-post")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.objects.filter(username="smoke_vite_signup").exists())
