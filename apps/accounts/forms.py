from django import forms


class SignupForm(forms.Form):
    """Extra sign-up fields; allauth mixes this into its (headless) sign-up input."""

    first_name = forms.CharField(max_length=150)
    last_name = forms.CharField(max_length=150)

    def signup(self, request, user) -> None:
        user.first_name = self.cleaned_data["first_name"].strip()
        user.last_name = self.cleaned_data["last_name"].strip()
        user.save(update_fields=["first_name", "last_name"])
