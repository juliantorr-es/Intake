"""CLI entry point for the operator console."""

import argparse
import sys
from typing import Any

# WARNING: This CLI is for DEVELOPMENT and DIAGNOSTIC purposes only.
# It is NOT a product surface and should not be used by end-users.
# The actual management surface is the Local Intake Console application.

from intake.config import get_settings
from intake.local_console.decrypt_utils import decrypt_quote_payload
from intake.storage.repositories import QuoteRepository


def list_quotes(args: argparse.Namespace) -> int:
    """List all quotes."""
    repo = QuoteRepository()
    try:
        quotes = repo.get_all()
        if not quotes:
            print("No quotes found.")
            return 0

        print(f"{'ID':<36} {'Status':<12} {'Service Lane':<20} {'Summary'}")
        print("-" * 80)
        for quote in quotes:
            service_lane = quote.service_lane.value if quote.service_lane else "none"
            summary = quote.short_summary[:40] if quote.short_summary else ""
            print(f"{quote.id:<36} {quote.status.value:<12} {service_lane:<20} {summary}")
        return 0
    except Exception as e:
        print(f"Error listing quotes: {e}", file=sys.stderr)
        return 1


def show_quote(args: argparse.Namespace) -> int:
    """Show quote details (safe summary)."""
    repo = QuoteRepository()
    try:
        quote = repo.get(args.quote_id)
        if not quote:
            print(f"Quote {args.quote_id} not found.", file=sys.stderr)
            return 1

        domain_quote = quote.to_domain()
        summary = domain_quote.get_safe_summary()

        print("Quote Details (Safe Summary)")
        print("-" * 40)
        for key, value in summary.items():
            print(f"  {key}: {value}")

        print("\nEncrypted fields:")
        print(f"  Has encrypted location: {domain_quote.encrypted_exact_location is not None}")
        print(f"  Has encrypted access notes: {domain_quote.encrypted_access_notes is not None}")
        print(f"  Has encrypted questionnaire: {domain_quote.encrypted_questionnaire is not None}")

        return 0
    except Exception as e:
        print(f"Error showing quote: {e}", file=sys.stderr)
        return 1


def decrypt_quote(args: argparse.Namespace) -> int:
    """Decrypt and show sensitive quote payload."""
    from intake.local_console.decrypt_utils import decrypt_quote_full

    try:
        result = decrypt_quote_full(args.quote_id)
        if not result:
            print(f"Quote {args.quote_id} not found.", file=sys.stderr)
            return 1

        print("Decrypted Quote Payload")
        print("=" * 40)

        safe, sensitive = result
        print("\n[SAFE DATA]")
        for key, value in safe.items():
            print(f"  {key}: {value}")

        print("\n[SENSITIVE DATA - DECRYPTED]")
        for key, value in sensitive.items():
            print(f"  {key}: {value}")

        return 0
    except Exception as e:
        print(f"Error decrypting quote: {e}", file=sys.stderr)
        return 1


def sync_review(args: argparse.Namespace) -> int:
    """Sync and review quotes from hosted backend via outbound API."""
    from intake.local_console.review_service import LocalQuoteReviewService
    from intake.local_console.sync_client import LocalSyncClient

    try:
        client = LocalSyncClient(sync_token=args.token)
        service = LocalQuoteReviewService(sync_client=client)

        print("Fetching pending quote projections from hosted backend...")
        pending = service.get_pending_reviews()

        if not pending:
            print("No quotes pending review.")
            return 0

        print(f"Found {len(pending)} pending quotes:")
        print(f"{'ID':<36} {'Status':<12} {'Area':<20} {'Uploads'}")
        print("-" * 80)
        for p in pending:
            print(f"{p.quote_id:<36} {p.status:<12} {p.general_service_area or 'N/A':<20} {p.upload_count}")

        if args.quote_id:
            print(f"\nFetching and decrypting envelope for quote {args.quote_id}...")
            review = service.get_decrypted_review(args.quote_id)
            
            print("\n=== Decrypted Local Review ===")
            print(f"  ID: {review.quote_id}")
            print(f"  Status: {review.status}")
            print(f"  Location: {review.exact_location or 'N/A'}")
            print(f"  Notes: {review.access_notes or 'N/A'}")
            print(f"  Questionnaire: {review.questionnaire_answers or 'N/A'}")
            print(f"  Decrypted Filenames: {review.decrypted_filenames}")

        return 0
    except Exception as e:
        print(f"Sync failed: {e}", file=sys.stderr)
        return 1


def main(argv: list[str] | None = None) -> int:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="intake-operator",
        description="Intake Operator Console - Local CLI for reviewing and decrypting quotes",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # list-quotes
    list_parser = subparsers.add_parser("list-quotes", help="List all quotes")
    list_parser.set_defaults(func=list_quotes)

    # show-quote
    show_parser = subparsers.add_parser("show-quote", help="Show quote details")
    show_parser.add_argument("quote_id", help="ID of the quote to show")
    show_parser.set_defaults(func=show_quote)

    # decrypt-quote
    decrypt_parser = subparsers.add_parser("decrypt-quote", help="Decrypt quote payload")
    decrypt_parser.add_argument("quote_id", help="ID of the quote to decrypt")
    decrypt_parser.set_defaults(func=decrypt_quote)

    # sync-review
    sync_parser = subparsers.add_parser("sync-review", help="Sync and review quotes via hosted API")
    sync_parser.add_argument("--token", help="Temporary sync token (overrides env)")
    sync_parser.add_argument("--quote-id", help="Optional quote ID to decrypt after listing")
    sync_parser.set_defaults(func=sync_review)

    args = parser.parse_args(argv)

    if not hasattr(args, "func"):
        parser.print_help()
        return 1

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
