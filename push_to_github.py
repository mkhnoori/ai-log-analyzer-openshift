#!/usr/bin/env python3
"""
push_to_github.py — creates the GitHub repo and pushes all project files.

Run from inside the ai-log-analyzer directory:
    python push_to_github.py

What it does:
  1. Checks git and GitHub CLI (gh) are installed
  2. Checks you are logged in to GitHub CLI
  3. Initialises a local git repo if needed
  4. Creates the remote repo mkhnoori/ai-log-analyzer-openshift on GitHub
  5. Commits all files
  6. Pushes to main branch
  7. Prints the repo URL
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path

RESET  = "\033[0m"
BOLD   = "\033[1m"
GREEN  = "\033[32m"
YELLOW = "\033[33m"
RED    = "\033[31m"
CYAN   = "\033[36m"

GITHUB_USER = "mkhnoori"
REPO_NAME   = "ai-log-analyzer-openshift"
REPO_DESC   = (
    "Fully local AI system that analyzes CI/CD logs to find root causes — "
    "deployed on OpenShift Local with Ollama on Apple Silicon"
)


def ok(msg):   print(f"  {GREEN}✓{RESET} {msg}")
def info(msg): print(f"  {CYAN}→{RESET} {msg}")
def warn(msg): print(f"  {YELLOW}⚠{RESET} {msg}")
def fail(msg):
    print(f"\n  {RED}\u2717 Error:{RESET} {msg}\n")
    sys.exit(1)
def step(n, t, msg): print(f"\n{BOLD}{CYAN}[{n}/{t}]{RESET} {BOLD}{msg}{RESET}")


def run(cmd, check=True, capture=True):
    return subprocess.run(cmd, shell=True, capture_output=capture,
                          text=True, check=check)


def main():
    print(f"\n{BOLD}{CYAN}{'='*50}")
    print(f"  Push to GitHub: {GITHUB_USER}/{REPO_NAME}")
    print(f"{'='*50}{RESET}\n")

    # ── Step 1: Check we're in the right directory ──────────────────────────
    step(1, 6, "Checking project directory")

    cwd = Path.cwd()
    required = ["main.py", "Dockerfile", "requirements.txt", "openshift"]
    missing = [f for f in required if not Path(f).exists()]
    if missing:
        fail(
            f"Missing files/dirs: {', '.join(missing)}\n"
            f"  Run this script from inside the ai-log-analyzer directory.\n"
            f"  Current directory: {cwd}"
        )
    ok(f"In project directory: {cwd.name}")

    # ── Step 2: Check git ───────────────────────────────────────────────────
    step(2, 6, "Checking git and GitHub CLI")

    if not shutil.which("git"):
        fail("git not found.\n  Install with: brew install git")
    ok(f"git: {run('git --version').stdout.strip()}")

    if not shutil.which("gh"):
        print(f"\n  {YELLOW}GitHub CLI (gh) not found — installing...{RESET}")
        result = run("brew install gh", capture=False, check=False)
        if result.returncode != 0:
            fail(
                "Could not install gh.\n"
                "  Install manually: brew install gh\n"
                "  Then run: gh auth login"
            )
    ok(f"gh: {run('gh --version').stdout.splitlines()[0]}")

    # ── Step 3: Check GitHub auth ───────────────────────────────────────────
    step(3, 6, "Checking GitHub authentication")

    auth = run("gh auth status", check=False)
    if auth.returncode != 0:
        print(f"\n  {YELLOW}Not logged in — starting interactive login...{RESET}\n")
        login = subprocess.run("gh auth login", shell=True, check=False)
        if login.returncode != 0:
            fail("GitHub login failed. Run 'gh auth login' manually and retry.")

    for line in (run("gh auth status").stdout + run("gh auth status", check=False).stderr).splitlines():
        if line.strip():
            ok(line.strip())

    # ── Step 4: Initialise git repo ─────────────────────────────────────────
    step(4, 6, "Initialising local git repository")

    if not Path(".git").exists():
        run("git init")
        run("git checkout -b main", check=False)
        ok("Initialised new git repo")
    else:
        ok("git repo already initialised")

    run("git checkout -b main 2>/dev/null || git checkout main", check=False)

    name_check = run("git config user.name", check=False)
    if not name_check.stdout.strip():
        run(f'git config user.name "{GITHUB_USER}"')
        run(f'git config user.email "{GITHUB_USER}@users.noreply.github.com"')
        ok("Set git identity")

    run("git add -A")
    status = run("git status --porcelain")
    if status.stdout.strip():
        run('git commit -m "feat: complete AI Log Analyzer with OpenShift CI/CD and learning loop"')
        ok("Created commit")
    else:
        ok("Nothing to commit — already up to date")

    # ── Step 5: Create GitHub repo ──────────────────────────────────────────
    step(5, 6, "Creating GitHub repository")

    existing = run(f"gh repo view {GITHUB_USER}/{REPO_NAME} --json name", check=False)

    if existing.returncode == 0:
        warn(f"Repo {GITHUB_USER}/{REPO_NAME} already exists")
        run("git remote remove origin 2>/dev/null || true", check=False)
        run(f"git remote add origin https://github.com/{GITHUB_USER}/{REPO_NAME}.git")
        ok("Remote origin updated")
    else:
        info(f"Creating https://github.com/{GITHUB_USER}/{REPO_NAME} ...")
        result = run(
            f'gh repo create {GITHUB_USER}/{REPO_NAME} '
            f'--public '
            f'--description "{REPO_DESC}" '
            f'--source=. '
            f'--remote=origin '
            f'--push',
            check=False,
            capture=False,
        )
        if result.returncode != 0:
            warn("gh repo create had issues — trying manual approach...")
            run("git remote remove origin 2>/dev/null || true", check=False)
            run(
                f'gh repo create {GITHUB_USER}/{REPO_NAME} '
                f'--public --description "{REPO_DESC}"',
                check=False, capture=False,
            )
            run(f"git remote add origin https://github.com/{GITHUB_USER}/{REPO_NAME}.git")

    # ── Step 6: Push ────────────────────────────────────────────────────────
    step(6, 6, "Pushing to GitHub")

    push = run("git push -u origin main --force", capture=False, check=False)
    if push.returncode != 0:
        token = run("gh auth token").stdout.strip()
        run(f"git remote set-url origin 'https://{GITHUB_USER}:{token}@github.com/{GITHUB_USER}/{REPO_NAME}.git'")
        run("git push -u origin main --force", capture=False)

    # ── Done ────────────────────────────────────────────────────────────────
    repo_url = f"https://github.com/{GITHUB_USER}/{REPO_NAME}"
    file_count = run("git ls-files | wc -l").stdout.strip()

    print(f"\n{BOLD}{GREEN}{'='*52}")
    print("  Repository pushed successfully!")
    print(f"{'='*52}{RESET}")
    print(f"\n  {BOLD}URL:{RESET}       {repo_url}")
    print(f"  {BOLD}Clone:{RESET}     git clone {repo_url}.git")
    print(f"  {BOLD}Branch:{RESET}    main")
    print(f"  {BOLD}Files:{RESET}     {file_count.strip()} files")
    print()
    print(f"  {BOLD}Next step — set up the self-hosted runner:{RESET}")
    print("  chmod +x setup_runner.sh")
    print("  ./setup_runner.sh")
    print()

    info("Opening repository in browser...")
    os.system(f"open {repo_url}")
    info("Opening runner registration page...")
    os.system(f"open https://github.com/{GITHUB_USER}/{REPO_NAME}/settings/actions/runners/new")


if __name__ == "__main__":
    main()
