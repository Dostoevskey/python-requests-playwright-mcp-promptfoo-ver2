#!/usr/bin/env python3
"""Seed the Conduit RealWorld backend with deterministic demo data. This script is idempotent.

It will create users and articles if they do not exist, and update them if they do.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import yaml
from dotenv import load_dotenv


@dataclass
class UserContext:
    username: str
    email: str
    token: str
    password: str


def slugify(title: str) -> str:
    import re

    slug = re.sub(r"[^a-zA-Z0-9]+", "-", title.strip().lower())
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug or "article"


def _get_auth_session(token: Optional[str] = None) -> requests.Session:
    sess = requests.Session()
    sess.headers.update({"Accept": "application/json", "Content-Type": "application/json"})
    retry = Retry(
        total=5,
        connect=5,
        backoff_factor=1,
        status_forcelist=(502, 503, 504),
        allowed_methods=("GET", "POST", "PUT"),
    )
    adapter = HTTPAdapter(max_retries=retry)
    sess.mount("http://", adapter)
    sess.mount("https://", adapter)
    if token:
        sess.headers.update({"Authorization": f"Token {token}"})
    return sess


def register_user(session: requests.Session, base_url: str, user: dict[str, Any], password: str) -> UserContext:
    payload = {"user": {"username": user["username"], "email": user["email"], "password": password}}
    resp = session.post(f"{base_url}/users", json=payload, timeout=15)
    if resp.status_code in (200, 201):
        data = resp.json()["user"]
        return UserContext(username=data["username"], email=data["email"], token=data["token"], password=password)
    if resp.status_code == 422:
        # user exists; fall back to login
        return login_user(session, base_url, user, password)
    resp.raise_for_status()


def login_user(session: requests.Session, base_url: str, user: dict[str, Any], password: str) -> UserContext:
    payload = {"user": {"email": user["email"], "password": password}}
    resp = session.post(f"{base_url}/users/login", json=payload, timeout=15)
    resp.raise_for_status()
    data = resp.json()["user"]
    return UserContext(username=data["username"], email=data["email"], token=data["token"], password=password)


def ensure_profile(
    session: requests.Session,
    base_url: str,
    author: UserContext,
    bio: str | None = None,
    password: str | None = None,
) -> None:
    profile_payload = {"user": {}}
    if bio:
        profile_payload["user"]["bio"] = bio
    if password:
        profile_payload["user"]["password"] = password
    if not profile_payload["user"]:
        return
    resp = session.put(
        f"{base_url}/user",
        headers={"Authorization": f"Token {author.token}"},
        json=profile_payload,
        timeout=15,
    )
    if resp.status_code in (200, 201):
        return
    if resp.status_code == 500:
        print(f"Profile update warning for {author.username}: {resp.text}")
        return
    resp.raise_for_status()


def ensure_article(
    session: requests.Session,
    base_url: str,
    article: dict[str, Any],
    author: UserContext,
) -> None:
    # Idempotent article creation: check by slug and update if present
    title = article.get("title")
    body = article.get("body")
    description = article.get("description", "")
    slug = slugify(title)

    # Try GET by slug
    get_resp = session.get(f"{base_url}/articles/{slug}", timeout=10)
    if get_resp.status_code == 200:
        # Update existing article to match desired state
        put_payload = {"article": {"title": title, "body": body}}
        put_resp = session.put(f"{base_url}/articles/{slug}", headers={"Authorization": f"Token {author.token}"}, json=put_payload, timeout=10)
        if put_resp.status_code in (200, 201):
            return
        put_resp.raise_for_status()
    else:
        # Create article
        payload = {"article": {"title": title, "description": description, "body": body, "tagList": article.get("tags", [])}}
        resp = session.post(f"{base_url}/articles", headers={"Authorization": f"Token {author.token}"}, json=payload, timeout=10)
        if resp.status_code in (200, 201):
            return
        # If conflict or validation, raise
        resp.raise_for_status()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", default="config/demo.env")
    args = parser.parse_args()

    env_path = Path(args.env_file)
    if not env_path.exists():
        print(f"Env file not found: {env_path}")
        return 2

    load_dotenv(env_path, override=True)
    base_url = os.environ.get("API_BASE_URL")
    if not base_url:
        print("API_BASE_URL not set in env file")
        return 2

    password = os.environ.get("DEFAULT_PASSWORD", "Password123!")
    data_path = Path(__file__).parent / "../promptfoo" / "seed" / "seed.json"

    # Fallback: if no seed bundle, use built-in small sample
    if not data_path.exists():
        sample = {
            "users": [
                {"username": "alice", "email": "alice@example.com"},
                {"username": "bob", "email": "bob@example.com"},
            ],
            "articles": [
                {"title": "Hello World", "body": "Sample article", "description": "sample"},
            ],
        }
    else:
        sample = json.loads(data_path.read_text(encoding="utf-8"))

    # Use a session without auth for user creation/login
    session = _get_auth_session()

    created_users: dict[str, UserContext] = {}
    for u in sample.get("users", []):
        uc = register_user(session, base_url, u, password)
        created_users[uc.username] = uc
        ensure_profile(session, base_url, uc, bio=u.get("bio"))

    # Use one of the authors as token for article operations
    # Fallback to first created user
    author = next(iter(created_users.values()), None)
    if not author:
        print("No users created; aborting")
        return 1

    auth_session = _get_auth_session(author.token)
    for art in sample.get("articles", []):
        ensure_article(auth_session, base_url, art, author)

    print("Seeding complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
