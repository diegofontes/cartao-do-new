from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm


class SignupForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = get_user_model()
        # mantém os campos padrão do UserCreationForm (username, password1, password2)
        fields = UserCreationForm.Meta.fields

