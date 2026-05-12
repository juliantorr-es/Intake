import sys
from pathlib import Path
from datetime import datetime, timezone

# Add src to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from intake.storage.repositories import SyncRepository
from intake.storage.models import RegisteredDeviceModel

def register():
    repo = SyncRepository()
    device_id = "dev-device-1"
    public_key = "NVLgm6zPT6VmFYuLYYNhqpEKC1HkxYKz40Z+lOg+/DA="
    
    # Check if already exists
    existing = repo.get_device(device_id)
    if existing:
        # Update it to ensure it's trusted and has correct key
        from sqlmodel import Session, select
        from intake.storage.db import get_session
        with get_session() as session:
            model = session.get(RegisteredDeviceModel, device_id)
            model.public_signing_key = public_key
            model.trust_state = "trusted"
            model.last_seen_at = datetime.now(timezone.utc)
            session.add(model)
            session.commit()
        print(f"Updated device: {device_id}")
    else:
        # Create new
        from sqlmodel import Session
        from intake.storage.db import get_session
        with get_session() as session:
            model = RegisteredDeviceModel(
                device_id=device_id,
                display_name="Dev Dogfood Device",
                public_signing_key=public_key,
                trust_state="trusted"
            )
            session.add(model)
            session.commit()
        print(f"Registered device: {device_id}")

if __name__ == "__main__":
    register()
