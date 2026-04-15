from django import forms
from django.contrib.auth import get_user_model

from apps.genealogy.models import (
    CollaboratorRole,
    EventType,
    Genealogy,
    GenealogyInvitation,
    Marriage,
    MarriageStatus,
    Member,
    MemberEvent,
    ParentChildRelation,
    ParentRole,
)


User = get_user_model()


class GenealogyForm(forms.ModelForm):
    class Meta:
        model = Genealogy
        fields = ["title", "surname", "compiled_at", "description"]
        widgets = {
            "title": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "例如：欧阳氏宗谱"}
            ),
            "surname": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "例如：欧阳"}
            ),
            "compiled_at": forms.NumberInput(
                attrs={"class": "form-control", "placeholder": "例如：2026"}
            ),
            "description": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 4,
                    "placeholder": "简要说明该族谱的来源、范围或备注",
                }
            ),
        }


class MemberForm(forms.ModelForm):
    class Meta:
        model = Member
        fields = [
            "full_name",
            "surname",
            "given_name",
            "gender",
            "birth_year",
            "death_year",
            "is_living",
            "generation_label",
            "seniority_text",
            "branch_name",
            "biography",
        ]
        widgets = {
            "full_name": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "例如：欧阳修"}
            ),
            "surname": forms.TextInput(attrs={"class": "form-control"}),
            "given_name": forms.TextInput(attrs={"class": "form-control"}),
            "gender": forms.Select(attrs={"class": "form-select"}),
            "birth_year": forms.NumberInput(attrs={"class": "form-control"}),
            "death_year": forms.NumberInput(attrs={"class": "form-control"}),
            "is_living": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "generation_label": forms.TextInput(attrs={"class": "form-control"}),
            "seniority_text": forms.TextInput(attrs={"class": "form-control"}),
            "branch_name": forms.TextInput(attrs={"class": "form-control"}),
            "biography": forms.Textarea(attrs={"class": "form-control", "rows": 4}),
        }


class MemberEventForm(forms.ModelForm):
    class Meta:
        model = MemberEvent
        fields = ["event_type", "event_year", "place_text", "description"]
        widgets = {
            "event_type": forms.Select(attrs={"class": "form-select"}),
            "event_year": forms.NumberInput(
                attrs={"class": "form-control", "placeholder": "例如：1998"}
            ),
            "place_text": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "例如：湖北武汉"}
            ),
            "description": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": "补充记录该成员的迁徙、居住、任职、成就等事件说明",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["event_type"].choices = EventType.choices


class InvitationCreateForm(forms.Form):
    invitee_username = forms.CharField(
        label="被邀请用户名",
        max_length=64,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "请输入系统中已注册的用户名",
            }
        ),
    )
    message = forms.CharField(
        label="邀请留言",
        required=False,
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 3,
                "placeholder": "例如：请一起维护这一支系的成员信息",
            }
        ),
    )

    def __init__(self, *args, **kwargs):
        self.genealogy = kwargs.pop("genealogy")
        self.inviter_user = kwargs.pop("inviter_user")
        super().__init__(*args, **kwargs)

    def clean_invitee_username(self):
        username = self.cleaned_data["invitee_username"].strip()
        try:
            invitee = User.objects.get(username=username)
        except User.DoesNotExist as exc:
            raise forms.ValidationError("该用户名不存在，请先确认对方已经注册。") from exc

        if invitee.user_id == self.inviter_user.user_id:
            raise forms.ValidationError("不能邀请自己成为协作者。")

        if self.genealogy.created_by_id == invitee.user_id:
            raise forms.ValidationError("族谱创建者无需再次被邀请。")

        if self.genealogy.collaborators.filter(user_id=invitee.user_id).exists():
            raise forms.ValidationError("该用户已经是当前族谱的协作者。")

        return username

    def save(self):
        invitee = User.objects.get(username=self.cleaned_data["invitee_username"].strip())
        invitation = GenealogyInvitation(
            genealogy=self.genealogy,
            inviter_user=self.inviter_user,
            invitee_user=invitee,
            message=self.cleaned_data["message"].strip(),
        )
        invitation.full_clean()
        invitation.save()
        return invitation


class CollaboratorRoleForm(forms.Form):
    role = forms.ChoiceField(
        label="协作权限",
        choices=CollaboratorRole.choices,
        widget=forms.Select(attrs={"class": "form-select form-select-sm"}),
    )


class GenealogyMemberScopedForm(forms.Form):
    def __init__(self, *args, **kwargs):
        self.genealogy = kwargs.pop("genealogy")
        super().__init__(*args, **kwargs)

    def get_member_or_error(self, member_id):
        try:
            return self.genealogy.members.get(member_id=member_id)
        except Member.DoesNotExist as exc:
            raise forms.ValidationError("该成员 ID 不存在于当前族谱中。") from exc


class MemberLookupForm(GenealogyMemberScopedForm):
    member_id = forms.IntegerField(
        label="成员 ID",
        min_value=1,
        widget=forms.NumberInput(
            attrs={"class": "form-control", "placeholder": "请输入成员 ID"}
        ),
    )

    def clean_member_id(self):
        return self.get_member_or_error(self.cleaned_data["member_id"])


class KinshipPathQueryForm(GenealogyMemberScopedForm):
    source_member_id = forms.IntegerField(
        label="起点成员 ID",
        min_value=1,
        widget=forms.NumberInput(
            attrs={"class": "form-control", "placeholder": "例如：10001"}
        ),
    )
    target_member_id = forms.IntegerField(
        label="终点成员 ID",
        min_value=1,
        widget=forms.NumberInput(
            attrs={"class": "form-control", "placeholder": "例如：10023"}
        ),
    )

    def clean_source_member_id(self):
        return self.get_member_or_error(self.cleaned_data["source_member_id"])

    def clean_target_member_id(self):
        return self.get_member_or_error(self.cleaned_data["target_member_id"])


class TreePreviewForm(GenealogyMemberScopedForm):
    root_member_id = forms.IntegerField(
        label="起始成员 ID",
        min_value=1,
        required=False,
        widget=forms.NumberInput(
            attrs={"class": "form-control", "placeholder": "例如：10001"}
        ),
    )
    max_depth = forms.IntegerField(
        label="向下预览层数",
        min_value=1,
        max_value=12,
        initial=5,
        widget=forms.NumberInput(attrs={"class": "form-control"}),
    )

    def clean_root_member_id(self):
        member_id = self.cleaned_data.get("root_member_id")
        if not member_id:
            return None
        return self.get_member_or_error(member_id)


class ParentChildRelationForm(GenealogyMemberScopedForm):
    parent_member_id = forms.IntegerField(
        label="父/母成员 ID",
        min_value=1,
        widget=forms.NumberInput(attrs={"class": "form-control"}),
    )
    child_member_id = forms.IntegerField(
        label="子女成员 ID",
        min_value=1,
        widget=forms.NumberInput(attrs={"class": "form-control"}),
    )
    parent_role = forms.ChoiceField(
        label="关系角色",
        choices=ParentRole.choices,
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    def __init__(self, *args, **kwargs):
        self.instance = kwargs.pop("instance", None)
        super().__init__(*args, **kwargs)
        if self.instance is not None and not self.is_bound:
            self.initial.update(
                {
                    "parent_member_id": self.instance.parent_member_id,
                    "child_member_id": self.instance.child_member_id,
                    "parent_role": self.instance.parent_role,
                }
            )

    def clean_parent_member_id(self):
        return self.get_member_or_error(self.cleaned_data["parent_member_id"])

    def clean_child_member_id(self):
        return self.get_member_or_error(self.cleaned_data["child_member_id"])

    def clean(self):
        cleaned_data = super().clean()
        parent_member = cleaned_data.get("parent_member_id")
        child_member = cleaned_data.get("child_member_id")

        if parent_member and child_member and parent_member.pk == child_member.pk:
            raise forms.ValidationError("成员不能与自己建立亲子关系。")

        return cleaned_data

    def save(self, *, created_by):
        relation = self.instance or ParentChildRelation(genealogy=self.genealogy)
        relation.parent_member = self.cleaned_data["parent_member_id"]
        relation.child_member = self.cleaned_data["child_member_id"]
        relation.parent_role = self.cleaned_data["parent_role"]
        if relation.created_by_id is None:
            relation.created_by = created_by
        relation.full_clean()
        relation.save()
        return relation


class MarriageForm(GenealogyMemberScopedForm):
    member_a_id = forms.IntegerField(
        label="成员 A ID",
        min_value=1,
        widget=forms.NumberInput(attrs={"class": "form-control"}),
    )
    member_b_id = forms.IntegerField(
        label="成员 B ID",
        min_value=1,
        widget=forms.NumberInput(attrs={"class": "form-control"}),
    )
    status = forms.ChoiceField(
        label="状态",
        choices=MarriageStatus.choices,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    start_year = forms.IntegerField(
        label="开始年份",
        required=False,
        min_value=1,
        max_value=3000,
        widget=forms.NumberInput(attrs={"class": "form-control"}),
    )
    end_year = forms.IntegerField(
        label="结束年份",
        required=False,
        min_value=1,
        max_value=3000,
        widget=forms.NumberInput(attrs={"class": "form-control"}),
    )
    description = forms.CharField(
        label="备注",
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 3}),
    )

    def __init__(self, *args, **kwargs):
        self.instance = kwargs.pop("instance", None)
        super().__init__(*args, **kwargs)
        if self.instance is not None and not self.is_bound:
            self.initial.update(
                {
                    "member_a_id": self.instance.member_a_id,
                    "member_b_id": self.instance.member_b_id,
                    "status": self.instance.status,
                    "start_year": self.instance.start_year,
                    "end_year": self.instance.end_year,
                    "description": self.instance.description,
                }
            )

    def clean_member_a_id(self):
        return self.get_member_or_error(self.cleaned_data["member_a_id"])

    def clean_member_b_id(self):
        return self.get_member_or_error(self.cleaned_data["member_b_id"])

    def clean(self):
        cleaned_data = super().clean()
        member_a = cleaned_data.get("member_a_id")
        member_b = cleaned_data.get("member_b_id")

        if member_a and member_b and member_a.pk == member_b.pk:
            raise forms.ValidationError("婚姻关系的两端不能是同一成员。")

        if member_a and member_b and member_a.pk > member_b.pk:
            cleaned_data["member_a_id"] = member_b
            cleaned_data["member_b_id"] = member_a

        return cleaned_data

    def save(self, *, created_by):
        marriage = self.instance or Marriage(genealogy=self.genealogy)
        marriage.member_a = self.cleaned_data["member_a_id"]
        marriage.member_b = self.cleaned_data["member_b_id"]
        marriage.status = self.cleaned_data["status"]
        marriage.start_year = self.cleaned_data["start_year"]
        marriage.end_year = self.cleaned_data["end_year"]
        marriage.description = self.cleaned_data["description"]
        if marriage.created_by_id is None:
            marriage.created_by = created_by
        marriage.full_clean()
        marriage.save()
        return marriage
