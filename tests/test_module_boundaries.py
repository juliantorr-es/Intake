"""Tests to enforce module boundaries between hosted and local_console."""

import sys
import os
import subprocess
import pytest

def test_hosted_does_not_import_local_console():
    """Verify that hosted modules do not import from local_console."""
    # We check if any hosted module already in sys.modules has a dependency on local_console
    # This is a bit tricky to test statically without a full tree scan, 
    # but we can try to import a hosted module and check its references.
    
    # Ensure local_console is NOT in sys.modules
    local_console_modules = [m for m in sys.modules if m.startswith("intake.local_console")]
    
    # This is more of a structural check. 
    # We'll use a simple grep-like check on the codebase.
    import subprocess
    import os
    
    src_root = os.path.join(os.getcwd(), "src", "intake", "hosted")
    
    # Look for 'from intake.local_console' or 'import intake.local_console'
    result = subprocess.run(
        ["grep", "-r", "intake.local_console", src_root],
        capture_output=True,
        text=True
    )
    
    assert result.returncode == 1, f"Hosted module imports local_console:\n{result.stdout}"

def test_local_console_does_not_import_hosted_api_directly():
    """Verify that local_console does not import hosted API routers directly."""
    src_root = os.path.join(os.getcwd(), "src", "intake", "local_console")
    
    # Look for imports of hosted API or web routers
    result = subprocess.run(
        ["grep", "-r", "intake.hosted.api", src_root],
        capture_output=True,
        text=True
    )
    assert result.returncode == 1, f"Local console imports hosted API directly:\n{result.stdout}"
    
    result = subprocess.run(
        ["grep", "-r", "intake.hosted.auth", src_root],
        capture_output=True,
        text=True
    )
    assert result.returncode == 1, f"Local console imports hosted Auth directly:\n{result.stdout}"
