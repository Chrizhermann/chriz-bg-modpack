"""Build an uninstalled scroll binding DLL against pinned shipped loader DLLs.

Creates import libraries from actual exported symbols, then links our sources.
Never builds the upstream projects (which contain COPY_TO_GAME post-builds),
loads a DLL, writes a game directory, or installs engine hooks.
"""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

import pefile

SOURCE = Path(__file__).resolve().parent
LOADER = Path("C:/tmp/scroll-hook-research-20261009/InfinityLoader")
DISTRIBUTION = Path("C:/tmp/scroll-hook-research-20261009/EEex/EEex/loader")


def run(argv, build, environment):
    result = subprocess.run(argv,cwd=build,env=environment,text=True,capture_output=True)
    if result.returncode:
        raise RuntimeError(result.stdout+result.stderr)
    return result.stdout


def build(directory, compiler, environment):
    directory = Path(directory).resolve()
    if directory == SOURCE or SOURCE in directory.parents:
        raise ValueError("build output must stay outside repository source")
    directory.mkdir(parents=True,exist_ok=True)
    librarian = shutil.which("lib.exe",path=environment.get("Path",environment.get("PATH","")))
    if not librarian:
        raise RuntimeError("MSVC x64 librarian required")
    dependencies = [DISTRIBUTION/"InfinityLoaderCommon.dll",DISTRIBUTION/"LuaBindingsCore.dll",DISTRIBUTION/"Lua52/LuaProvider.dll"]
    libraries = []
    for dll in dependencies:
        pe = pefile.PE(str(dll))
        names = sorted(symbol.name.decode("ascii") for symbol in pe.DIRECTORY_ENTRY_EXPORT.symbols if symbol.name)
        definition = directory/(dll.stem+".def")
        if any(any(character.isspace() for character in name) or '"' in name for name in names):
            raise ValueError("unsupported exported-symbol spelling in import definition")
        definition.write_text('LIBRARY '+dll.name+'\nEXPORTS\n'+''.join('  '+name+'\n' for name in names))
        library = directory/(dll.stem+".lib")
        run([librarian,"/nologo","/machine:x64","/def:"+str(definition),"/out:"+str(library)],directory,environment)
        libraries.append(library)
    output = directory/"CBMScroll.dll"
    units = ["native_api.cpp","eeex_save_bridge.cpp","decode_carrier_api.cpp","decode_hook_host.cpp","marshal_carrier_api.cpp","lifecycle_carrier_api.cpp","item_carrier_api.cpp","item_hook_host.cpp","dispatch_carrier_api.cpp","dispatch_hook_host.cpp","cast_carrier_api.cpp","cast_hook_host.cpp","action_carrier_api.cpp","action_hook_host.cpp","linked177_api.cpp","linked177_host.cpp","policy_resource_hash.cpp","policy_resource_lua.cpp","eeex_lua_bindings.cpp","startup.cpp","startup_lua.cpp","dll_entry.cpp"]
    args = [compiler,"/nologo","/std:c++20","/EHsc","/W4","/WX","/permissive-","/LD"]
    units += ["conditional_api.cpp","conditional_host.cpp"]
    args += [str(SOURCE/name) for name in units]
    args += ["/I"+str(LOADER/part) for part in ["InfinityLoaderCommon/headers/common","LuaBindingsCore/headers/common"]]
    args += ["/Fe"+str(output),"/link"]+[str(path) for path in libraries]
    run(args,directory,environment)
    pe = pefile.PE(str(output))
    imported = {entry.dll.decode():[symbol.name.decode() for symbol in entry.imports if symbol.name] for entry in pe.DIRECTORY_ENTRY_IMPORT}
    # The DLL import name is intentionally LuaProvider.dll, so both supported
    # loader families must supply every actually used imported function.
    required = set(imported.get("LuaProvider.dll",[]))
    for family in ("Lua52","LuaJIT"):
        provider=pefile.PE(str(DISTRIBUTION/family/"LuaProvider.dll"))
        exports={symbol.name.decode() for symbol in provider.DIRECTORY_ENTRY_EXPORT.symbols if symbol.name}
        if not required<=exports:
            raise RuntimeError(family+" is missing imported scroll binding APIs: "+str(required-exports))
    manifest = dict(artifact=str(output),sha256=hashlib.sha256(output.read_bytes()).hexdigest(),
        status="uninstalled trial candidate; native game acceptance not performed",imports=imported,
        text_hash_normalization="LF",
        sources={name:hashlib.sha256((SOURCE/name).read_bytes().replace(b"\r\n",b"\n")).hexdigest() for name in units},
        dependencies={str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in dependencies})
    (directory/"CBMScroll-build.json").write_text(json.dumps(manifest,indent=2)+"\n")
    return manifest
