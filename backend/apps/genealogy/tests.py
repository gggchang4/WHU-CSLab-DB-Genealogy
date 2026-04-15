from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

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

    def test_viewer_cannot_access_relationship_page(self):
        self.client.force_login(self.viewer)
        response = self.client.get(
            reverse(
                "genealogy:relationships",
                kwargs={"genealogy_id": self.genealogy.genealogy_id},
            )
        )

        self.assertEqual(response.status_code, 404)

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
