from lensnode.datasource_sync import _git_auth_url


def test_git_auth_url_uses_inline_access_token():
    """HTTPS token auth can use the datasource config access token."""

    url = _git_auth_url(
        "https://github.com/example/repo.git",
        {
            "auth_scheme": "token",
            "access_token": "ghp_example",
        },
    )

    assert url == "https://oauth2:ghp_example@github.com/example/repo.git"
