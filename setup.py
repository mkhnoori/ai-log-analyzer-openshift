#!/usr/bin/env python3
"""
AI Log Analyzer — automated setup script for macOS (Apple Silicon).

Run this once from inside the ai-log-analyzer directory:
    python setup.py

What it does:
  1. Checks system requirements (macOS, Python 3.11+, Homebrew)
  2. Installs / starts Ollama
  3. Pulls llama3.1:8b and nomic-embed-text models
  4. Creates a Python virtual environment
  5. Installs all pip dependencies
  6. Verifies the installation by importing key packages
  7. Prints the start command and opens the browser when ready
"""

import os
import sys
import shutil
import subprocess
import time
import platform
import textwrap
from pathlib import Path

# ── ANSI colours ──────────────────────────────────────────────────────────────
RESET  = "\033[0m"
BOLD   = "\033[1m"
GREEN  = "\033[32m"
YELLOW = "\033[33m"
RED    = "\033[31m"
CYAN   = "\033[36m"
DIM    = "\033[2m"


def clr(text: str, color: str) -> str:
    return f"{color}{text}{RESET}"


def step(n: int, total: int, msg: str):
    bar = clr(f"[{n}/{total}]", CYAN)
    print(f"\n{bar} {BOLD}{msg}{RESET}")


def ok(msg: str):
    print(f"  {clr('✓', GREEN)} {msg}")


def warn(msg: str):
    print(f"  {clr('⚠', YELLOW)} {msg}")


def fail(msg: str):
    print(f"\n  {clr('✗ Error:', RED)} {msg}\n")
    sys.exit(1)


def run(cmd: list[str], capture: bool = True, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        capture_output=capture,
        text=True,
        check=check,
    )


def run_shell(cmd: str, capture: bool = True, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd, shell=True, capture_output=capture, text=True, check=check,
    )


# ── Step helpers ──────────────────────────────────────────────────────────────

def check_requirements():
    step(1, 7, "Checking system requirements")

    # macOS check
    if platform.system() != "Darwin":
        fail(
            "This setup script targets macOS (Apple Silicon). "
            "On Linux, install Ollama manually from https://ollama.com/download/linux "
            "then re-run this script."
        )
    ok(f"macOS {platform.mac_ver()[0]} detected")

    # Apple Silicon
    arch = platform.machine()
    if arch == "arm64":
        ok("Apple Silicon (arm64) — Metal GPU acceleration will be used")
    else:
        warn(f"Architecture: {arch} — not Apple Silicon, performance may be lower")

    # Python version
    major, minor = sys.version_info.major, sys.version_info.minor
    if major < 3 or (major == 3 and minor < 11):
        fail(
            f"Python 3.11+ required, found {major}.{minor}.\n"
            "  Install via pyenv:  pyenv install 3.11.9 && pyenv global 3.11.9\n"
            "  Or via Homebrew:    brew install python@3.11"
        )
    ok(f"Python {major}.{minor}.{sys.version_info.micro}")

    # Homebrew
    if not shutil.which("brew"):
        fail(
            "Homebrew not found.\n"
            '  Install it from:  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/'
            'Homebrew/install/HEAD/install.sh)"'
        )
    ok("Homebrew found")

    # Confirm we're in the right directory
    required = ["main.py", "config.py", "requirements.txt", ".env"]
    missing = [f for f in required if not Path(f).exists()]
    if missing:
        fail(
            f"Missing files: {', '.join(missing)}.\n"
            "  Make sure you run setup.py from inside the ai-log-analyzer directory."
        )
    ok("Project files present")


def install_ollama():
    step(2, 7, "Setting up Ollama")

    if shutil.which("ollama"):
        ok("Ollama already installed")
    else:
        print(f"  {DIM}Installing Ollama via Homebrew (this may take a moment)...{RESET}")
        try:
            run(["brew", "install", "ollama"], capture=False)
            ok("Ollama installed")
        except subprocess.CalledProcessError:
            fail(
                "Failed to install Ollama via Homebrew.\n"
                "  Install manually from https://ollama.com/download then re-run setup.py"
            )

    # Start the Ollama service
    print(f"  {DIM}Starting Ollama service...{RESET}")
    run_shell("brew services start ollama", check=False)
    time.sleep(3)

    # Wait for the API to become available
    import urllib.request
    import urllib.error
    for attempt in range(15):
        try:
            urllib.request.urlopen("http://localhost:11434", timeout=2)
            ok("Ollama service is running (http://localhost:11434)")
            return
        except Exception:
            if attempt < 14:
                print(f"  {DIM}Waiting for Ollama to start... ({attempt + 1}/15){RESET}", end="\r")
                time.sleep(2)

    fail(
        "Ollama did not start within 30 seconds.\n"
        "  Try manually: brew services restart ollama\n"
        "  Then re-run setup.py"
    )


def pull_models():
    step(3, 7, "Pulling AI models (this is the longest step — ~5 GB download)")

    models = [
        ("llama3.1:8b",       "Llama 3.1 8B — main reasoning model     (~4.7 GB)"),
        ("nomic-embed-text",   "nomic-embed-text — embedding model       (~274 MB)"),
    ]

    # Check which models are already present
    try:
        result = run(["ollama", "list"])
        already = result.stdout
    except Exception:
        already = ""

    for model_tag, description in models:
        base = model_tag.split(":")[0]
        if base in already or model_tag in already:
            ok(f"Already downloaded: {description}")
            continue

        print(f"\n  Pulling {clr(model_tag, CYAN)} — {description}")
        print(f"  {DIM}This may take several minutes depending on your connection...{RESET}")
        try:
            subprocess.run(
                ["ollama", "pull", model_tag],
                capture_output=False,
                text=True,
                check=True,
            )
            ok(f"Downloaded: {model_tag}")
        except subprocess.CalledProcessError:
            fail(f"Failed to pull model {model_tag}.\n  Try manually: ollama pull {model_tag}")


def create_venv():
    step(4, 7, "Creating Python virtual environment")

    venv_path = Path("venv")
    if venv_path.exists():
        ok("Virtual environment already exists (venv/)")
    else:
        run([sys.executable, "-m", "venv", "venv"])
        ok("Created venv/")

    # Determine pip and python paths inside venv
    if platform.system() == "Windows":
        pip    = str(venv_path / "Scripts" / "pip")
        python = str(venv_path / "Scripts" / "python")
    else:
        pip    = str(venv_path / "bin" / "pip")
        python = str(venv_path / "bin" / "python")

    if not Path(pip).exists():
        fail(f"pip not found at {pip} — virtual environment may be corrupt. Delete venv/ and retry.")

    ok(f"Python: {python}")
    ok(f"pip:    {pip}")
    return pip, python


def install_deps(pip: str):
    step(5, 7, "Installing Python dependencies")
    print(f"  {DIM}Upgrading pip...{RESET}")
    run([pip, "install", "--upgrade", "pip", "--quiet"])

    print(f"  {DIM}Installing packages from requirements.txt...{RESET}")
    try:
        subprocess.run(
            [pip, "install", "-r", "requirements.txt"],
            capture_output=False,
            text=True,
            check=True,
        )
        ok("All packages installed")
    except subprocess.CalledProcessError:
        fail(
            "pip install failed.\n"
            "  Check the error above — the most common cause is a network issue.\n"
            "  Try manually: source venv/bin/activate && pip install -r requirements.txt"
        )


def verify_install(python: str):
    step(6, 7, "Verifying installation")

    checks = [
        ("fastapi",           "FastAPI"),
        ("uvicorn",           "Uvicorn"),
        ("httpx",             "httpx"),
        ("chromadb",          "ChromaDB"),
        ("pydantic",          "Pydantic"),
        ("pydantic_settings", "pydantic-settings"),
        ("loguru",            "loguru"),
        ("tiktoken",          "tiktoken"),
    ]

    all_ok = True
    for module, name in checks:
        result = run([python, "-c", f"import {module}; print({module}.__version__ if hasattr({module}, '__version__') else 'ok')"], check=False)
        if result.returncode == 0:
            version = result.stdout.strip()
            ok(f"{name} ({version})")
        else:
            warn(f"{name} — import failed: {result.stderr.strip()[:80]}")
            all_ok = False

    if not all_ok:
        warn(
            "Some packages failed to import. The server may still work.\n"
            "  If you see errors on startup, try:\n"
            "  source venv/bin/activate && pip install -r requirements.txt --force-reinstall"
        )


def print_start_instructions():
    step(7, 7, "Setup complete!")

    width = 62
    box_top    = "┌" + "─" * width + "┐"
    box_bot    = "└" + "─" * width + "┘"
    box_mid    = "├" + "─" * width + "┤"

    def row(text: str, pad: int = 0) -> str:
        content = " " * pad + text
        spaces  = width - len(content)
        return "│" + content + " " * max(0, spaces) + "│"

    print(f"\n{clr(box_top, GREEN)}")
    print(clr(row(" AI Log Analyzer is ready to start!", 1), GREEN))
    print(clr(box_mid, GREEN))
    print(clr(row(""), GREEN))
    print(clr(row(" Start the server:", 1), GREEN))
    print(clr(row(""), GREEN))
    print(clr(row("   source venv/bin/activate", 1), GREEN))
    print(clr(row("   uvicorn main:app --host 0.0.0.0 --port 8000 --reload", 1), GREEN))
    print(clr(row(""), GREEN))
    print(clr(row(" Then open in your browser:", 1), GREEN))
    print(clr(row("   http://localhost:8000", 1), GREEN))
    print(clr(row(""), GREEN))
    print(clr(box_mid, GREEN))
    print(clr(row(""), GREEN))
    print(clr(row(" API endpoints:", 1), GREEN))
    print(clr(row("   POST /analyze    — analyze a log", 1), GREEN))
    print(clr(row("   POST /incidents  — add a resolved incident", 1), GREEN))
    print(clr(row("   POST /feedback   — submit feedback", 1), GREEN))
    print(clr(row("   GET  /health     — check server status", 1), GREEN))
    print(clr(row(""), GREEN))
    print(clr(box_bot, GREEN))

    print(f"\n{DIM}Tip: on first analysis the model loads into Metal memory (~5 s).{RESET}")
    print(f"{DIM}Subsequent requests will be much faster.{RESET}\n")

    # Ask if user wants to start right now
    try:
        answer = input("Start the server now? [Y/n] ").strip().lower()
    except (KeyboardInterrupt, EOFError):
        answer = "n"

    if answer in ("", "y", "yes"):
        _start_server()


def _start_server():
    _ = Path("venv") / "bin" / "python"
    venv_uvicorn = Path("venv") / "bin" / "uvicorn"

    if not venv_uvicorn.exists():
        print(f"\n{YELLOW}Could not find uvicorn in venv. Start manually:{RESET}")
        print("  source venv/bin/activate")
        print("  uvicorn main:app --host 0.0.0.0 --port 8000 --reload\n")
        return

    print(f"\n{clr('Starting server...', CYAN)} (Ctrl+C to stop)\n")

    # Open the browser after a short delay
    def _open_browser():
        time.sleep(4)
        import webbrowser
        webbrowser.open("http://localhost:8000")

    import threading
    t = threading.Thread(target=_open_browser, daemon=True)
    t.start()

    os.execv(
        str(venv_uvicorn),
        [str(venv_uvicorn), "main:app",
         "--host", "0.0.0.0",
         "--port", "8000",
         "--reload"],
    )


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print(f"\n{BOLD}{CYAN}{'=' * 60}")
    print("  AI Log Analyzer — Setup Script")
    print(f"{'=' * 60}{RESET}\n")
    print(f"{DIM}This script sets up everything you need to run the AI Log")
    print(f"Analyzer on your Apple Silicon Mac.{RESET}\n")

    check_requirements()
    install_ollama()
    pull_models()
    pip, python = create_venv()
    install_deps(pip)
    verify_install(python)
    print_start_instructions()


if __name__ == "__main__":
    main()
