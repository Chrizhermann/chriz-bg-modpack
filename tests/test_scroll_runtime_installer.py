"""Component430 through real WeiDU and the shipped policy EXE, synthetic input only."""
import hashlib
import json
from pathlib import Path, PureWindowsPath

import pytest

from tests.test_recruitment_xp import install, tree
from tests.test_utility_xp_installer import SyntheticGame, WEIDU
from test_scroll_runtime_resources import resource, effect

pytestmark = pytest.mark.skipif(WEIDU is None, reason='WeiDU unavailable')
ROOT=Path(__file__).resolve().parents[1]
PACKAGE=ROOT/'chriz-bg-modpack/scroll-casting'


def test_native_package_matches_current_sources_and_distributable_files():
    manifest=json.loads((PACKAGE/'native-build.json').read_text())
    assert manifest['text_hash_normalization']=='LF'
    source=ROOT/'research/scroll-runtime'
    for group in ('sources','source_headers'):
        for name,expected in manifest[group].items():
            data=(source/name).read_bytes().replace(b'\r\n',b'\n')
            assert hashlib.sha256(data).hexdigest()==expected,name
    for name,expected in manifest['package'].items():
        assert hashlib.sha256((PACKAGE/name).read_bytes()).hexdigest()==expected,name
    assert manifest['sha256']==manifest['package']['CBMScroll.dll']
    # The record says where this DLL's in-game checks are; the guide must name it.
    assert manifest['status'].startswith('installed by component 430;')
    assert manifest['sha256'] in (ROOT/'docs/scroll-casting.md').read_text(encoding='utf-8')


def test_native_package_record_names_no_build_machine_folders():
    manifest=json.loads((PACKAGE/'native-build.json').read_text())
    assert manifest['artifact']=='CBMScroll.dll'
    assert sorted(manifest['dependencies'])==['loader/InfinityLoaderCommon.dll','loader/Lua52/LuaProvider.dll','loader/LuaBindingsCore.dll']
    def strings(value):
        if isinstance(value,dict):
            for key,item in value.items():yield key;yield from strings(item)
        elif isinstance(value,list):
            for item in value:yield from strings(item)
        elif isinstance(value,str):yield value
    for text in strings(manifest):
        assert not PureWindowsPath(text).anchor and not text.startswith('/'),text


def fixture(tmp_path, *, kind='bg2ee', review=False):
    game=SyntheticGame(tmp_path/'game',game=kind)
    (game.root/'EEex.dll').write_bytes(b'synthetic capability marker, never loaded')
    scripts=game.root/'EEex_scripts';scripts.mkdir()
    (scripts/'EEex_Modules.lua').write_bytes(b'-- another owner\r\nExistingModule = true\r\n')
    effects=[effect(146,b'A',0,15)]
    if review:effects.append(effect(147,b'A'))
    (game.override/'scroll.itm').write_bytes(resource('ITM',11,[(3,0,effects),(3,0,[effect(147,b'A')])],effects_first=True))
    (game.override/'a.spl').write_bytes(resource('SPL',2,[(1,1,[]),(1,7,[])]))
    return game


@pytest.mark.parametrize('kind,review,existing',[('bg2ee',False,False),('eet',True,True)])
def test_public_installer_real_builder_no_resource_mutation_exact_uninstall(tmp_path,kind,review,existing):
    assert (PACKAGE/'CBMScroll.dll').is_file() and (PACKAGE/'tools/CBMSPolicy.exe').is_file()
    game=fixture(tmp_path,kind=kind,review=review)
    if existing:
        (game.root/'CBMScroll').mkdir()
        (game.root/'CBMScroll.dll').write_bytes(b'prior DLL, never loaded')
        (game.root/'CBMScroll/CBMSPOL1.bin').write_bytes(b'prior table')
    before=tree(game)
    result,transcript=install(game,430)
    assert result.returncode==0,transcript
    assert (game.root/'CBMScroll.dll').read_bytes()==(PACKAGE/'CBMScroll.dll').read_bytes()
    for name in ['CBMS_Startup.lua','CBMS_ScrollMarshal.lua','policy_resource.lua']:
        assert (game.root/'CBMScroll'/name).read_bytes()==(PACKAGE/name).read_bytes()
    report=json.loads((game.root/'CBMScroll/CBMSPOL1.json').read_text())
    assert report['inventory']['root_errors']==0
    assert report['inventory']['requires_review']==review
    policy={r['ability']:r for r in report['abilities'] if r['item']=='SCROLL'}
    assert policy[0]['classification']==('mixed_learning_cast' if review else 'typed_cast_candidate')
    assert policy[1]['classification']=='learning'
    modules=(game.root/'EEex_scripts/EEex_Modules.lua').read_bytes()
    assert b'ExistingModule = true' in modules
    assert modules.count(b'dofile("CBMScroll/CBMS_Startup.lua")')==1
    after=tree(game)
    assert {n:v for n,v in after.items() if n.startswith('OVERRIDE/')}=={n:v for n,v in before.items() if n.startswith('OVERRIDE/')}
    result,transcript=install(game,430,uninstall=True)
    assert result.returncode==0,transcript
    assert tree(game)==before


@pytest.mark.parametrize('failure',['missing_eeex','missing_builder','bad_root','unsupported_game'])
def test_public_installer_failure_has_no_public_runtime_or_resource_writes(tmp_path,failure):
    game=fixture(tmp_path,kind='bgee' if failure=='unsupported_game' else 'bg2ee')
    if failure=='missing_eeex':(game.root/'EEex.dll').unlink()
    elif failure=='missing_builder':(game.root/'chriz-bg-modpack/scroll-casting/tools/CBMSPolicy.exe').unlink()
    elif failure=='bad_root':(game.override/'scroll.itm').write_bytes(b'bad')
    before=tree(game)
    result,transcript=install(game,430)
    if failure=='unsupported_game':
        assert 'SKIPPING:' in transcript and 'not supported' in transcript
    else:
        assert result.returncode!=0,transcript
    assert not (game.root/'CBMScroll.dll').exists()
    assert tree(game)==before
