from intake.local_console.app import app

print("Local Console App Routes:")
for route in app.routes:
    if hasattr(route, "path"):
        print(f"  {route.path}")
    elif hasattr(route, "routes"):
        for subroute in route.routes:
             print(f"  {route.path}{subroute.path}")
