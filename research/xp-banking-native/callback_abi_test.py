"""Private adapter isolation checks; actual ABI execution is bridge_source_probe.

These tests intentionally do not claim that source-string assertions establish
native argument placement. The independent probe compiles and executes it.
"""
from importlib import import_module
from pathlib import Path

import pytest

ROOT=Path(__file__).resolve().parent


@pytest.fixture(params=["lua51","lua52","luajit21"])
def lua(request):
    runtime=import_module("lupa."+request.param).LuaRuntime(unpack_returned_tuples=True)
    runtime.globals().adapter=runtime.execute((ROOT/"callback_abi.lua").read_text())
    return runtime


@pytest.mark.parametrize("correct",[False,True])
def test_private_generated_copy_preserves_upstream_and_existing_correct_layout(lua,correct):
    lua.globals().correct=correct
    lua.execute("""
        local k,ctx=correct and 40 or 8,correct and 32 or 0
        local assembly={'#MAKE_SHADOW_SPACE(64)',{'mov rbx,rcx'},
            '#ALIGN\\nmov qword ptr ss:[rsp+'..k..'],0\\n'..
            'mov qword ptr ss:[rsp+'..ctx..'],0\\ncall #L(Hardcoded_lua_pcallk)\\n#ALIGN_END'}
        local before=assembly[3];local observed
        EEex_GenLuaCall=function(name,meta) observed=meta;assert(name=='PrivateCallback');return assembly end
        local global=EEex_GenLuaCall;local meta={returnType=1,args={}}
        local fixed=adapter.GenLuaCall('PrivateCallback',meta)
        assert(EEex_GenLuaCall==global and observed==meta)
        assert(fixed~=assembly and fixed[2]~=assembly[2] and assembly[3]==before)
        assert(fixed[3]:find('mov qword ptr ss:[rsp+32], 0 #ENDL '..
            'mov qword ptr ss:[rsp+40], 0 #ENDL call #L(Hardcoded_lua_pcallk)',1,true))
        fixed[2][1]='changed';assert(assembly[2][1]=='mov rbx,rcx')
    """)


def test_comments_cannot_create_a_protected_call_and_unknown_generator_refuses(lua):
    lua.execute("""
        local comment='; call #L(Hardcoded_lua_pcallk)'
        EEex_GenLuaCall=function()return {comment}end
        local ok,why=pcall(adapter.GenLuaCall,'PrivateCallback',{})
        assert(not ok and tostring(why):find('ABI must be reviewed'))
        EEex_GenLuaCall=function()return {comment..'\\ncall #L(Hardcoded_lua_pcallk)'}end
        local fixed=adapter.GenLuaCall('PrivateCallback',{})
        assert(fixed[1]:sub(1,#comment)==comment)
    """)
