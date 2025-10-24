"""
API Error Handling and Negative Test Cases

Tests validation errors, authorization failures, and edge cases
that should be handled gracefully by the API.
"""
from __future__ import annotations

from dataclasses import replace

import allure
import pytest

from src.utils.api_client import ApiClient, ApiError


@pytest.mark.api
def test_duplicate_user_registration(api_client: ApiClient) -> None:
    """Test that duplicate registration is rejected with appropriate error."""
    creds = api_client.generate_credentials(prefix="api_duplicate")

    with allure.step("register user for the first time"):
        api_client.register_user(creds)

    with allure.step("attempt to register same user again"):
        with pytest.raises(ApiError) as exc_info:
            api_client.register_user(creds)
        assert exc_info.value.status_code in {422, 409}, "Expected 422 Unprocessable Entity or 409 Conflict"


@pytest.mark.api
def test_login_with_invalid_credentials(api_client: ApiClient) -> None:
    """Test that login with wrong password fails appropriately."""
    creds = api_client.generate_credentials(prefix="api_badlogin")
    api_client.register_user(creds)

    with allure.step("attempt login with wrong password"):
        bad_creds = replace(creds, password="WrongPassword123!")
        with pytest.raises(ApiError) as exc_info:
            api_client.login_user(bad_creds)
        assert exc_info.value.status_code in {401, 403, 422}, "Expected 401 Unauthorized or similar"


@pytest.mark.api
def test_unauthorized_article_delete(api_client: ApiClient) -> None:
    """Test that users cannot delete articles they don't own."""
    # Create article with first user
    owner_creds = api_client.generate_credentials(prefix="api_owner")
    api_client.register_user(owner_creds)
    article = api_client.create_article(
        owner_creds,
        title="Article by owner",
        description="Test",
        body="Content",
        tags=["test"],
    )["article"]
    slug = article["slug"]

    # Try to delete with different user
    attacker_creds = api_client.generate_credentials(prefix="api_attacker")
    api_client.register_user(attacker_creds)

    with allure.step("attempt unauthorized delete"):
        with pytest.raises(ApiError) as exc_info:
            api_client.delete_article(attacker_creds, slug)
        assert exc_info.value.status_code in {401, 403}, "Expected 401/403 for unauthorized delete"

    # Verify article still exists
    with allure.step("verify article was not deleted"):
        fetched = api_client.get_article(slug)["article"]
        assert fetched["slug"] == slug


@pytest.mark.api
def test_get_nonexistent_article(api_client: ApiClient) -> None:
    """Test that fetching non-existent article returns 404."""
    with pytest.raises(ApiError) as exc_info:
        api_client.get_article("nonexistent-article-slug-12345")
    assert exc_info.value.status_code == 404, "Expected 404 Not Found"


@pytest.mark.api
def test_invalid_article_creation_missing_fields(api_client: ApiClient) -> None:
    """Test article creation with missing required fields."""
    creds = api_client.generate_credentials(prefix="api_invalid")
    registered = api_client.register_user(creds)

    with allure.step("attempt article creation with empty title"):
        # Direct API call with missing fields
        headers = {"Authorization": f"Token {registered.token}"}
        response = api_client.session.post(
            f"{api_client.base_url}/articles",
            json={"article": {"title": "", "description": "test", "body": "test"}},
            headers=headers,
        )
        # Should return 422 validation error
        assert response.status_code == 422, "Expected 422 for missing title"


@pytest.mark.api
def test_article_update_slug_change(api_client: ApiClient) -> None:
    """Test that updating article title changes its slug."""
    creds = api_client.generate_credentials(prefix="api_slug")
    api_client.register_user(creds)

    with allure.step("create article with initial title"):
        article = api_client.create_article(
            creds,
            title="Original Title for Slug Test",
            description="Test",
            body="Content",
            tags=["test"],
        )["article"]
        original_slug = article["slug"]

    with allure.step("update article with different title"):
        updated = api_client.update_article(
            creds,
            slug=original_slug,
            title="Completely Different Title",
        )["article"]
        new_slug = updated["slug"]

        # Slug should change
        assert new_slug != original_slug, "Slug should change when title changes significantly"

    with allure.step("verify old slug returns 404"):
        with pytest.raises(ApiError) as exc_info:
            api_client.get_article(original_slug)
        assert exc_info.value.status_code == 404


@pytest.mark.api
def test_pagination_boundary_cases(api_client: ApiClient) -> None:
    """Test pagination with edge case parameters."""
    with allure.step("request with zero limit"):
        result = api_client.list_articles(limit=0, offset=0)
        assert result["articles"] == [] or len(result["articles"]) <= 20, "Zero limit should return empty or default"

    with allure.step("request with excessive offset"):
        result = api_client.list_articles(limit=5, offset=10000)
        assert result["articles"] == [], "Excessive offset should return empty list"

    with allure.step("request with very large limit"):
        result = api_client.list_articles(limit=1000, offset=0)
        # API should cap this at reasonable limit
        assert len(result["articles"]) <= 100, "API should cap excessive limits"


@pytest.mark.api
def test_favorite_unfavorite_article(api_client: ApiClient) -> None:
    """Test favoriting and unfavoriting article workflow."""
    author_creds = api_client.generate_credentials(prefix="api_fav_author")
    api_client.register_user(author_creds)

    reader_creds = api_client.generate_credentials(prefix="api_fav_reader")
    api_client.register_user(reader_creds)

    with allure.step("create article"):
        article = api_client.create_article(
            author_creds,
            title="Article to favorite",
            description="Test",
            body="Content",
            tags=["test"],
        )["article"]
        slug = article["slug"]
        initial_fav_count = article["favoritesCount"]

    with allure.step("reader favorites the article"):
        favorited = api_client.favorite_article(reader_creds, slug)["article"]
        assert favorited["favorited"] is True
        assert favorited["favoritesCount"] == initial_fav_count + 1

    with allure.step("reader unfavorites the article"):
        unfavorited = api_client.unfavorite_article(reader_creds, slug)["article"]
        assert unfavorited["favorited"] is False
        assert unfavorited["favoritesCount"] == initial_fav_count


@pytest.mark.api
def test_concurrent_article_creation(api_client: ApiClient) -> None:
    """Test that concurrent article creations by same user work correctly."""
    creds = api_client.generate_credentials(prefix="api_concurrent")
    api_client.register_user(creds)

    with allure.step("create multiple articles rapidly"):
        created_slugs = set()
        for i in range(5):
            article = api_client.create_article(
                creds,
                title=f"Concurrent Article {i} {creds.username}",
                description=f"Test {i}",
                body=f"Content {i}",
                tags=["concurrent"],
            )["article"]
            created_slugs.add(article["slug"])

        # All articles should have unique slugs
        assert len(created_slugs) == 5, "All articles should be created with unique slugs"

    with allure.step("verify all articles are retrievable"):
        for slug in created_slugs:
            fetched = api_client.get_article(slug)["article"]
            assert fetched["slug"] == slug


@pytest.mark.api
def test_article_with_special_characters(api_client: ApiClient) -> None:
    """Test article creation with special characters and unicode."""
    creds = api_client.generate_credentials(prefix="api_special")
    api_client.register_user(creds)

    special_title = "Article with émojis 🚀 and spëcial çhars"
    special_body = "Content with unicode: 日本語, العربية, עברית"

    with allure.step("create article with special characters"):
        article = api_client.create_article(
            creds,
            title=special_title,
            description="Unicode test",
            body=special_body,
            tags=["unicode", "test"],
        )["article"]
        slug = article["slug"]

    with allure.step("verify content is preserved correctly"):
        fetched = api_client.get_article(slug)["article"]
        # Title might be sanitized in slug, but content should be preserved
        assert fetched["body"] == special_body, "Unicode content should be preserved"


@pytest.mark.api
def test_unauthorized_profile_update(api_client: ApiClient) -> None:
    """Test that updating profile without authentication fails."""
    creds = api_client.generate_credentials(prefix="api_unauth_profile")

    with allure.step("attempt profile update without registration"):
        with pytest.raises(ApiError) as exc_info:
            # This should fail because user is not registered/authenticated
            api_client.update_profile(creds, bio="Should fail")
        assert exc_info.value.status_code in {401, 403, 422}, "Expected auth error"


@pytest.mark.api
def test_very_long_article_content(api_client: ApiClient) -> None:
    """Test article creation with very long content (boundary test)."""
    creds = api_client.generate_credentials(prefix="api_longcontent")
    api_client.register_user(creds)

    # Create article with very long body (10KB+)
    long_body = "This is a very long article body. " * 500  # ~17KB

    with allure.step("create article with long content"):
        article = api_client.create_article(
            creds,
            title="Article with very long content",
            description="Long content test",
            body=long_body,
            tags=["boundary"],
        )["article"]
        slug = article["slug"]

    with allure.step("verify long content is stored and retrieved correctly"):
        fetched = api_client.get_article(slug)["article"]
        assert len(fetched["body"]) == len(long_body), "Long content should be preserved"
        assert fetched["body"] == long_body


@pytest.mark.api
def test_multiple_tags_on_article(api_client: ApiClient) -> None:
    """Test article with many tags."""
    creds = api_client.generate_credentials(prefix="api_tags")
    api_client.register_user(creds)

    many_tags = [f"tag{i}" for i in range(20)]

    with allure.step("create article with many tags"):
        article = api_client.create_article(
            creds,
            title="Article with many tags",
            description="Tag test",
            body="Content",
            tags=many_tags,
        )["article"]

    with allure.step("verify all tags are preserved"):
        assert len(article["tagList"]) == len(many_tags), "All tags should be preserved"
        assert set(article["tagList"]) == set(many_tags), "Tag content should match"

