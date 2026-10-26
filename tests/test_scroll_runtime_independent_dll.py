"""Link the real independent binding DLL, inspect it, never LoadLibrary it."""
import importlib.util
import pefile

from test_scroll_runtime_native import SOURCE,compiler_environment


def build_module():
    spec=importlib.util.spec_from_file_location("build_scroll_dll",SOURCE/"build_independent_dll.py")
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def test_independent_binding_dll_links_both_provider_families(tmp_path):
    module=build_module()
    compiler,environment,msvc=compiler_environment();assert msvc
    result=module.build(tmp_path,compiler,environment)
    pe=pefile.PE(result["artifact"])
    exports={entry.name.decode() for entry in pe.DIRECTORY_ENTRY_EXPORT.symbols if entry.name}
    assert {"InitBindings","OpenBindings","CBMS_UnmarshalCarrier","CBMS_DecodeCarrier","CBMS_BindDecodeModules","CBMS_InstallDecodeHooks","CBMS_RemoveDecodeHooks","CBMS_InstallPersistenceHooks","CBMS_MarshalCarrier"}<=exports
    assert "CBMS_EEexAttachForTest" not in exports
    assert "CBMS_TestInstallDecodeHooks" not in exports
    assert "CBMS_TestInstallEffectPersistenceHooks" not in exports
    assert {"CBMS_InstallEffectPersistenceHooks","CBMS_EffectCopyCarrier","CBMS_EffectDestroyCarrier","CBMS_ActorDestroyCarrier"}<=exports
    assert {"InfinityLoaderCommon.dll","LuaBindingsCore.dll","LuaProvider.dll"}<=set(result["imports"])
    assert "EEex.dll" not in result["imports"] # no forked EEex owner or private symbols
    assert pe.FILE_HEADER.Machine==0x8664 and pe.OPTIONAL_HEADER.Magic==0x20B
    assert result["status"].startswith("installed by component 430;")
    assert "docs/scroll-casting.md" in result["status"]


def test_independent_binding_dll_rebuilds_byte_for_byte(tmp_path):
    # /Brepro stamps content hashes instead of link times, so the shipped DLL
    # is reproducible from its recorded sources in any build folder. The sources
    # themselves must stay where they are: MSVC derives anonymous-namespace
    # names from their path.
    module=build_module()
    compiler,environment,msvc=compiler_environment();assert msvc
    first=module.build(tmp_path/"first",compiler,environment)
    second=module.build(tmp_path/"second-folder",compiler,environment)
    assert first["sha256"]==second["sha256"]
    assert (tmp_path/"first"/"CBMScroll.dll").read_bytes()==(tmp_path/"second-folder"/"CBMScroll.dll").read_bytes()
