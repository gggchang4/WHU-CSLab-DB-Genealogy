from django import forms

from apps.genealogy.models import Genealogy, Member


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
