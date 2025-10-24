"""Lightweight wrapper around the RealWorld API for test readability."""
from __future__ import annotations

import random
import string
from dataclasses import dataclass
from typing import Any, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

DEFAULT_TIMEOUT = 10  # seconds

@dataclass
class UserCredentials:
    username: str
    email: str
    password: str
    token: str | None = None


class ApiError(RuntimeError):
    """Raised when the API returns an unexpected status code."""

    def __init__(self, message: str, status: Optional[int] = None, body: Optional[str] = None) -> None:
        super().__init__(message)
        self.status = status
        self.status_code = status  # Alias for consistency
        self.body = body


class ApiClient:
    def __init__(self, base_url: str, session: requests.Session | None = None, timeout: int = DEFAULT_TIMEOUT) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = session or requests.Session()
        # Configure retries for transient server/network errors
        retries = Retry(total=3, backoff_factor=0.3, status_forcelist=(429, 500, 502, 503, 504), raise_on_status=False)
        adapter = HTTPAdapter(max_retries=retries)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        # Default headers
        self.session.headers.update({"Accept": "application/json", "Content-Type": "application/json"})

    def _raise_for_status(self, response: requests.Response, expected: tuple[int, ...]) -> dict[str, Any]:
        if response.status_code not in expected:
            raise ApiError(f"Unexpected status {response.status_code}: {response.text}", status=response.status_code, body=response.text)
        if response.text:
            return response.json()
        return {}

    def _random_suffix(self, length: int = 6) -> str:
        return "".join(random.choices(string.ascii_lowercase + string.digits, k=length))

    def generate_credentials(self, prefix: str = "testuser") -> UserCredentials:
        suffix = self._random_suffix()
        username = f"{prefix}_{suffix}"
        email = f"{username}@example.com"
        password = f"Pass!{suffix}"
        return UserCredentials(username=username, email=email, password=password)

    # User endpoints -----------------------------------------------------

    def register_user(self, creds: UserCredentials) -> UserCredentials:
        payload = {"user": {"username": creds.username, "email": creds.email, "password": creds.password}}
        response = self.session.post(f"{self.base_url}/users", json=payload, timeout=self.timeout)
        data = self._raise_for_status(response, expected=(200, 201))
        token = data["user"].get("token")
        creds.token = token
        return creds

    def login_user(self, creds: UserCredentials) -> UserCredentials:
        payload = {"user": {"email": creds.email, "password": creds.password}}
        response = self.session.post(f"{self.base_url}/users/login", json=payload, timeout=self.timeout)
        data = self._raise_for_status(response, expected=(200,))
        creds.token = data["user"].get("token")
        return creds

    def update_profile(
        self,
        creds: UserCredentials,
        bio: str | None = None,
        image: str | None = None,
        password: str | None = None,
    ) -> dict[str, Any]:
        headers = {"Authorization": f"Token {creds.token}"} if creds.token else {}
        payload = {"user": {}}
        if bio:
            payload["user"]["bio"] = bio
        if image:
            payload["user"]["image"] = image
        if password:
            payload["user"]["password"] = password
        response = self.session.put(f"{self.base_url}/user", headers=headers, json=payload, timeout=self.timeout)
        return self._raise_for_status(response, expected=(200,))

    # Article endpoints --------------------------------------------------

    def create_article(
        self,
        creds: UserCredentials,
        title: str,
        description: str,
        body: str,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        headers = {"Authorization": f"Token {creds.token}"} if creds.token else {}
        payload = {
            "article": {
                "title": title,
                "description": description,
                "body": body,
                "tagList": tags or [],
            }
        }
        response = self.session.post(f"{self.base_url}/articles", headers=headers, json=payload, timeout=self.timeout)
        return self._raise_for_status(response, expected=(200, 201))

    def get_article(self, slug: str) -> dict[str, Any]:
        response = self.session.get(f"{self.base_url}/articles/{slug}", timeout=self.timeout)
        return self._raise_for_status(response, expected=(200,))

    def list_articles(self, limit: int = 5, offset: int = 0) -> dict[str, Any]:
        params = {"limit": limit, "offset": offset}
        response = self.session.get(f"{self.base_url}/articles", params=params, timeout=self.timeout)
        return self._raise_for_status(response, expected=(200,))

    def update_article(self, creds: UserCredentials, slug: str, title: str | None = None, body: str | None = None) -> dict[str, Any]:
        headers = {"Authorization": f"Token {creds.token}"} if creds.token else {}
        payload: dict[str, Any] = {"article": {}}
        if title:
            payload["article"]["title"] = title
        if body:
            payload["article"]["body"] = body
        response = self.session.put(f"{self.base_url}/articles/{slug}", headers=headers, json=payload, timeout=self.timeout)
        return self._raise_for_status(response, expected=(200,))

    def delete_article(self, creds: UserCredentials, slug: str) -> None:
        headers = {"Authorization": f"Token {creds.token}"} if creds.token else {}
        response = self.session.delete(f"{self.base_url}/articles/{slug}", headers=headers, timeout=self.timeout)
        self._raise_for_status(response, expected=(200, 204))

    def favorite_article(self, creds: UserCredentials, slug: str) -> dict[str, Any]:
        """Favorite an article."""
        headers = {"Authorization": f"Token {creds.token}"} if creds.token else {}
        response = self.session.post(f"{self.base_url}/articles/{slug}/favorite", headers=headers, timeout=self.timeout)
        return self._raise_for_status(response, expected=(200, 201))

    def unfavorite_article(self, creds: UserCredentials, slug: str) -> dict[str, Any]:
        """Unfavorite an article."""
        headers = {"Authorization": f"Token {creds.token}"} if creds.token else {}
        response = self.session.delete(f"{self.base_url}/articles/{slug}/favorite", headers=headers, timeout=self.timeout)
        return self._raise_for_status(response, expected=(200, 204))

    # Comment endpoints --------------------------------------------------

    def add_comment(self, creds: UserCredentials, slug: str, body: str) -> dict[str, Any]:
        """Add a comment to an article."""
        headers = {"Authorization": f"Token {creds.token}"} if creds.token else {}
        payload = {"comment": {"body": body}}
        response = self.session.post(
            f"{self.base_url}/articles/{slug}/comments",
            headers=headers,
            json=payload,
            timeout=self.timeout,
        )
        return self._raise_for_status(response, expected=(200, 201))

    def get_comments(self, slug: str) -> dict[str, Any]:
        """Get all comments for an article."""
        response = self.session.get(f"{self.base_url}/articles/{slug}/comments", timeout=self.timeout)
        return self._raise_for_status(response, expected=(200,))

    def delete_comment(self, creds: UserCredentials, slug: str, comment_id: int) -> None:
        """Delete a comment from an article."""
        headers = {"Authorization": f"Token {creds.token}"} if creds.token else {}
        response = self.session.delete(
            f"{self.base_url}/articles/{slug}/comments/{comment_id}",
            headers=headers,
            timeout=self.timeout,
        )
        self._raise_for_status(response, expected=(200, 204))

    def close(self) -> None:
        try:
            self.session.close()
        except Exception:
            pass


__all__ = ["ApiClient", "ApiError", "UserCredentials"]