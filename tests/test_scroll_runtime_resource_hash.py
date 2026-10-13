"""Full-buffer CNG SHA256 and the real-resource adapter protocol, offline only."""
import ctypes
import hashlib
from pathlib import Path
import subprocess

import pytest
from lupa.lua51 import LuaRuntime as Lua51
from lupa.luajit21 import LuaRuntime as LuaJIT
from test_scroll_runtime_native import compiler_environment
from test_scroll_runtime_resources import effect, resource, eff

SOURCE = Path(__file__).resolve().parents[1] / "research/scroll-runtime"


@pytest.fixture(scope="session")
def hash_api(tmp_path_factory):
    root = tmp_path_factory.mktemp("scroll-resource-sha")
    compiler, env, msvc = compiler_environment()
    assert msvc, "Native resource hashing currently targets the Windows EEex host"
    output = root / "resource_hash.dll"
    result = subprocess.run([compiler, "/nologo", "/std:c++20", "/EHsc", "/W4", "/WX", "/permissive-", "/LD",
                             str(SOURCE / "policy_resource_hash.cpp"), f"/Fe{output}"],
                            cwd=root, env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    api = ctypes.CDLL(str(output))
    api.CBMS_PolicyHashBytes.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p]
    api.CBMS_PolicyHashBytes.restype = ctypes.c_int
    return api


def digest(api, data):
    source = ctypes.create_string_buffer(data)
    result = ctypes.create_string_buffer(65)
    assert api.CBMS_PolicyHashBytes(source, len(data), result) == 1
    return result.value.decode()


@pytest.mark.parametrize("data", [b"", b"abc", b"a\0b\0\xff", bytes(range(256)) * 4097,
    resource("ITM", 11, [(3, 0, [effect(146, b"HELP")]), (3, 0, [effect(147, b"HELP")])], effects_first=True),
    resource("SPL", 4, [(1, 1, [effect(148, b"ACTUAL")]), (1, 30, [effect(12)])], globals=[effect(141)]),
    eff(177, b"LINK") + b"\0tail data preserved\xff"],
    ids=["empty", "abc", "embedded-nul", "multiple-blocks", "reordered-itm", "multi-ability-spl", "eff-tail"])
def test_real_cng_hash_covers_complete_resource(hash_api, data):
    assert digest(hash_api, data) == hashlib.sha256(data).hexdigest()


def test_native_hash_invalid_arguments_do_not_publish_partial_digest(hash_api):
    output = ctypes.create_string_buffer(b"stale hash", 65)
    assert hash_api.CBMS_PolicyHashBytes(None, 5, output) == 0
    assert output.value == b""
    assert hash_api.CBMS_PolicyHashBytes(None, 0, None) == 0


@pytest.mark.parametrize("runtime", [Lua51, LuaJIT], ids=["Lua51", "LuaJIT"])
@pytest.mark.parametrize("extension", ["ITM", "SPL", "EFF"])
def test_adapter_demands_raw_effective_buffer_and_native_full_size(hash_api, runtime, extension):
    lua = runtime(unpack_returned_tuples=True)
    module = lua.execute((SOURCE / "policy_resource.lua").read_text())
    raw = b"EFF V2.0" + b"\0" * 264 + b"untouched tail" if extension == "EFF" else b"full\0installed bytes\xff"
    expected = hashlib.sha256(raw).hexdigest()
    def native_hash(token, length):
        assert token == "raw-demanded-buffer" and length == len(raw)
        return digest(hash_api, raw)
    lua.globals().NativeHash = native_hash
    lua.globals().ExpectedLength = len(raw)
    lua.globals().Extension = extension
    lua.execute('''
      local resource={nSize=ExpectedLength,Demand=function(self)return "raw-demanded-buffer"end}
      EEex_Resource_Fetch=function(name,extension)
       assert(name=="SCROLL" and extension==Extension);return resource
      end
      EEex_Resource_Demand=function()error("EFF-adjusted helper must not be used")end
      CBMS_NativeResourceSHA256=function(data,size)return NativeHash(data,size)end
    ''')
    assert module.Digest("SCROLL", extension) == expected


@pytest.mark.parametrize("runtime", [Lua51, LuaJIT], ids=["Lua51", "LuaJIT"])
def test_adapter_missing_failed_or_changed_resource_is_not_cached(runtime):
    lua = runtime(unpack_returned_tuples=True)
    lua.globals().Module = lua.execute((SOURCE / "policy_resource.lua").read_text())
    lua.execute('''
      local present=false;local loaded=false;local version=string.rep("a",64);local reads=0
      local resource={nSize=272,Demand=function()if loaded then return "buffer"end end}
      EEex_Resource_Fetch=function()reads=reads+1;if present then return resource end end
      CBMS_NativeResourceSHA256=function(data,size)assert(data=="buffer"and size==272);return version end
      assert(Module.Digest("LINK","EFF")==nil)
      present=true;assert(Module.Digest("LINK","EFF")==nil)
      loaded=true;assert(Module.Digest("LINK","EFF")==string.rep("a",64))
      version=string.rep("b",64);assert(Module.Digest("LINK","EFF")==version)
      assert(reads==4)
      resource.nSize=0;assert(not pcall(Module.Digest,"LINK","EFF"))
      resource.nSize=272;version="not-a-digest";assert(not pcall(Module.Digest,"LINK","EFF"))
      assert(not pcall(Module.Digest,"LINK","EXE"))
    ''')


@pytest.mark.parametrize("runtime", [Lua51, LuaJIT], ids=["Lua51", "LuaJIT"])
def test_signed_provider_size_is_normalized_without_shortening(runtime):
    lua = runtime(unpack_returned_tuples=True)
    lua.globals().Module = lua.execute((SOURCE / "policy_resource.lua").read_text())
    # Protocol only: never allocates or hashes a >2GB fixture.
    lua.execute('''
      EEex_Resource_Fetch=function()return {nSize=-1,Demand=function()return "buffer"end}end
      CBMS_NativeResourceSHA256=function(data,size)assert(size==4294967295);return string.rep("a",64)end
      assert(Module.Digest("LINK","EFF")==string.rep("a",64))
    ''')
