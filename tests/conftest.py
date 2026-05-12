import pytest
from intake.storage.db import create_all_tables, drop_all_tables, reset_engine

@pytest.fixture(autouse=True)
def db_setup():
    """Shared database setup and teardown for all tests."""
    # Reset engine to ensure we pick up fresh settings/connection
    reset_engine()
    
    # Create all tables
    create_all_tables()
    
    yield
    
    # We don't drop tables by default to allow inspection on failure 
    # if using a file-backed DB, but autouse=True ensures a clean 
    # start for the next test if tables are recreated.
