"""Open the fork-to-team comparison; submission remains in the GitHub UI."""
import argparse
import subprocess
import webbrowser
from pathlib import Path
from urllib.parse import quote


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base', default='feature/unity')
    parser.add_argument('--print-url', action='store_true')
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[3]
    branch = subprocess.check_output(['git', '-C', str(repo), 'branch', '--show-current'], text=True).strip()
    if not branch:
        parser.error('Check out a branch before opening a PR.')
    url = ('https://github.com/HealthyMon/healthmon-capstone/compare/'
           f'{quote(args.base, safe="")}...KORemc2:{quote(branch, safe="")}?expand=1')
    print(url)
    if not args.print_url:
        webbrowser.open(url)


if __name__ == '__main__':
    main()
