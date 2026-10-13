"""Effective installed policy CLI; disposable KEY/BIF/override inputs only."""
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import sys
import subprocess

import pytest

from test_scroll_runtime_resources import resource, effect

SOURCE = Path(__file__).resolve().parents[1]/"research/scroll-runtime"
sys.path.insert(0,str(SOURCE))
spec = importlib.util.spec_from_file_location("scroll_policy_cli",SOURCE/"build_installed_policy.py")
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)


def game(tmp_path, resources):
    """Small ordinary variable-resource KEY/BIFF pair, with mixed disk casing."""
    root = tmp_path/"game"
    (root/"DaTa").mkdir(parents=True)
    (root/"OvErRiDe").mkdir()
    entries = list(resources.items())
    types = {"ITM":1005,"SPL":1006,"EFF":1016}
    offset = 20+16*len(entries)
    bif = bytearray(struct.pack("<4s4sIII",b"BIFF",b"V1  ",len(entries),0,20))
    payload = bytearray()
    for i, (name, raw) in enumerate(entries):
        bif.extend(struct.pack("<IIIHH",i,offset+len(payload),len(raw),types[name.rpartition('.')[2]],0))
        payload.extend(raw)
    bif.extend(payload)
    (root/"DaTa"/"TeSt.BiF").write_bytes(bif)
    filename = b"data\\test.bif\0"
    name_offset = 24+12+14*len(entries)
    key = bytearray(struct.pack("<4s4sIIII",b"KEY ",b"V1  ",1,len(entries),24,36))
    key.extend(struct.pack("<IIHH",len(bif),name_offset,len(filename),0))
    for i, (name, _) in enumerate(entries):
        resref, _, ext = name.rpartition('.')
        key.extend(struct.pack("<8sHI",resref.encode().ljust(8,b"\0"),types[ext],i))
    key.extend(filename)
    (root/"ChItIn.KeY").write_bytes(key)
    return root


def hashes(root):
    return {str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file()}


def scroll(*effects):
    return resource("ITM",11,[(3,0,list(effects))])


def test_actual_key_bif_override_precedence_case_all_use_abilities_and_no_game_writes(tmp_path):
    root = game(tmp_path,{
        "S.ITM":scroll(effect(146,b"MISSING")),
        "A.SPL":resource("SPL",1,[(1,1,[])]),
        "BIFONLY.ITM":scroll(effect(146,b"A")),
        "NOTSCROL.ITM":resource("ITM",7,[(3,0,[effect(146,b"MISSING")])]),
    })
    replacement = resource("ITM",11,[(1,0,[effect(146,b"MISSING")]),
                                    (3,0,[effect(146,b"A")]),(3,0,[effect(147,b"A")])],effects_first=True)
    (root/"OvErRiDe"/"s.ItM").write_bytes(replacement)
    (root/"OvErRiDe"/"a.sPl").write_bytes(resource("SPL",2,[(1,7,[]),(1,17,[])],effects_first=True))
    (root/"OvErRiDe"/"Extra.iTm").write_bytes(scroll(effect(12)))
    # Not valid engine resrefs; do not accidentally enumerate them as ITMs.
    (root/"OvErRiDe"/"not-a-resref.itm").write_bytes(b"backup")
    before = hashes(root)
    output = tmp_path/"artifacts"
    assert cli.main(["--game-root",str(root),"--output-dir",str(output)]) == 0
    assert hashes(root) == before
    assert {p.name for p in output.iterdir()} == {cli.TABLE_NAME,cli.REPORT_NAME}
    raw = (output/cli.TABLE_NAME).read_bytes()
    report = json.loads((output/cli.REPORT_NAME).read_text())
    assert raw[:8] == b"CBMSPOL1"
    assert struct.unpack_from("<II",raw,8) == (4,4)
    assert report["table_sha256"] == hashlib.sha256(raw).hexdigest()
    assert report["inventory"] == {"items":4,"category11_items":3,"classification_counts":{
        "typed_cast_candidate":2,"learning":1,"native_only":1},"root_errors":0,
        "unresolved_abilities":0,"complete":True,"requires_review":False}
    by_key = {(a["item"],a["ability"]):a for a in report["abilities"]}
    assert list(by_key) == [("BIFONLY",0),("EXTRA",0),("S",1),("S",2)]
    assert by_key["S",1]["spells"]["A"] == {"installed_type":2,"policy":"divine","ability_levels":[7,17]}
    assert by_key["S",1]["resources"]["S.ITM"] == hashlib.sha256(replacement).hexdigest()
    assert report["sources"]["S.ITM"]["kind"] == "override"
    assert report["sources"]["BIFONLY.ITM"]["kind"] == "bif"


def test_fixed_mixed_unresolved_and_malformed_reports_are_not_enabled_or_fabricated(tmp_path):
    root = game(tmp_path,{
        "SCRL03.ITM":scroll(effect(27)),
        "MIX.ITM":scroll(effect(147,b"A"),effect(146,b"A")),
        "MISS.ITM":scroll(effect(146,b"ABSENT")),
        "S.ITM":scroll(effect(146,b"A")),
        "A.SPL":resource("SPL",1,[(1,1,[])]),
    })
    # Bad override must not quietly fall back to the otherwise usable KEY item.
    (root/"OvErRiDe"/"s.itm").write_bytes(b"bad override")
    before = hashes(root)
    output = tmp_path/"out"
    assert cli.main(["--game-root",str(root),"--output-dir",str(output)]) == 2
    report = json.loads((output/cli.REPORT_NAME).read_text())
    assert hashes(root) == before
    assert report["inventory"]["complete"] is False
    assert report["inventory"]["root_errors"] == 1
    assert report["inventory"]["unresolved_abilities"] == 2
    assert report["inventory_errors"][0]["resource"] == "S.ITM"
    assert "truncated" in report["inventory_errors"][0]["diagnostic"]
    by_item = {a["item"]:a for a in report["abilities"]}
    assert set(by_item) == {"SCRL03","MIX","MISS"}
    assert by_item["SCRL03"]["classification"] == "native_exception"
    assert by_item["MIX"]["classification"] == "mixed_learning_cast"
    assert by_item["MISS"]["classification"] == "unresolved"
    assert "ABSENT.SPL" in by_item["MISS"]["diagnostics"][0]


@pytest.mark.parametrize("kind",["bad_key","missing_key","missing_bif","truncated_bif"])
def test_malformed_or_missing_indexed_input_has_clear_outcome(tmp_path,capsys,kind):
    root = game(tmp_path,{"S.ITM":scroll(effect(12))})
    if kind == "bad_key": (root/"ChItIn.KeY").write_bytes(b"KEY ")
    elif kind == "missing_key": (root/"ChItIn.KeY").unlink()
    elif kind == "missing_bif": (root/"DaTa"/"TeSt.BiF").unlink()
    else: (root/"DaTa"/"TeSt.BiF").write_bytes(b"BIFF")
    before = hashes(root)
    output = tmp_path/"out"
    status = cli.main(["--game-root",str(root),"--output-dir",str(output)])
    assert hashes(root) == before
    if kind.endswith("key"):
        assert status == 1 and "KEY" in capsys.readouterr().err.upper()
        assert not output.exists()
    else:
        assert status == 2
        report = json.loads((output/cli.REPORT_NAME).read_text())
        assert report["entries"] == 0
        assert report["inventory_errors"][0]["resource"] == "S.ITM"
        assert "BIF" in report["inventory_errors"][0]["diagnostic"].upper()


@pytest.mark.parametrize("where",["root","override","new_child"])
def test_output_must_be_explicitly_outside_game_before_any_write(tmp_path,where):
    root = game(tmp_path,{"S.ITM":scroll(effect(12))})
    output = {"root":root,"override":root/"OvErRiDe","new_child":root/"new"/"out"}[where]
    before = hashes(root)
    assert cli.main(["--game-root",str(root),"--output-dir",str(output)]) == 1
    assert hashes(root) == before
    assert not (root/"new").exists()


def test_output_alias_into_game_is_rejected(tmp_path):
    root = game(tmp_path,{"S.ITM":scroll(effect(12))})
    alias = tmp_path/"outside_alias"
    try:
        alias.symlink_to(root,target_is_directory=True)
    except OSError as error:
        pytest.skip(f"test host cannot create directory symlink: {error}")
    before = hashes(root)
    assert cli.main(["--game-root",str(root),"--output-dir",str(alias/"out")]) == 1
    assert hashes(root) == before


@pytest.mark.parametrize("existing",[cli.TABLE_NAME,cli.REPORT_NAME])
def test_no_overwrite_or_partial_pair_when_output_already_exists(tmp_path,existing):
    root = game(tmp_path,{"S.ITM":scroll(effect(12))})
    out = tmp_path/"out"
    out.mkdir()
    (out/existing).write_bytes(b"existing evidence")
    before = hashes(root)
    assert cli.main(["--game-root",str(root),"--output-dir",str(out)]) == 1
    assert hashes(root) == before
    assert list(out.iterdir()) == [out/existing]
    assert (out/existing).read_bytes() == b"existing evidence"


def test_repeated_inventory_is_deterministic_and_contains_only_effective_dependencies(tmp_path):
    root = game(tmp_path,{"S.ITM":scroll(effect(146,b"A")),"A.SPL":resource("SPL",1,[(1,1,[])])})
    one,two = tmp_path/"one",tmp_path/"two"
    cli.write_inventory(root,one)
    cli.write_inventory(root,two)
    assert hashes(one) == hashes(two)


def test_bad_dependency_override_preserves_unresolved_instead_of_using_bif(tmp_path):
    root = game(tmp_path,{"S.ITM":scroll(effect(146,b"A")),"A.SPL":resource("SPL",1,[(1,1,[])])})
    (root/"OvErRiDe"/"a.spl").write_bytes(b"bad spell")
    out = tmp_path/"out"
    report = cli.write_inventory(root,out)
    assert report["inventory"]["complete"] is True
    assert report["inventory"]["requires_review"] is True
    assert report["abilities"][0]["classification"] == "unresolved"
    assert "outside resource" in report["abilities"][0]["diagnostics"][0]
    assert report["dependencies"] == 1


def test_installer_staging_rebuilds_only_owned_outputs_and_preserves_game(tmp_path):
    root=game(tmp_path,{"S.ITM":scroll(effect(146,b"A")),"A.SPL":resource("SPL",1,[(1,1,[])])})
    out=root/cli.INSTALLER_STAGE
    before=hashes(root)
    args=["--game-root",str(root),"--output-dir",str(out),"--installer-staging"]
    assert cli.main(args)==0
    (out/"unrelated.txt").write_bytes(b"keep me")
    (out/cli.TABLE_NAME).write_bytes(b"previous generated table")
    assert cli.main(args)==0
    assert (out/cli.TABLE_NAME).read_bytes()[:8]==b"CBMSPOL1"
    assert (out/"unrelated.txt").read_bytes()==b"keep me"
    assert not list(out.glob("*.tmp"))
    assert all((root/name).read_bytes() and hashes(root)[name]==digest for name,digest in before.items())


@pytest.mark.parametrize('where',['override','other_work','outside'])
def test_installer_mode_does_not_allow_arbitrary_output_paths(tmp_path,where):
    root=game(tmp_path,{"S.ITM":scroll(effect(12))})
    out={'override':root/'OvErRiDe','other_work':root/'weidu_external/other',
         'outside':tmp_path/'outside'}[where]
    before=hashes(root)
    assert cli.main(["--game-root",str(root),"--output-dir",str(out),"--installer-staging"])==1
    assert hashes(root)==before


def test_installer_mode_refuses_missing_root_and_keeps_previous_stage(tmp_path):
    root=game(tmp_path,{"S.ITM":scroll(effect(12))})
    out=root/cli.INSTALLER_STAGE;out.mkdir(parents=True)
    (out/cli.TABLE_NAME).write_bytes(b"previous table")
    (root/'OvErRiDe'/'s.itm').write_bytes(b"invalid root")
    before=hashes(root)
    assert cli.main(["--game-root",str(root),"--output-dir",str(out),"--installer-staging"])==1
    assert hashes(root)==before


@pytest.mark.skipif(sys.platform!='win32',reason='packaged installer helper targets Windows')
def test_packaged_builder_works_without_python_or_external_reader_argument(tmp_path):
    executable=SOURCE.parents[1]/'chriz-bg-modpack/scroll-casting/tools/CBMSPolicy.exe'
    assert executable.is_file(),'build the shipped helper before package validation'
    root=game(tmp_path,{"S.ITM":scroll(effect(146,b"A")),"A.SPL":resource("SPL",1,[(1,1,[])])})
    before=hashes(root);out=root/cli.INSTALLER_STAGE
    result=subprocess.run([str(executable),'--game-root',str(root),'--output-dir',str(out),
                           '--installer-staging'],capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stdout+result.stderr
    ordinary=tmp_path/'expected';cli.write_inventory(root,ordinary)
    assert (out/cli.TABLE_NAME).read_bytes()==(ordinary/cli.TABLE_NAME).read_bytes()
    assert all(hashes(root)[name]==digest for name,digest in before.items())
