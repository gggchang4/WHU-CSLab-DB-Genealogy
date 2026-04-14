from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q
from django.contrib.postgres.indexes import GinIndex

from apps.accounts.models import User
from apps.core.models import CreatedAtModel, TimeStampedModel


class GenealogyQuerySet(models.QuerySet):
    def accessible_to(self, user):
        if user.is_anonymous:
            return self.none()
        if getattr(user, "is_superuser", False):
            return self
        return self.filter(
            Q(created_by=user) | Q(collaborators__user=user)
        ).distinct()

    def editable_by(self, user):
        if user.is_anonymous:
            return self.none()
        if getattr(user, "is_superuser", False):
            return self
        return self.filter(
            Q(created_by=user)
            | Q(
                collaborators__user=user,
                collaborators__role=CollaboratorRole.EDITOR,
            )
        ).distinct()


class InvitationStatus(models.TextChoices):
    PENDING = "pending", "待处理"
    ACCEPTED = "accepted", "已接受"
    DECLINED = "declined", "已拒绝"
    REVOKED = "revoked", "已撤销"
    EXPIRED = "expired", "已过期"


class CollaboratorRole(models.TextChoices):
    EDITOR = "editor", "编辑者"
    VIEWER = "viewer", "只读"


class Gender(models.TextChoices):
    MALE = "male", "男"
    FEMALE = "female", "女"
    UNKNOWN = "unknown", "未知"


class EventType(models.TextChoices):
    MIGRATION = "migration", "迁徙"
    RESIDENCE = "residence", "居住"
    OCCUPATION = "occupation", "任职"
    ACHIEVEMENT = "achievement", "成就"
    BURIAL = "burial", "安葬"
    MARRIAGE_NOTE = "marriage_note", "婚配记载"
    OTHER = "other", "其他"


class ParentRole(models.TextChoices):
    FATHER = "father", "父亲"
    MOTHER = "mother", "母亲"


class MarriageStatus(models.TextChoices):
    MARRIED = "married", "婚姻存续"
    DIVORCED = "divorced", "离异"
    WIDOWED = "widowed", "丧偶"
    UNKNOWN = "unknown", "未知"


class Genealogy(TimeStampedModel):
    genealogy_id = models.BigAutoField(primary_key=True)
    title = models.CharField(max_length=200)
    surname = models.CharField(max_length=64)
    compiled_at = models.IntegerField(null=True, blank=True)
    description = models.TextField(blank=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.RESTRICT,
        related_name="created_genealogies",
        db_column="created_by",
    )

    objects = GenealogyQuerySet.as_manager()

    class Meta:
        db_table = "genealogies"
        ordering = ["title", "genealogy_id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(compiled_at__isnull=True)
                | Q(compiled_at__gte=1, compiled_at__lte=3000),
                name="genealogies_compiled_at_range",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.title} ({self.surname})"


class GenealogyInvitation(models.Model):
    invitation_id = models.BigAutoField(primary_key=True)
    genealogy = models.ForeignKey(
        Genealogy,
        on_delete=models.CASCADE,
        related_name="invitations",
        db_column="genealogy_id",
    )
    inviter_user = models.ForeignKey(
        User,
        on_delete=models.RESTRICT,
        related_name="sent_genealogy_invitations",
        db_column="inviter_user_id",
    )
    invitee_user = models.ForeignKey(
        User,
        on_delete=models.RESTRICT,
        related_name="received_genealogy_invitations",
        db_column="invitee_user_id",
    )
    status = models.CharField(
        max_length=16,
        choices=InvitationStatus.choices,
        default=InvitationStatus.PENDING,
    )
    message = models.TextField(blank=True)
    invited_at = models.DateTimeField(auto_now_add=True)
    responded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "genealogy_invitations"
        ordering = ["-invited_at", "-invitation_id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(status__in=[choice.value for choice in InvitationStatus]),
                name="genealogy_invitations_status_valid",
            ),
            models.CheckConstraint(
                condition=~Q(inviter_user=F("invitee_user")),
                name="genealogy_invitations_not_self",
            ),
            models.CheckConstraint(
                condition=Q(responded_at__isnull=True)
                | Q(responded_at__gte=F("invited_at")),
                name="genealogy_invitations_response_after_invite",
            ),
            models.UniqueConstraint(
                fields=["genealogy", "invitee_user"],
                condition=Q(status=InvitationStatus.PENDING),
                name="genealogy_invitations_pending_once",
            ),
        ]

    def clean(self) -> None:
        if self.inviter_user_id == self.invitee_user_id:
            raise ValidationError("不能邀请自己成为协作者。")

        if self.genealogy_id and self.inviter_user_id:
            inviter_allowed = (
                self.genealogy.created_by_id == self.inviter_user_id
                or GenealogyCollaborator.objects.filter(
                    genealogy_id=self.genealogy_id,
                    user_id=self.inviter_user_id,
                ).exists()
            )
            if not inviter_allowed:
                raise ValidationError("邀请人不是该族谱的创建者或已存在协作者。")

        if self.genealogy_id and self.invitee_user_id:
            if self.genealogy.created_by_id == self.invitee_user_id:
                raise ValidationError("族谱创建者不能被重复邀请。")
            if GenealogyCollaborator.objects.filter(
                genealogy_id=self.genealogy_id,
                user_id=self.invitee_user_id,
            ).exists():
                raise ValidationError("该用户已经是当前族谱的协作者。")


class GenealogyCollaborator(models.Model):
    collaborator_id = models.BigAutoField(primary_key=True)
    genealogy = models.ForeignKey(
        Genealogy,
        on_delete=models.CASCADE,
        related_name="collaborators",
        db_column="genealogy_id",
    )
    user = models.ForeignKey(
        User,
        on_delete=models.RESTRICT,
        related_name="genealogy_collaborations",
        db_column="user_id",
    )
    source_invitation = models.OneToOneField(
        GenealogyInvitation,
        on_delete=models.RESTRICT,
        related_name="activated_collaborator",
        db_column="source_invitation_id",
    )
    role = models.CharField(
        max_length=16,
        choices=CollaboratorRole.choices,
        default=CollaboratorRole.EDITOR,
    )
    joined_at = models.DateTimeField(auto_now_add=True)
    added_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="added_genealogy_collaborators",
        db_column="added_by",
    )

    class Meta:
        db_table = "genealogy_collaborators"
        ordering = ["genealogy_id", "user_id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(role__in=[choice.value for choice in CollaboratorRole]),
                name="genealogy_collaborators_role_valid",
            ),
            models.UniqueConstraint(
                fields=["genealogy", "user"],
                name="genealogy_collaborators_unique_user_per_genealogy",
            ),
        ]

    def clean(self) -> None:
        if not self.source_invitation_id or not self.genealogy_id or not self.user_id:
            return

        if self.source_invitation.genealogy_id != self.genealogy_id:
            raise ValidationError("协作关系必须来源于同一族谱的邀请。")

        if self.source_invitation.invitee_user_id != self.user_id:
            raise ValidationError("协作关系用户必须与邀请的被邀请人一致。")

        if self.source_invitation.status != InvitationStatus.ACCEPTED:
            raise ValidationError("只有已接受的邀请才能激活协作者关系。")

        if self.added_by_id is not None:
            actor_allowed = (
                self.genealogy.created_by_id == self.added_by_id
                or self.user_id == self.added_by_id
                or GenealogyCollaborator.objects.filter(
                    genealogy_id=self.genealogy_id,
                    user_id=self.added_by_id,
                ).exclude(pk=self.pk).exists()
            )
            if not actor_allowed:
                raise ValidationError("added_by 必须是创建者、现有协作者或邀请接受人本人。")


class Member(TimeStampedModel):
    member_id = models.BigAutoField(primary_key=True)
    genealogy = models.ForeignKey(
        Genealogy,
        on_delete=models.CASCADE,
        related_name="members",
        db_column="genealogy_id",
    )
    full_name = models.CharField(max_length=200)
    surname = models.CharField(max_length=64, blank=True)
    given_name = models.CharField(max_length=128, blank=True)
    gender = models.CharField(
        max_length=16,
        choices=Gender.choices,
        default=Gender.UNKNOWN,
    )
    birth_year = models.IntegerField(null=True, blank=True)
    death_year = models.IntegerField(null=True, blank=True)
    is_living = models.BooleanField(default=True)
    generation_label = models.CharField(max_length=64, blank=True)
    seniority_text = models.CharField(max_length=64, blank=True)
    branch_name = models.CharField(max_length=128, blank=True)
    biography = models.TextField(blank=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_members",
        db_column="created_by",
    )

    class Meta:
        db_table = "members"
        ordering = ["genealogy_id", "full_name", "member_id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(gender__in=[choice.value for choice in Gender]),
                name="members_gender_valid",
            ),
            models.CheckConstraint(
                condition=Q(birth_year__isnull=True)
                | Q(birth_year__gte=1, birth_year__lte=3000),
                name="members_birth_year_range",
            ),
            models.CheckConstraint(
                condition=Q(death_year__isnull=True)
                | Q(death_year__gte=1, death_year__lte=3000),
                name="members_death_year_range",
            ),
            models.CheckConstraint(
                condition=Q(death_year__isnull=True)
                | Q(birth_year__isnull=True)
                | Q(birth_year__lte=F("death_year")),
                name="members_birth_before_death",
            ),
            models.CheckConstraint(
                condition=Q(is_living=False) | Q(death_year__isnull=True),
                name="members_living_has_no_death_year",
            ),
        ]
        indexes = [
            models.Index(fields=["genealogy", "full_name"], name="members_genealogy_name_idx"),
            models.Index(fields=["genealogy", "gender"], name="members_genealogy_gender_idx"),
            GinIndex(
                fields=["full_name"],
                name="members_full_name_trgm_idx",
                opclasses=["gin_trgm_ops"],
            ),
        ]

    def __str__(self) -> str:
        return self.full_name


class MemberEvent(CreatedAtModel):
    event_id = models.BigAutoField(primary_key=True)
    genealogy = models.ForeignKey(
        Genealogy,
        on_delete=models.CASCADE,
        related_name="member_events",
        db_column="genealogy_id",
    )
    member = models.ForeignKey(
        Member,
        on_delete=models.CASCADE,
        related_name="events",
        db_column="member_id",
    )
    event_type = models.CharField(max_length=32, choices=EventType.choices)
    event_year = models.IntegerField(null=True, blank=True)
    place_text = models.CharField(max_length=255, blank=True)
    description = models.TextField(blank=True)
    recorded_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="recorded_member_events",
        db_column="recorded_by",
    )

    class Meta:
        db_table = "member_events"
        ordering = ["genealogy_id", "member_id", "event_year", "event_id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(event_type__in=[choice.value for choice in EventType]),
                name="member_events_type_valid",
            ),
            models.CheckConstraint(
                condition=Q(event_year__isnull=True)
                | Q(event_year__gte=1, event_year__lte=3000),
                name="member_events_year_range",
            ),
        ]
        indexes = [
            models.Index(
                fields=["genealogy", "member", "event_type", "event_year"],
                name="member_events_timeline_idx",
            ),
        ]

    def clean(self) -> None:
        if not self.member_id or not self.genealogy_id:
            return

        if self.member.genealogy_id != self.genealogy_id:
            raise ValidationError("成员事件必须和成员属于同一个族谱。")


class ParentChildRelation(CreatedAtModel):
    relation_id = models.BigAutoField(primary_key=True)
    genealogy = models.ForeignKey(
        Genealogy,
        on_delete=models.CASCADE,
        related_name="parent_child_relations",
        db_column="genealogy_id",
    )
    parent_member = models.ForeignKey(
        Member,
        on_delete=models.CASCADE,
        related_name="children_relations",
        db_column="parent_member_id",
    )
    child_member = models.ForeignKey(
        Member,
        on_delete=models.CASCADE,
        related_name="parent_relations",
        db_column="child_member_id",
    )
    parent_role = models.CharField(max_length=16, choices=ParentRole.choices)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_parent_child_relations",
        db_column="created_by",
    )

    class Meta:
        db_table = "parent_child_relations"
        ordering = ["genealogy_id", "child_member_id", "parent_role"]
        constraints = [
            models.CheckConstraint(
                condition=Q(parent_role__in=[choice.value for choice in ParentRole]),
                name="parent_child_relations_role_valid",
            ),
            models.CheckConstraint(
                condition=~Q(parent_member=F("child_member")),
                name="parent_child_relations_not_self",
            ),
            models.UniqueConstraint(
                fields=["genealogy", "parent_member", "child_member", "parent_role"],
                name="parent_child_relations_unique_edge",
            ),
            models.UniqueConstraint(
                fields=["genealogy", "child_member"],
                condition=Q(parent_role=ParentRole.FATHER),
                name="parent_child_relations_single_father",
            ),
            models.UniqueConstraint(
                fields=["genealogy", "child_member"],
                condition=Q(parent_role=ParentRole.MOTHER),
                name="parent_child_relations_single_mother",
            ),
        ]
        indexes = [
            models.Index(fields=["genealogy", "parent_member"], name="pcr_parent_lookup_idx"),
            models.Index(fields=["genealogy", "child_member"], name="pcr_child_lookup_idx"),
        ]

    def clean(self) -> None:
        if not self.parent_member_id or not self.child_member_id or not self.genealogy_id:
            return

        if self.parent_member_id == self.child_member_id:
            raise ValidationError("成员不能与自己建立父母关系。")

        if self.parent_member.genealogy_id != self.genealogy_id:
            raise ValidationError("父成员必须属于当前族谱。")
        if self.child_member.genealogy_id != self.genealogy_id:
            raise ValidationError("子成员必须属于当前族谱。")

        if self.parent_role == ParentRole.FATHER and self.parent_member.gender != Gender.MALE:
            raise ValidationError("father 关系要求父成员性别为 male。")
        if self.parent_role == ParentRole.MOTHER and self.parent_member.gender != Gender.FEMALE:
            raise ValidationError("mother 关系要求母成员性别为 female。")

        if (
            self.parent_member.birth_year is not None
            and self.child_member.birth_year is not None
            and self.parent_member.birth_year >= self.child_member.birth_year
        ):
            raise ValidationError("父母出生年份必须早于子女。")


class Marriage(CreatedAtModel):
    marriage_id = models.BigAutoField(primary_key=True)
    genealogy = models.ForeignKey(
        Genealogy,
        on_delete=models.CASCADE,
        related_name="marriages",
        db_column="genealogy_id",
    )
    member_a = models.ForeignKey(
        Member,
        on_delete=models.CASCADE,
        related_name="marriages_as_a",
        db_column="member_a_id",
    )
    member_b = models.ForeignKey(
        Member,
        on_delete=models.CASCADE,
        related_name="marriages_as_b",
        db_column="member_b_id",
    )
    status = models.CharField(
        max_length=16,
        choices=MarriageStatus.choices,
        default=MarriageStatus.MARRIED,
    )
    start_year = models.IntegerField(null=True, blank=True)
    end_year = models.IntegerField(null=True, blank=True)
    description = models.TextField(blank=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_marriages",
        db_column="created_by",
    )

    class Meta:
        db_table = "marriages"
        ordering = ["genealogy_id", "member_a_id", "member_b_id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(status__in=[choice.value for choice in MarriageStatus]),
                name="marriages_status_valid",
            ),
            models.CheckConstraint(
                condition=~Q(member_a=F("member_b")),
                name="marriages_not_self",
            ),
            models.CheckConstraint(
                condition=Q(member_a__lt=F("member_b")),
                name="marriages_canonical_member_order",
            ),
            models.CheckConstraint(
                condition=Q(end_year__isnull=True)
                | Q(start_year__isnull=True)
                | Q(start_year__lte=F("end_year")),
                name="marriages_start_before_end",
            ),
            models.UniqueConstraint(
                fields=["genealogy", "member_a", "member_b"],
                condition=Q(status=MarriageStatus.MARRIED),
                name="marriages_single_active_pair",
            ),
        ]
        indexes = [
            models.Index(fields=["genealogy", "member_a"], name="marriages_member_a_idx"),
            models.Index(fields=["genealogy", "member_b"], name="marriages_member_b_idx"),
        ]

    def clean(self) -> None:
        if not self.member_a_id or not self.member_b_id or not self.genealogy_id:
            return

        if self.member_a_id == self.member_b_id:
            raise ValidationError("婚姻关系两端不能是同一成员。")
        if self.member_a_id and self.member_b_id and self.member_a_id >= self.member_b_id:
            raise ValidationError("member_a 必须小于 member_b，以保证婚姻边唯一表示。")
        if self.member_a.genealogy_id != self.genealogy_id:
            raise ValidationError("member_a 必须属于当前族谱。")
        if self.member_b.genealogy_id != self.genealogy_id:
            raise ValidationError("member_b 必须属于当前族谱。")

        if (
            self.status == MarriageStatus.MARRIED
            and Marriage.objects.filter(
                genealogy_id=self.genealogy_id,
                status=MarriageStatus.MARRIED,
            )
            .exclude(pk=self.pk)
            .filter(Q(member_a_id__in=[self.member_a_id, self.member_b_id]) | Q(member_b_id__in=[self.member_a_id, self.member_b_id]))
            .exists()
        ):
            raise ValidationError("同一成员同一时刻只能存在一条有效婚姻记录。")
