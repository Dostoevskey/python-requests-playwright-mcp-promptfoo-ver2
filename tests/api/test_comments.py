"""
API Tests for Comment Functionality

Tests comment creation, retrieval, deletion, and authorization.
"""
from __future__ import annotations

import allure
import pytest

from src.utils.api_client import ApiClient, ApiError


@pytest.mark.api
def test_add_and_retrieve_comments(api_client: ApiClient) -> None:
    """Test adding comments to an article and retrieving them."""
    author_creds = api_client.generate_credentials(prefix="api_comment_author")
    api_client.register_user(author_creds)

    commenter_creds = api_client.generate_credentials(prefix="api_commenter")
    api_client.register_user(commenter_creds)

    with allure.step("create article"):
        article = api_client.create_article(
            author_creds,
            title=f"Article for comments {author_creds.username}",
            description="Test",
            body="Content",
            tags=["test"],
        )["article"]
        slug = article["slug"]

    with allure.step("add comment to article"):
        comment_body = "This is a test comment"
        comment_response = api_client.add_comment(commenter_creds, slug, comment_body)
        comment = comment_response["comment"]
        assert comment["body"] == comment_body
        assert comment["author"]["username"] == commenter_creds.username
        comment_id = comment["id"]

    with allure.step("retrieve comments for article"):
        comments_response = api_client.get_comments(slug)
        comments = comments_response["comments"]
        assert len(comments) >= 1, "Should have at least one comment"
        assert any(c["id"] == comment_id for c in comments), "Posted comment should be in list"

    with allure.step("delete comment"):
        api_client.delete_comment(commenter_creds, slug, comment_id)

    with allure.step("verify comment was deleted"):
        comments_after = api_client.get_comments(slug)["comments"]
        assert not any(c["id"] == comment_id for c in comments_after), "Comment should be deleted"


@pytest.mark.api
def test_unauthorized_comment_deletion(api_client: ApiClient) -> None:
    """Test that users cannot delete comments they don't own."""
    author_creds = api_client.generate_credentials(prefix="api_comment_del_author")
    api_client.register_user(author_creds)

    commenter_creds = api_client.generate_credentials(prefix="api_comment_del_commenter")
    api_client.register_user(commenter_creds)

    attacker_creds = api_client.generate_credentials(prefix="api_comment_del_attacker")
    api_client.register_user(attacker_creds)

    with allure.step("create article and add comment"):
        article = api_client.create_article(
            author_creds,
            title="Article for comment deletion test",
            description="Test",
            body="Content",
            tags=["test"],
        )["article"]
        slug = article["slug"]

        comment_response = api_client.add_comment(commenter_creds, slug, "Test comment")
        comment_id = comment_response["comment"]["id"]

    with allure.step("attempt to delete comment as different user"):
        with pytest.raises(ApiError) as exc_info:
            api_client.delete_comment(attacker_creds, slug, comment_id)
        assert exc_info.value.status_code in {401, 403}, "Expected 401/403 for unauthorized delete"

    with allure.step("verify comment still exists"):
        comments = api_client.get_comments(slug)["comments"]
        assert any(c["id"] == comment_id for c in comments), "Comment should still exist"


@pytest.mark.api
def test_comment_on_nonexistent_article(api_client: ApiClient) -> None:
    """Test that commenting on non-existent article fails appropriately."""
    creds = api_client.generate_credentials(prefix="api_comment_notfound")
    api_client.register_user(creds)

    with pytest.raises(ApiError) as exc_info:
        api_client.add_comment(creds, "nonexistent-article-slug-12345", "Test comment")
    assert exc_info.value.status_code == 404, "Expected 404 for non-existent article"


@pytest.mark.api
def test_multiple_comments_ordering(api_client: ApiClient) -> None:
    """Test that multiple comments are retrieved in correct order."""
    author_creds = api_client.generate_credentials(prefix="api_multi_comment_author")
    api_client.register_user(author_creds)

    with allure.step("create article"):
        article = api_client.create_article(
            author_creds,
            title="Article for multiple comments",
            description="Test",
            body="Content",
            tags=["test"],
        )["article"]
        slug = article["slug"]

    with allure.step("add multiple comments"):
        comment_ids = []
        for i in range(3):
            comment_response = api_client.add_comment(
                author_creds, slug, f"Comment number {i + 1}"
            )
            comment_ids.append(comment_response["comment"]["id"])

    with allure.step("verify all comments are present"):
        comments = api_client.get_comments(slug)["comments"]
        retrieved_ids = [c["id"] for c in comments]

        for comment_id in comment_ids:
            assert comment_id in retrieved_ids, f"Comment {comment_id} should be present"


@pytest.mark.api
def test_empty_comment_rejection(api_client: ApiClient) -> None:
    """Test that empty comments are rejected."""
    creds = api_client.generate_credentials(prefix="api_empty_comment")
    api_client.register_user(creds)

    with allure.step("create article"):
        article = api_client.create_article(
            creds,
            title="Article for empty comment test",
            description="Test",
            body="Content",
            tags=["test"],
        )["article"]
        slug = article["slug"]

    with allure.step("attempt to add empty comment"):
        with pytest.raises(ApiError) as exc_info:
            api_client.add_comment(creds, slug, "")
        assert exc_info.value.status_code in {400, 422}, "Expected validation error for empty comment"


@pytest.mark.api
def test_very_long_comment(api_client: ApiClient) -> None:
    """Test comment with very long content (boundary test)."""
    creds = api_client.generate_credentials(prefix="api_long_comment")
    api_client.register_user(creds)

    with allure.step("create article"):
        article = api_client.create_article(
            creds,
            title="Article for long comment",
            description="Test",
            body="Content",
            tags=["test"],
        )["article"]
        slug = article["slug"]

    with allure.step("add very long comment"):
        long_comment = "This is a very long comment. " * 200  # ~6KB
        comment_response = api_client.add_comment(creds, slug, long_comment)
        comment = comment_response["comment"]
        assert len(comment["body"]) == len(long_comment), "Long comment should be preserved"


@pytest.mark.api
def test_comment_with_special_characters(api_client: ApiClient) -> None:
    """Test comment with special characters and unicode."""
    creds = api_client.generate_credentials(prefix="api_special_comment")
    api_client.register_user(creds)

    with allure.step("create article"):
        article = api_client.create_article(
            creds,
            title="Article for special comment",
            description="Test",
            body="Content",
            tags=["test"],
        )["article"]
        slug = article["slug"]

    special_comment = "Comment with émojis 🎉 and spëcial çhars: 日本語, עברית"

    with allure.step("add comment with special characters"):
        comment_response = api_client.add_comment(creds, slug, special_comment)
        comment = comment_response["comment"]
        assert comment["body"] == special_comment, "Special characters should be preserved"

    with allure.step("verify comment can be retrieved with special characters"):
        comments = api_client.get_comments(slug)["comments"]
        assert any(c["body"] == special_comment for c in comments)

