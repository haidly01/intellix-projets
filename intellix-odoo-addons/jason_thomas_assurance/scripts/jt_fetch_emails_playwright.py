#!/usr/bin/env python3
"""Ré-extraction AGO avec emails via profil Playwright (session Assure&Go requise)."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import requests
from playwright.sync_api import sync_playwright

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
IA_ROOT = REPO_ROOT.parent / 'iaexcellence_extract'
sys.path.insert(0, str(IA_ROOT))

from ago_core import run_extraction, session_logged_in  # noqa: E402


def session_from_profile(profile: Path) -> requests.Session:
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(user_data_dir=str(profile), headless=True)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto('https://ago.iaexcellence.com/', timeout=90000)
        page.wait_for_timeout(8000)
        s = requests.Session()
        s.headers['User-Agent'] = (
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/120.0.0.0'
        )
        for c in ctx.cookies():
            s.cookies.set(c['name'], c['value'], domain=c.get('domain'), path=c.get('path', '/'))
        ctx.close()
    return s


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--profile', default=str(REPO_ROOT / '.browser_profile' / 'account_2'))
    parser.add_argument('--out', default=str(IA_ROOT / 'output'))
    args = parser.parse_args()

    profile = Path(args.profile)
    out = Path(args.out)
    if not profile.exists():
        print(f'Profil introuvable: {profile}', file=sys.stderr)
        return 1

    s = session_from_profile(profile)
    if not session_logged_in(s):
        print(
            'Session AGO invalide. Connectez-vous à https://ago.iaexcellence.com '
            f'dans le profil {profile} puis relancez.',
            file=sys.stderr,
        )
        return 2

    log = out / 'playwright_ago_email_extract.log'
    stats = run_extraction(s, out, log, with_activities=False)
    print('OK', stats)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
