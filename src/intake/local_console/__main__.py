"""Main entry point for running intake.local_console as a module."""

import sys

if __name__ == "__main__":
    # Check if we're running the doctor
    if len(sys.argv) > 1 and sys.argv[1] == "doctor":
        from intake.local_console.doctor import main
        main()
    else:
        # Run the local console app by default
        from intake.local_console.app import main as app_main
        app_main()
