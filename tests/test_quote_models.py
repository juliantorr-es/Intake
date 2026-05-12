"""Tests for quote domain models."""

import pytest

from intake.domain.quotes import (
    Quote,
    QuoteServiceLane,
    QuoteStatus,
    Upload,
    UploadStatus,
)


def test_quote_creation_defaults():
    """Test that quote has correct defaults."""
    quote = Quote()
    assert quote.status == QuoteStatus.DRAFT
    assert quote.service_lane is None
    assert quote.account_id is None
    assert quote.short_summary == ""
    assert quote.detailed_description == ""
    assert quote.preferred_timeline is None
    assert quote.general_service_area == ""
    assert quote.encrypted_exact_location is None
    assert quote.encrypted_access_notes is None
    assert quote.encrypted_questionnaire is None
    assert quote.uploads == []


def test_quote_creation_with_values():
    """Test quote creation with custom values."""
    quote = Quote(
        service_lane=QuoteServiceLane.SOFTWARE_SYSTEMS,
        short_summary="Test summary",
        status=QuoteStatus.DRAFT,
    )
    assert quote.service_lane == QuoteServiceLane.SOFTWARE_SYSTEMS
    assert quote.short_summary == "Test summary"
    assert quote.status == QuoteStatus.DRAFT


def test_quote_service_lanes():
    """Test all service lane values."""
    lanes = [
        QuoteServiceLane.SOFTWARE_SYSTEMS,
        QuoteServiceLane.PHOTOGRAPHY,
        QuoteServiceLane.PRACTICAL_HELP,
        QuoteServiceLane.UNSURE,
    ]
    for lane in lanes:
        assert lane.value in ["software_systems", "photography", "practical_help", "unsure"]


def test_quote_statuses():
    """Test all quote status values."""
    statuses = [
        QuoteStatus.DRAFT,
        QuoteStatus.SUBMITTED,
        QuoteStatus.NEEDS_REVIEW,
        QuoteStatus.REVIEWING,
        QuoteStatus.QUOTED,
        QuoteStatus.ACCEPTED,
        QuoteStatus.DECLINED,
        QuoteStatus.CLOSED,
    ]
    expected_values = ["draft", "submitted", "needs_review", "reviewing", "quoted", "accepted", "declined", "closed"]
    for status in statuses:
        assert status.value in expected_values


def test_quote_can_submit():
    """Test quote can_submit method."""
    # Draft with service lane can submit
    quote1 = Quote(service_lane=QuoteServiceLane.SOFTWARE_SYSTEMS, status=QuoteStatus.DRAFT)
    assert quote1.can_submit() is True

    # Draft without service lane cannot submit
    quote2 = Quote(service_lane=None, status=QuoteStatus.DRAFT)
    assert quote2.can_submit() is False

    # Submitted quote cannot submit
    quote3 = Quote(service_lane=QuoteServiceLane.SOFTWARE_SYSTEMS, status=QuoteStatus.SUBMITTED)
    assert quote3.can_submit() is False


def test_quote_can_review():
    """Test quote can_review method."""
    # Need to fix: can_review should be True for SUBMITTED and NEEDS_REVIEW
    statuses_that_can_review = [QuoteStatus.SUBMITTED, QuoteStatus.NEEDS_REVIEW]
    statuses_that_cannot_review = [
        QuoteStatus.DRAFT,
        QuoteStatus.REVIEWING,
        QuoteStatus.QUOTED,
        QuoteStatus.ACCEPTED,
        QuoteStatus.DECLINED,
        QuoteStatus.CLOSED,
    ]

    for status in statuses_that_can_review:
        quote = Quote(status=status)
        assert quote.can_review() is True, f"Status {status.value} should be able to review"

    for status in statuses_that_cannot_review:
        quote = Quote(status=status)
        assert quote.can_review() is False, f"Status {status.value} should not be able to review"


def test_quote_get_safe_summary():
    """Test quote get_safe_summary method."""
    quote = Quote(
        id="test-id",
        service_lane=QuoteServiceLane.PHOTOGRAPHY,
        short_summary="Test Summary",
        detailed_description="Detailed description",
        general_service_area="Test Area",
        status=QuoteStatus.DRAFT,
        uploads=[
            Upload(
                quote_id="test-id", 
                account_id="user-1", 
                storage_object_id="obj1", 
                storage_relative_path="path1", 
                encrypted_original_filename={"ciphertext": "enc:test.jpg", "nonce": "nonce"},
                extension=".jpg",
                declared_content_type="image/jpeg",
                size_bytes=1024
            ),
            Upload(
                quote_id="test-id", 
                account_id="user-1", 
                storage_object_id="obj2", 
                storage_relative_path="path2", 
                encrypted_original_filename={"ciphertext": "enc:test2.png", "nonce": "nonce"},
                extension=".png",
                declared_content_type="image/png",
                size_bytes=2048
            ),
        ],
    )

    summary = quote.get_safe_summary()

    assert summary["id"] == "test-id"
    assert summary["service_lane"] == QuoteServiceLane.PHOTOGRAPHY
    assert summary["short_summary"] == "Test Summary"
    assert summary["general_service_area"] == "Test Area"
    assert summary["status"] == QuoteStatus.DRAFT
    assert summary["upload_count"] == 2

    # Should not include sensitive data
    assert "detailed_description" not in summary
    assert "encrypted_exact_location" not in summary
    assert "uploads" not in summary


def test_upload_model():
    """Test upload domain model."""
    upload = Upload(
        quote_id="quote-1",
        account_id="user-1",
        storage_object_id="storage-1",
        storage_relative_path="rel/path",
        encrypted_original_filename={"ciphertext": "enc:doc.pdf", "nonce": "nonce"},
        extension=".pdf",
        declared_content_type="application/pdf",
        size_bytes=102400,
    )

    assert upload.quote_id == "quote-1"
    assert upload.declared_content_type == "application/pdf"
    assert upload.size_bytes == 102400


def test_quote_aggregate_type():
    """Test quote aggregate type."""
    from intake.domain.events import EventAggregateType

    quote = Quote()
    assert quote.aggregate_type == EventAggregateType.QUOTE


def test_quote_status_transitions():
    """Test valid quote status transitions."""
    # This is more of a documentation test
    # Valid transitions:
    # DRAFT -> SUBMITTED
    # SUBMITTED -> NEEDS_REVIEW
    # NEEDS_REVIEW -> REVIEWING
    # REVIEWING -> QUOTED
    # QUOTED -> ACCEPTED or DECLINED
    # ACCEPTED -> CLOSED
    # DECLINED -> CLOSED

    quote = Quote(status=QuoteStatus.DRAFT)
    quote.status = QuoteStatus.SUBMITTED
    assert quote.status == QuoteStatus.SUBMITTED

    quote.status = QuoteStatus.NEEDS_REVIEW
    assert quote.status == QuoteStatus.NEEDS_REVIEW

    quote.status = QuoteStatus.REVIEWING
    assert quote.status == QuoteStatus.REVIEWING

    quote.status = QuoteStatus.QUOTED
    assert quote.status == QuoteStatus.QUOTED

    quote.status = QuoteStatus.ACCEPTED
    assert quote.status == QuoteStatus.ACCEPTED

    quote.status = QuoteStatus.CLOSED
    assert quote.status == QuoteStatus.CLOSED
