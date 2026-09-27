import importlib

import pytest


@pytest.mark.parametrize(
    ("overrides", "expected_host", "expected_password"),
    [
        (
            {
                "EMAIL_HOST": "smtp.resend.com",
                "EMAIL_HOST_USER": "resend",
                "EMAIL_HOST_PASSWORD": "re_ab/c@d:e",
            },
            "smtp.resend.com",
            "re_ab/c@d:e",
        ),
        (
            {"EMAIL_HOST": "", "EMAIL_URL": "smtp+ssl://u:p@mail.example.com:465"},
            "mail.example.com",
            "p",
        ),
    ],
)
def test_mailers_built_from_discrete_vars_or_url(
    monkeypatch, overrides, expected_host, expected_password
):
    monkeypatch.setenv("SECRET_KEY", "x")
    for key, value in overrides.items():
        monkeypatch.setenv(key, value)
    import config.settings as settings_module

    module = importlib.reload(settings_module)
    options = module.MAILERS["default"]["OPTIONS"]
    assert options["host"] == expected_host
    assert options["password"] == expected_password
    assert module.MAILERS["default"]["BACKEND"].endswith("smtp.EmailBackend")
    importlib.reload(settings_module)  # restore
