from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.genealogy.models import (
    CollaboratorRole,
    Genealogy,
    GenealogyCollaborator,
    GenealogyInvitation,
    InvitationStatus,
    Member,
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
            title="欧阳氏宗谱",
            surname="欧阳",
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
            title="王氏家谱",
            surname="王",
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
                "title": "新修李氏族谱",
                "surname": "李",
                "compiled_at": 2026,
                "description": "course demo",
            },
        )

        created = Genealogy.objects.get(title="新修李氏族谱")
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
            full_name="欧阳修",
            surname="欧阳",
            given_name="修",
            created_by=self.owner,
        )
        Member.objects.create(
            genealogy=self.genealogy,
            full_name="欧阳询",
            surname="欧阳",
            given_name="询",
            created_by=self.owner,
        )

        self.client.force_login(self.collaborator)
        response = self.client.get(
            reverse(
                "genealogy:member-list",
                kwargs={"genealogy_id": self.genealogy.genealogy_id},
            ),
            data={"q": "欧阳修"},
        )

        self.assertContains(response, "欧阳修")
        self.assertNotContains(response, "欧阳询")

    def test_member_create_sets_genealogy_and_creator(self):
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse(
                "genealogy:member-create",
                kwargs={"genealogy_id": self.genealogy.genealogy_id},
            ),
            data={
                "full_name": "欧阳修",
                "surname": "欧阳",
                "given_name": "修",
                "gender": "male",
                "birth_year": 1007,
                "death_year": 1072,
                "is_living": "",
                "generation_label": "",
                "seniority_text": "",
                "branch_name": "主支",
                "biography": "北宋文学家",
            },
        )

        created = Member.objects.get(full_name="欧阳修")
        self.assertRedirects(
            response,
            reverse(
                "genealogy:member-list",
                kwargs={"genealogy_id": self.genealogy.genealogy_id},
            ),
        )
        self.assertEqual(created.genealogy, self.genealogy)
        self.assertEqual(created.created_by, self.owner)
