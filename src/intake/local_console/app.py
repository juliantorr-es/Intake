"""Main entrypoint for the Local Intake Console window app."""

import threading
import uvicorn
import webview
import socket
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from fastapi import Request
import os
import sys

from intake.local_console.api import router as api_router

def find_free_port():
    """Find a free port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]

# Create the local app
app = FastAPI(title="Intake Local Console")

# Add API
app.include_router(api_router, prefix="/api/local")

# Setup templates and static files
# In a real package, we'd use importlib.resources
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "web/static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "web/templates"))

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Render the main console UI."""
    return templates.TemplateResponse("index.html", {"request": request, "view": "dashboard"})


@app.get("/quotes", response_class=HTMLResponse)
async def quotes_view(request: Request):
    """Render the quotes list view."""
    return templates.TemplateResponse("index.html", {"request": request, "view": "quotes"})


@app.get("/settings", response_class=HTMLResponse)
async def settings_view(request: Request):
    """Render the settings view."""
    return templates.TemplateResponse("index.html", {"request": request, "view": "settings"})


@app.get("/costs", response_class=HTMLResponse)
async def costs_view(request: Request):
    """Render the Vendor Cost Ledger UI."""
    return templates.TemplateResponse("costs.html", {"request": request})


@app.get("/uploads", response_class=HTMLResponse)
async def uploads_view(request: Request):
    """Render the uploads view."""
    return templates.TemplateResponse("uploads.html", {"request": request})


@app.get("/deploy", response_class=HTMLResponse)
async def deploy_view(request: Request):
    """Render the deployment readiness view."""
    return templates.TemplateResponse("deploy.html", {"request": request})


@app.get("/providers", response_class=HTMLResponse)
async def providers_view(request: Request):
    """Render the providers view."""
    return templates.TemplateResponse("providers.html", {"request": request})

def run_server(port):
    """Run the local FastAPI server."""
    # Force 127.0.0.1 for security
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")

def main():
    """Start the local console app."""
    # Use environment variable or find a free port
    env_port = os.environ.get("INTAKE_LOCAL_PORT")
    if env_port:
        port = int(env_port)
    else:
        port = find_free_port()
    
    url = f"http://127.0.0.1:{port}"
    headless = os.environ.get("INTAKE_HEADLESS") == "1"
    
    if headless:
        print(f"Local Console Server started in HEADLESS mode at {url}")
        run_server(port)
    else:
        # Start server in a background thread
        server_thread = threading.Thread(target=run_server, args=(port,), daemon=True)
        server_thread.start()
        
        print(f"Local Console Server started at {url}")
        
        # Create pywebview window
        webview.create_window(
            "Intake Local Console",
            url,
            width=1024,
            height=768,
            min_size=(800, 600)
        )
        
        # Start webview loop (this blocks until window closed)
        webview.start()
        
        print("Local Console closed.")

if __name__ == "__main__":
    main()
