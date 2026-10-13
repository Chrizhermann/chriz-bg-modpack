"""Build the Windows scroll inventory helper; never installs into a game.

Run with a build-only Python environment containing PyInstaller 6.22.3.
The released helper includes Python; players do not need a Python installation.
"""
from pathlib import Path
import argparse
import hashlib
import importlib.metadata
import json
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'research/scroll-runtime'
VERSION='6.22.3'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work-dir',type=Path,required=True)
    args=parser.parse_args()
    if sys.platform!='win32':
        parser.error('build with Windows Python for the Windows installer')
    if importlib.metadata.version('pyinstaller')!=VERSION:
        parser.error(f'build requires pinned PyInstaller {VERSION}')
    work=args.work_dir.resolve();work.mkdir(parents=True,exist_ok=True)
    subprocess.run([sys.executable,'-m','PyInstaller','--noconfirm','--clean',
                    '--onefile','--console','--noupx','--name','CBMSPolicy',
                    '--distpath',str(work/'dist'),'--workpath',str(work/'build'),
                    '--specpath',str(work),'--paths',str(SOURCE),
                    str(SOURCE/'build_installed_policy.py')],check=True,cwd=work)
    output=ROOT/'chriz-bg-modpack/scroll-casting/tools'
    output.mkdir(parents=True,exist_ok=True)
    exe=output/'CBMSPolicy.exe'
    shutil.copyfile(work/'dist/CBMSPolicy.exe',exe)
    manifest={'pyinstaller':VERSION,'python':sys.version,'sha256':hashlib.sha256(exe.read_bytes()).hexdigest(),
              'sourceTextNormalization':'LF',
              'sources':{name:hashlib.sha256((SOURCE/name).read_text(encoding='utf-8').encode('utf-8')).hexdigest() for name in
                         ['build_installed_policy.py','installed_resources.py','policy_table.py','extract_key_resource.py']}}
    (output/'CBMSPolicy-build.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    # Required runtime/license notices accompany the self-contained executable.
    dist=importlib.metadata.distribution('pyinstaller')
    license_path=Path(dist.locate_file('pyinstaller-'+VERSION+'.dist-info/licenses/COPYING.txt'))
    if not license_path.is_file():
        license_path=next(Path(dist._path).rglob('COPYING.txt'))
    shutil.copyfile(license_path,output/'PyInstaller-COPYING.txt')
    python_license=Path(sys.base_prefix)/'LICENSE.txt'
    if not python_license.is_file():
        raise FileNotFoundError(f'Python license missing: {python_license}')
    shutil.copyfile(python_license,output/'Python-LICENSE.txt')
    print(f'Built {exe} ({exe.stat().st_size} bytes), SHA-256 {manifest["sha256"]}')


if __name__=='__main__':
    main()
