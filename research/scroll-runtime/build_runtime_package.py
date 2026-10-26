"""Build package inputs outside a game; copy only owned distributable files.

No module load or engine execution. The compiler setup helper belongs to this
repository's tests; end users receive the built DLL and need no compiler.
"""
import argparse,hashlib,json,shutil,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tests'))
from test_scroll_runtime_native import compiler_environment
from build_independent_dll import build,DISTRIBUTION,SOURCE

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--build-dir',required=True)
    args=parser.parse_args();compiler,environment,msvc=compiler_environment()
    if not msvc:raise RuntimeError('Windows x64 MSVC build required')
    manifest=build(args.build_dir,compiler,environment)
    package=ROOT/'chriz-bg-modpack/scroll-casting';package.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(manifest['artifact'],package/'CBMScroll.dll')
    # The shipped record names files and hashes, never this machine's build folders.
    manifest['artifact']='CBMScroll.dll'
    manifest['dependencies']={Path(name).relative_to(DISTRIBUTION.parent).as_posix():digest for name,digest in manifest['dependencies'].items()}
    for name in ['CBMS_Startup.lua','CBMS_ScrollMarshal.lua','policy_resource.lua']:
        (package/name).write_bytes((SOURCE/name).read_bytes().replace(b"\r\n",b"\n"))
    manifest['source_headers']={p.name:hashlib.sha256(p.read_bytes().replace(b"\r\n",b"\n")).hexdigest() for ext in ['*.h','*.hpp'] for p in sorted(SOURCE.glob(ext))}
    manifest['package']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(package.iterdir()) if p.is_file() and p.suffix in ('.dll','.lua')}
    # LF like the repository copy, so a rebuild leaves the committed record unchanged.
    (package/'native-build.json').write_text(json.dumps(manifest,indent=2)+'\n',newline='\n')
    print(json.dumps({'dll_sha256':manifest['sha256'],'package':str(package)},indent=2))
if __name__=='__main__':main()
