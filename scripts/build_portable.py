"""Build a PyInstaller folder; run with the target platform's Python."""
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    subprocess.run([
        sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--onedir',
        '--name', 'CurvePress', '--paths', str(ROOT),
        '--collect-all', 'curvepress', '--collect-all', 'OCP', '--collect-all', 'vtkmodules',
        str(ROOT / 'launcher' / 'desktop.py'),
    ], cwd=ROOT, check=True)
    folder = ROOT / 'dist' / 'CurvePress'
    for name in ('LICENSE', 'README.md'):
        shutil.copy2(ROOT / name, folder / name)
    shutil.copytree(ROOT / 'docs', folder / 'docs', dirs_exist_ok=True)
    executable = folder / ('CurvePress.exe' if sys.platform == 'win32' else 'CurvePress')
    subprocess.run([str(executable), '--self-test'], check=True, timeout=180)
    shutil.make_archive(str(ROOT / 'dist' / 'CurvePress-Studio-Windows'), 'zip', ROOT / 'dist', 'CurvePress')


if __name__ == '__main__':
    main()
