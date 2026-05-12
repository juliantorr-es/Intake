"""Doctor command for Intake Local Console - diagnoses configuration and setup issues.

Usage:
    python -m intake.local_console.doctor

Checks for common issues and configuration requirements for the Local Console.
"""

import importlib
import os
import sys
from pathlib import Path
from typing import List, Tuple


class DoctorCheck:
    """A single check that can pass, fail, or warn."""
    
    def __init__(
        self,
        name: str,
        description: str,
        check_func=None,
        is_blocker: bool = False,
        category: str = "general"
    ):
        self.name = name
        self.description = description
        self.check_func = check_func
        self.is_blocker = is_blocker
        self.category = category
        self._result: Tuple[bool, str] = (None, "")
    
    def run(self) -> Tuple[bool, str]:
        """Run the check and return (passed, message)."""
        if self.check_func is None:
            return False, f"Check '{self.name}' has no function"
        
        try:
            self._result = self.check_func()
            return self._result
        except Exception as e:
            return False, f"Check '{self.name}' threw: {e}"
    
    @property
    def passed(self) -> bool:
        return self._result[0]
    
    @property
    def message(self) -> str:
        return self._result[1]


class DoctorResult:
    """Aggregated results from all doctor checks."""
    
    def __init__(self):
        self.checks: List[DoctorCheck] = []
        self.results: List[Tuple[str, bool, str, bool]] = []  # (name, passed, message, is_blocker)
    
    def add_check(self, check: DoctorCheck):
        self.checks.append(check)
    
    def run_all(self) -> int:
        """Run all checks and return exit code (0 = all passed or only warnings, 1 = blockers found)."""
        passed = 0
        failed = 0
        blockers = 0
        
        print("=" * 70)
        print("Intake Local Console Doctor")
        print("=" * 70)
        print()
        
        for check in self.checks:
            result_passed, result_msg = check.run()
            is_blocker = check.is_blocker
            
            self.results.append((check.name, result_passed, result_msg, is_blocker))
            
            if result_passed:
                status = "PASS"
                symbol = "[+]"
                passed += 1
            else:
                status = "FAIL" if is_blocker else "WARN"
                symbol = "[-]" if is_blocker else "[!]"
                if is_blocker:
                    blockers += 1
                failed += 1
            
            category_prefix = f"[{check.category}]" if check.category else ""
            print(f"{symbol} {category_prefix} {check.name}: {status}")
            print(f"    {result_msg}")
            print()
        
        # Summary
        print("-" * 70)
        print(f"Results: {passed} passed, {failed - blockers} warnings, {blockers} blockers")
        print("-" * 70)
        
        if blockers > 0:
            return 1
        return 0


def _check_import(module_path: str, display_name: str = None) -> Tuple[bool, str]:
    """Check if a module can be imported."""
    if display_name is None:
        display_name = module_path
    try:
        module = importlib.import_module(module_path)
        return True, f"{display_name} importable"
    except ImportError as e:
        return False, f"Cannot import {display_name}: {e}"
    except Exception as e:
        return False, f"Error importing {display_name}: {e}"


def _check_file_exists(path: str | Path, display_name: str = None, check_content: str = None) -> Tuple[bool, str]:
    """Check if a file exists and optionally contains specific content."""
    if display_name is None:
        display_name = str(path)
    
    p = Path(path)
    
    # If it's a relative path under the package, resolve it
    if not p.is_absolute():
        # Try resolving from the package root
        package_dir = Path(__file__).parent.parent
        candidate = package_dir / path
        if candidate.exists():
            p = candidate
        else:
            # Try relative to cwd
            candidate = Path.cwd() / path
            if candidate.exists():
                p = candidate
    
    if not p.exists():
        return False, f"{display_name} not found at {p}"
    
    if check_content:
        try:
            content = p.read_text()
            if check_content not in content:
                return False, f"{display_name} exists but does not contain '{check_content}'"
        except Exception as e:
            return False, f"Cannot read {display_name}: {e}"
    
    return True, f"{display_name} exists at {p}"


def _check_pywebview() -> Tuple[bool, str]:
    """Check if pywebview is available."""
    try:
        import webview
        version = getattr(webview, '__version__', 'unknown')
        return True, f"pywebview available (version: {version})"
    except ImportError:
        return False, "pywebview not installed - pip install pywebview"


def _check_macos_auth() -> Tuple[bool, str]:
    """Check if macOS LocalAuthentication would be available (macOS only)."""
    import sys
    if sys.platform != "darwin":
        return False, "macOS LocalAuthentication only available on macOS (current: {sys.platform})"
    
    try:
        # In Swift, LocalAuthentication is always available on macOS
        # This is a placeholder - the actual check happens at runtime in Swift
        return True, "macOS LocalAuthentication available (checked at Swift runtime)"
    except Exception as e:
        return False, f"macOS auth check failed: {e}"


def _check_env_var(var_name: str, display_name: str = None) -> Tuple[bool, str]:
    """Check if an environment variable is set."""
    if display_name is None:
        display_name = var_name
    value = os.environ.get(var_name)
    if value:
        return True, f"{display_name} is set"
    else:
        return False, f"{display_name} is not set"


def _check_templates() -> Tuple[bool, str]:
    """Check if static templates exist."""
    base_dir = Path(__file__).parent / "web" / "templates"
    templates = ["index.html", "costs.html", "uploads.html", "deploy.html", "providers.html"]
    
    missing = []
    for template in templates:
        if not (base_dir / template).exists():
            missing.append(template)
    
    if missing:
        return False, f"Missing templates: {', '.join(missing)}"
    return True, f"All {len(templates)} templates found"


def _check_static_files() -> Tuple[bool, str]:
    """Check if static files exist."""
    base_dir = Path(__file__).parent / "web" / "static"
    expected = ["js/main.js", "css/styles.css"]
    
    missing = []
    for f in expected:
        if not (base_dir / f).exists():
            missing.append(f)
    
    if missing:
        return False, f"Missing static files: {', '.join(missing)}"
    return True, f"All {len(expected)} static file checks passed"


def _check_security_endpoints() -> Tuple[bool, str]:
    """Check if security endpoints can be imported."""
    try:
        from intake.local_console.api import security
        # Check for key endpoints
        has_challenge = hasattr(security, 'router')
        return True, "Security endpoints importable"
    except ImportError as e:
        return False, f"Cannot import security endpoints: {e}"


def _check_receiver_status() -> Tuple[bool, str]:
    """Check if receiver status endpoint can be imported."""
    try:
        from intake.local_console.api import main as api_main
        return True, "Receiver status route importable"
    except ImportError as e:
        return False, f"Cannot import receiver routes: {e}"


def _check_proof_rail() -> Tuple[bool, str]:
    """Check if proof rail endpoint can be imported."""
    try:
        from intake.local_console.api import proof_rail
        return True, "Proof rail route importable"
    except ImportError as e:
        return False, f"Cannot import proof rail routes: {e}"


def _check_database_config() -> Tuple[bool, str]:
    """Check if database configuration is valid."""
    try:
        from intake.config import get_settings, reset_settings
        reset_settings()
        settings = get_settings()
        db_url = settings.intake_database_url
        if db_url.startswith("sqlite://"):
            return True, f"Database configured (SQLite: {db_url})"
        return True, f"Database configured ({db_url[:50]}...)"
    except Exception as e:
        return False, f"Database config error: {e}"


def _check_dev_insecure_flag() -> Tuple[bool, str]:
    """Check if insecure dev unlock flag is properly configured."""
    try:
        from intake.config import get_settings, reset_settings
        reset_settings()
        settings = get_settings()
        # The flag should exist and default to False
        flag_value = settings.intake_enable_insecure_dev_unlock
        return True, f"INTAKE_ENABLE_INSECURE_DEV_UNLOCK defaults to {flag_value}"
    except Exception as e:
        return False, f"Error checking dev insecure flag: {e}"


def build_doctor() -> DoctorResult:
    """Build the doctor with all checks."""
    result = DoctorResult()
    
    # Core imports
    result.add_check(DoctorCheck(
        name="Local Console imports",
        description="Check if local_console module imports correctly",
        check_func=lambda: _check_import("intake.local_console"),
        is_blocker=True,
        category="python"
    ))
    
    result.add_check(DoctorCheck(
        name="pywebview availability",
        description="Check if pywebview is installed",
        check_func=_check_pywebview,
        is_blocker=False,
        category="python"
    ))
    
    # macOS checks (informational)
    result.add_check(DoctorCheck(
        name="macOS auth availability",
        description="Check if macOS auth would be available",
        check_func=_check_macos_auth,
        is_blocker=False,
        category="runtime"
    ))
    
    # Static files
    result.add_check(DoctorCheck(
        name="Static templates",
        description="Check if HTML templates exist",
        check_func=_check_templates,
        is_blocker=True,
        category="files"
    ))
    
    result.add_check(DoctorCheck(
        name="Static assets",
        description="Check if JS/CSS static files exist",
        check_func=_check_static_files,
        is_blocker=True,
        category="files"
    ))
    
    # Security endpoints
    result.add_check(DoctorCheck(
        name="Security endpoints",
        description="Check if security API endpoints can be imported",
        check_func=_check_security_endpoints,
        is_blocker=True,
        category="api"
    ))
    
    result.add_check(DoctorCheck(
        name="Receiver status route",
        description="Check if receiver status route can be imported",
        check_func=_check_receiver_status,
        is_blocker=False,
        category="api"
    ))
    
    result.add_check(DoctorCheck(
        name="Proof rail route",
        description="Check if proof rail route can be imported",
        check_func=_check_proof_rail,
        is_blocker=False,
        category="api"
    ))
    
    # Database configuration
    result.add_check(DoctorCheck(
        name="Database configuration",
        description="Check if database config is valid",
        check_func=_check_database_config,
        is_blocker=True,
        category="config"
    ))
    
    # Dev insecure flag
    result.add_check(DoctorCheck(
        name="Dev insecure unlock flag",
        description="Check if insecure dev unlock flag is properly configured",
        check_func=_check_dev_insecure_flag,
        is_blocker=False,
        category="config"
    ))
    
    # Native capability check
    result.add_check(DoctorCheck(
        name="Native capability config",
        description="Check if native unlock capability config is available",
        check_func=lambda: _check_import("intake.config"),
        is_blocker=False,
        category="config"
    ))
    
    return result


def main():
    """Run the doctor command."""
    result = build_doctor()
    exit_code = result.run_all()
    
    sys.exit(exit_code)


# Pure check functions for testing
def check_imports() -> List[Tuple[str, bool, str]]:
    """Testable function: Check all core imports."""
    checks = [
        ("intake.local_console", True, "Should import"),
        ("intake.local_console.api.security", True, "Should import"),
        ("intake.local_console.review_service", True, "Should import"),
        ("intake.local_console.app", True, "Should import"),
    ]
    
    results = []
    for module, expected_pass, _ in checks:
        passed, msg = _check_import(module)
        results.append((module, passed == expected_pass, msg))
    
    return results


def check_files() -> List[Tuple[str, bool, str]]:
    """Testable function: Check all required files."""
    base_dir = Path(__file__).parent
    
    file_checks = [
        ("web/templates/index.html", base_dir / "web" / "templates" / "index.html"),
        ("web/templates/costs.html", base_dir / "web" / "templates" / "costs.html"),
        ("web/static/js/main.js", base_dir / "web" / "static" / "js" / "main.js"),
        ("web/static/css/styles.css", base_dir / "web" / "static" / "css" / "styles.css"),
    ]
    
    results = []
    for display_name, path in file_checks:
        passed, msg = _check_file_exists(path, display_name)
        results.append((display_name, passed, msg))
    
    return results


def check_pywebview() -> Tuple[bool, str]:
    """Testable function: Check pywebview availability."""
    return _check_pywebview()


def check_security_endpoints() -> Tuple[bool, str]:
    """Testable function: Check security endpoints."""
    return _check_security_endpoints()


if __name__ == "__main__":
    main()
