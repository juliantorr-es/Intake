"""Entry point for running intake as a module."""

import uvicorn

if __name__ == "__main__":
    uvicorn.run("intake.app:app", host="0.0.0.0", port=8000, reload=True)
