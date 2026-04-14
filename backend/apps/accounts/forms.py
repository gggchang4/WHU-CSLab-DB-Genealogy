from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm


User = get_user_model()


class LoginForm(AuthenticationForm):
    username = forms.CharField(
        label="用户名",
        max_length=64,
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "请输入用户名"}
        ),
    )
    password = forms.CharField(
        label="密码",
        strip=False,
        widget=forms.PasswordInput(
            attrs={"class": "form-control", "placeholder": "请输入密码"}
        ),
    )


class UserRegistrationForm(UserCreationForm):
    display_name = forms.CharField(
        label="显示名称",
        max_length=128,
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "例如：欧阳修谱人"}
        ),
    )
    email = forms.EmailField(
        label="邮箱",
        widget=forms.EmailInput(
            attrs={"class": "form-control", "placeholder": "name@example.com"}
        ),
    )
    username = forms.CharField(
        label="用户名",
        max_length=64,
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "请输入登录用户名"}
        ),
    )
    password1 = forms.CharField(
        label="密码",
        strip=False,
        widget=forms.PasswordInput(
            attrs={"class": "form-control", "placeholder": "至少 8 位"}
        ),
    )
    password2 = forms.CharField(
        label="确认密码",
        strip=False,
        widget=forms.PasswordInput(
            attrs={"class": "form-control", "placeholder": "再次输入密码"}
        ),
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "display_name", "email")
