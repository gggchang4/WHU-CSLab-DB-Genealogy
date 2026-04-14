from django import forms
from django.contrib.auth import get_user_model

from apps.genealogy.models import (
    CollaboratorRole,
    Genealogy,
    Marriage,
    Member,
    ParentChildRelation,
)


User = get_user_model()


class MemberChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return f"{obj.member_id} - {obj.full_name}"


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
            "biography": forms.Textarea(
                attrs={"class": "form-control", "rows": 4}
            ),
        }


class InvitationCreateForm(forms.Form):
    invitee_username = forms.CharField(
        label="被邀请用户名",
        max_length=64,
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "请输入系统中已注册的用户名"}
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
        from apps.genealogy.models import GenealogyInvitation

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


class ParentChildRelationForm(forms.ModelForm):
    parent_member = MemberChoiceField(
        label="父/母成员",
        queryset=Member.objects.none(),
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    child_member = MemberChoiceField(
        label="子女成员",
        queryset=Member.objects.none(),
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    class Meta:
        model = ParentChildRelation
        fields = ["parent_member", "child_member", "parent_role"]
        widgets = {
            "parent_role": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, **kwargs):
        genealogy = kwargs.pop("genealogy")
        super().__init__(*args, **kwargs)
        member_queryset = genealogy.members.order_by("full_name", "member_id")
        self.fields["parent_member"].queryset = member_queryset
        self.fields["child_member"].queryset = member_queryset


class MarriageForm(forms.ModelForm):
    member_a = MemberChoiceField(
        label="成员 A",
        queryset=Member.objects.none(),
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    member_b = MemberChoiceField(
        label="成员 B",
        queryset=Member.objects.none(),
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    class Meta:
        model = Marriage
        fields = ["member_a", "member_b", "status", "start_year", "end_year", "description"]
        widgets = {
            "status": forms.Select(attrs={"class": "form-select"}),
            "start_year": forms.NumberInput(attrs={"class": "form-control"}),
            "end_year": forms.NumberInput(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        genealogy = kwargs.pop("genealogy")
        super().__init__(*args, **kwargs)
        member_queryset = genealogy.members.order_by("full_name", "member_id")
        self.fields["member_a"].queryset = member_queryset
        self.fields["member_b"].queryset = member_queryset

    def clean(self):
        cleaned_data = super().clean()
        member_a = cleaned_data.get("member_a")
        member_b = cleaned_data.get("member_b")

        if member_a and member_b and member_a.pk == member_b.pk:
            raise forms.ValidationError("婚姻关系的两端不能是同一成员。")

        if member_a and member_b and member_a.pk > member_b.pk:
            cleaned_data["member_a"] = member_b
            cleaned_data["member_b"] = member_a

        return cleaned_data
