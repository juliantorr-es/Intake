import sys
import os
from pathlib import Path

# Add src to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from intake.storage.repositories import AccountRepository
from intake.domain.accounts import Account
from intake.services.session_service import get_session_service
from intake.services.quote_service import get_quote_service
from intake.domain.quotes import QuoteServiceLane, QuoteStatus

def bootstrap():
    # 1. Create account
    repo = AccountRepository()
    account_id = "dogfood-user"
    if not repo.get(account_id):
        from intake.domain.time import utc_now
        acc = Account(id=account_id, email_verified_at=utc_now())
        repo.create(acc)
        print(f"Created account: {account_id}")
    else:
        from intake.domain.time import utc_now
        acc = repo.get_by_id(account_id)
        acc.email_verified_at = utc_now()
        repo.update(acc)
        print(f"Account {account_id} already exists (verified now)")

    # 2. Create session
    session_svc = get_session_service()
    session = session_svc.create_session(account_id)
    print(f"SESSION_ID: {session.id}")

    # 3. Create quote
    quote_svc = get_quote_service()
    quote = quote_svc.create_quote(service_lane=QuoteServiceLane.PRACTICAL_HELP)
    quote_svc.add_basic_info(quote.id, "Dogfood Quote", "Testing Secure Unlock", "asap")
    quote_svc.add_location(quote.id, "Local Test Area", "123 Workshop Lane")
    
    # Submit it so it shows up in local console
    quote_svc.submit_quote(quote.id, account_id)
    print(f"QUOTE_ID: {quote.id}")
    print("Quote submitted and ready for local sync.")

if __name__ == "__main__":
    bootstrap()
