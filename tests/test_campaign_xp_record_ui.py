"""Record presentation with real EEex menu helpers and synthetic UI objects.

No game/display engine is launched. These tests establish callback behavior,
not visual acceptance or support for alternative UI mods.
"""
from importlib import import_module
import os
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
EEEX = Path(os.environ.get("CBM_EEEX_SOURCE", "C:/tmp/scroll-hook-research-20261009/EEex"))
MENU_SOURCE = EEEX / "EEex/copy/EEex_scripts/EEex_Menu.lua"


def function(source, name):
    start = source.index("function " + name + "(")
    return source[start:source.index("\nend", start) + 4]


@pytest.fixture(params=["lua51", "luajit21"])
def ui(request):
    lua = import_module("lupa." + request.param).LuaRuntime(unpack_returned_tuples=True)
    lua.execute('''
        registry={};nextRegistry=100;logs={};lookups={};reads={}
        EEex_Menu_BeforeMainFileLoadedListeners={}
        EEex_Menu_AfterMainFileLoadedListeners={}
        uiItemType={ITEM_TEXT=1,ITEM_LABEL=2}
        uiVariantType={UIVAR_INT=1,UIVAR_FUNCTION=2,UIVAR_STRING=3,UIVAR_FLOAT=4}
        function EEex_GetLuaRegistryIndex(index)return registry[index]end
        function EEex_SetLuaRegistryIndex(index,value)assert(index);registry[index]=value end
        function EEex_AddToLuaRegistry(value)
            nextRegistry=nextRegistry+1;registry[nextRegistry]=value;return nextRegistry
        end
        function EEex_Error(message)error(message)end
        function print(message)logs[#logs+1]=message end
        EngineGlobals={findMenu=function(name,panel,state)
            assert(name=='CHARACTER' and panel==0 and state==0);return menu
        end}
        function EEex_GameObject_Get(id)
            lookups[#lookups+1]=id;return actors[id]
        end
        function EEex_Sprite_GetSelected()error('World selection is not record selection')end
        actors={
            [11]={bank=439000,cap=161000,phase='BG1',policy='bg1_sod'},
            [22]={bank=17,cap=500000,phase='SOD',policy='bg1_sod'}
        }
        authored={
            [11]={classlevel={first={details='Fighter: level 7; XP: 161000'}},kitDesc='Original kit description.'},
            [22]={classlevel={first={details='Mage: level 10; XP: 500000'}},kitDesc='Second kit description.'}
        }
        R={RecordView=function(actor,cap)
            assert(actor.cap==cap);reads[#reads+1]=actor
            if actor.unresolved then return nil end
            return {bank=actor.bank,cap=cap,phase=actor.phase,policy=actor.policy}
        end}
        reset={NativeCap=function(actor)return actor.cap end}
        requestedID=11;openCalls=0;getterCalls=0;foreignCalls=0
        function getClassString()
            getterCalls=getterCalls+1
            assert(characters and currentID,'Class getter ran before onOpen')
            local char=assert(characters[currentID]);local parts={}
            for _,key in ipairs({'first','second','third'}) do
                if char.classlevel[key] then parts[#parts+1]=char.classlevel[key].details end
            end
            return (heading or '')..table.concat(parts,'\\n\\n')..'\\n\\n'..char.kitDesc
        end
        function makeText(callback,itemType)
            return {type=itemType or uiItemType.ITEM_TEXT,
                scrollbar={bam={get=function()return 'GUISCRC'end}},
                text={text={type=uiVariantType.UIVAR_FUNCTION,
                    value={luaFunc=EEex_AddToLuaRegistry(callback)}}}}
        end
        function buildMenu()
            originalOpen=function(token)
                openCalls=openCalls+1;characters=authored;currentID=requestedID
                return token
            end
            originalText=function()return getClassString()end
            target=makeText(originalText)
            target.enabled=false -- Opening a different record tab is ordinary.
            foreignText=function()foreignCalls=foreignCalls+1;return 'Foreign scroll text'end
            foreign=makeText(foreignText)
            label=makeText(function()return getClassString()end,uiItemType.ITEM_LABEL)
            label.next=foreign;foreign.next=target
            menu={items=label,reference_onOpen={value=EEex_AddToLuaRegistry(originalOpen)}}
            return menu
        end
        function fire(list)for _,callback in ipairs(list)do callback()end end
        function render()return EEex_Menu_GetItemVariant(target.text.text)()end
        function start()
            assert(N.Install{runtime=R,reset=reset})
            fire(EEex_Menu_AfterMainFileLoadedListeners)
            assert(EEex_Menu_GetItemFunction(menu.reference_onOpen)('opened')=='opened')
        end
        buildMenu()
    ''')
    source = MENU_SOURCE.read_text(encoding="utf-8")
    for name in (
        "EEex_Menu_Find", "EEex_Menu_GetItemFunction", "EEex_Menu_SetItemFunction",
        "EEex_Menu_GetItemVariant", "EEex_Menu_AddBeforeMainFileLoadedListener",
        "EEex_Menu_AddAfterMainFileLoadedListener",
    ):
        lua.execute(function(source, name))
    lua.globals().N = lua.execute(
        (ROOT / "research/xp-banking-native/bank_record.lua").read_text(encoding="utf-8")
    )
    return lua


def test_loading_is_inert_and_original_open_initializes_before_discovery(ui):
    ui.execute('''
        assert(#EEex_Menu_BeforeMainFileLoadedListeners==0)
        assert(#EEex_Menu_AfterMainFileLoadedListeners==0)
        assert(EEex_Menu_GetItemFunction(menu.reference_onOpen)==originalOpen)
        assert(EEex_Menu_GetItemVariant(target.text.text)==originalText)
        assert(getterCalls==0 and openCalls==0 and #logs==0)
        assert(N.Install{runtime=R,reset=reset})
        assert(getterCalls==0 and openCalls==0)
        fire(EEex_Menu_AfterMainFileLoadedListeners)
        assert(getterCalls==0 and characters==nil)
        EEex_Menu_GetItemFunction(menu.reference_onOpen)()
        assert(openCalls==1 and characters==authored and getterCalls>0)
        assert(target.enabled==false and render():find('Banked XP: 439,000',1,true))
        assert(#logs==0)
    ''')


@pytest.mark.parametrize("kind", ["single", "multi", "dual"])
def test_all_class_details_precede_one_bank_then_unchanged_kit_text(ui, kind):
    ui.globals().kind = kind
    ui.execute('''
        local levels=authored[11].classlevel
        if kind~='single' then levels.second={details='Mage: level 5; XP: 12500'}end
        if kind=='multi' then levels.third={details='Thief: level 6; XP: 20000'}end
        start()
        local source=getClassString()
        local shown=render()
        local bank=assert(shown:find('Banked XP: 439,000',1,true))
        for _,level in pairs(levels)do
            local first,last=shown:find(level.details,1,true)
            assert(first and last<bank)
        end
        local kit=authored[11].kitDesc
        assert(shown:sub(-#kit)==kit and shown:find(kit,1,true)>bank)
        assert(select(2,shown:gsub('Banked XP:',''))==1)
        assert(getClassString()==source and originalText()==source)
        assert(authored[11].classlevel==levels and #logs==0)
    ''')


def test_zero_bank_and_record_actor_switch_ignore_world_selection_and_refresh_sprite(ui):
    ui.execute('''
        actors[11].bank=0;start()
        assert(render():find('Banked XP: 0',1,true))
        currentID=22
        assert(render():find('Banked XP: 17',1,true))
        local prior=actors[22]
        actors[22]={bank=1234567,cap=500000,phase='SOD',policy='bg1_sod'}
        local shown=render()
        assert(shown:find('Banked XP: 1,234,567',1,true))
        assert(reads[#reads]==actors[22] and reads[#reads]~=prior)
        assert(lookups[#lookups]==22 and #logs==0)
    ''')


def test_reopen_idempotence_reload_and_remove_preserve_foreign_handlers(ui):
    ui.execute('''
        local beforeCount,afterCount=0,0
        local otherBefore=function()beforeCount=beforeCount+1 end
        local otherAfter=function()afterCount=afterCount+1 end
        EEex_Menu_AddBeforeMainFileLoadedListener(otherBefore)
        EEex_Menu_AddAfterMainFileLoadedListener(otherAfter)
        start()
        local wrappedOpen=EEex_Menu_GetItemFunction(menu.reference_onOpen)
        local wrappedText=EEex_Menu_GetItemVariant(target.text.text)
        for _=1,3 do
            assert(N.Install{runtime=R,reset=reset})
            fire(EEex_Menu_AfterMainFileLoadedListeners)
            wrappedOpen()
            assert(EEex_Menu_GetItemFunction(menu.reference_onOpen)==wrappedOpen)
            assert(EEex_Menu_GetItemVariant(target.text.text)==wrappedText)
            assert(select(2,render():gsub('Banked XP:',''))==1)
        end
        assert(EEex_Menu_GetItemVariant(foreign.text.text)==foreignText)
        fire(EEex_Menu_BeforeMainFileLoadedListeners)
        registry={};characters=nil;currentID=nil
        buildMenu()
        fire(EEex_Menu_AfterMainFileLoadedListeners)
        EEex_Menu_GetItemFunction(menu.reference_onOpen)()
        assert(render():find('Banked XP: 439,000',1,true))
        assert(beforeCount==1 and afterCount==5)
        N.Remove();N.Remove()
        assert(EEex_Menu_GetItemFunction(menu.reference_onOpen)==originalOpen)
        assert(EEex_Menu_GetItemVariant(target.text.text)==originalText)
        assert(render()==getClassString())
        assert(#EEex_Menu_BeforeMainFileLoadedListeners==1)
        assert(EEex_Menu_BeforeMainFileLoadedListeners[1]==otherBefore)
        assert(#EEex_Menu_AfterMainFileLoadedListeners==1)
        assert(EEex_Menu_AfterMainFileLoadedListeners[1]==otherAfter)
        assert(EEex_Menu_GetItemVariant(foreign.text.text)==foreignText and #logs==0)
    ''')


def test_remove_does_not_overwrite_later_callback_owners(ui):
    ui.execute('''
        start()
        local nextText=function()return 'Later text owner'end
        local nextOpen=function()return 'Later open owner'end
        EEex_SetLuaRegistryIndex(target.text.text.value.luaFunc,nextText)
        EEex_Menu_SetItemFunction(menu.reference_onOpen,nextOpen)
        N.Remove()
        assert(EEex_Menu_GetItemVariant(target.text.text)==nextText)
        assert(EEex_Menu_GetItemFunction(menu.reference_onOpen)==nextOpen)
    ''')


def test_absent_original_open_callback_is_restored_as_absent(ui):
    ui.execute('''
        characters=authored;currentID=11;menu.reference_onOpen.value=0
        assert(N.Install{runtime=R,reset=reset})
        fire(EEex_Menu_AfterMainFileLoadedListeners)
        EEex_Menu_GetItemFunction(menu.reference_onOpen)()
        assert(render():find('Banked XP: 439,000',1,true))
        N.Remove()
        assert(menu.reference_onOpen.value==0)
        assert(EEex_Menu_GetItemFunction(menu.reference_onOpen)==nil)
        assert(EEex_Menu_GetItemVariant(target.text.text)==originalText)
    ''')


@pytest.mark.parametrize("problem", ["menu", "getter", "element", "ambiguous", "details", "scrollbar"])
def test_unrecognized_layout_preserves_callbacks_and_reports_only_once(ui, problem):
    ui.globals().problem = problem
    ui.execute('''
        local sourceText=originalText
        if problem=='menu' then menu=nil
        elseif problem=='getter' then getClassString=nil
        elseif problem=='element' then foreign.next=nil
        elseif problem=='ambiguous' then target.next=makeText(originalText)
        elseif problem=='scrollbar' then target.scrollbar.bam.get=function()return ''end
        elseif problem=='details' then
            originalText=function()return 'Unrecognized custom description'end
            EEex_SetLuaRegistryIndex(target.text.text.value.luaFunc,originalText)
        end
        local expectedCallback=EEex_Menu_GetItemVariant(target.text.text)
        assert(N.Install{runtime=R,reset=reset})
        for _=1,4 do
            fire(EEex_Menu_AfterMainFileLoadedListeners)
            if menu then EEex_Menu_GetItemFunction(menu.reference_onOpen)()end
        end
        assert(EEex_Menu_GetItemVariant(target.text.text)==expectedCallback)
        assert(#logs==1 and logs[1]:find('notices and CBMBank_Status()',1,true))
        assert(#reads==0 and #lookups==0)
    ''')


def test_duplicated_class_details_are_ambiguous_without_changing_source(ui):
    ui.execute('''
        local getter=getClassString
        getClassString=function()
            return getter()..'\\n\\n'..characters[currentID].classlevel.first.details
        end
        start()
        local source=getClassString()
        for _=1,3 do
            EEex_Menu_GetItemFunction(menu.reference_onOpen)()
            assert(render()==source)
        end
        assert(EEex_Menu_GetItemVariant(target.text.text)==originalText)
        assert(#logs==1 and #reads==0)
    ''')


def test_translated_details_headings_extra_items_and_order_are_preserved(ui):
    ui.execute('''
        heading='Personnage / Classe\\n\\n'
        authored[11].classlevel.first.details='Guerrier : niveau 7 ; Experience : 161000'
        authored[11].classlevel.second={details='Magier: Stufe 5; Erfahrung: 12500'}
        authored[11].kitDesc='Beschreibung: Sonderklasse.\\nTexte supplementaire.'
        local extra=makeText(function()return 'Additional statistics'end)
        target.scrollbar.bam.get=function()return 'CUSTOMSB'end
        menu.items=extra;extra.next=target;target.next=label;label.next=foreign;foreign.next=nil
        start()
        local shown=render()
        assert(shown:sub(1,#heading)==heading)
        assert(shown:find(authored[11].classlevel.first.details,1,true))
        assert(shown:find(authored[11].classlevel.second.details,1,true))
        assert(shown:sub(-#authored[11].kitDesc)==authored[11].kitDesc)
        assert(shown:find('Banked XP: 439,000',1,true))
        assert(EEex_Menu_GetItemVariant(extra.text.text)()=='Additional statistics')
        assert(EEex_Menu_GetItemVariant(foreign.text.text)==foreignText and #logs==0)
    ''')


@pytest.mark.parametrize("phase,policy,cap,expected,release", [
    ("BG1", "bg1_sod", 161000, "BG1 usable XP limit: 161,000.", "later campaigns"),
    ("SOD", "bg1_sod", 500000, "SoD usable XP limit: 500,000.", "the campaign cap ends there."),
    ("SOD", "bg1_sod_soa", 500000, "SoD usable XP limit: 500,000.", "up to its cap; the campaign cap ends in ToB."),
    ("SOA", "bg1_sod_soa", 2950000, "SoA usable XP limit: 2,950,000.", "usable in ToB"),
    ("SOA", "bg1_sod", 8000000, "No campaign cap in SoA. Installed XP limit: 8,000,000.", "subject to installed XP limits."),
    ("TOB", "bg1_sod_soa", 8000000, "No campaign cap in ToB. Installed XP limit: 8,000,000.", "subject to installed XP limits."),
    ("CH2", "chapter_caps", 16000, "Chapter 2 usable XP limit: 16,000.", "later chapters raise the cap."),
    ("CH14", "chapter_caps", 1000000, "Chapter 14 usable XP limit: 1,000,000.", "later chapters raise the cap."),
    ("CH22", "chapter_caps", 8900000, "Chapter 22 usable XP limit: 8,900,000.", "Final chapter XP limit reached."),
])
def test_campaign_explanation_matches_policy(ui, phase, policy, cap, expected, release):
    actor = ui.globals().actors[11]
    actor.phase, actor.policy, actor.cap = phase, policy, cap
    ui.globals().expectedCapText = expected
    ui.globals().expectedReleaseText = release
    ui.execute('''
        start()
        local shown=render()
        assert(shown:find(expectedCapText,1,true))
        assert(shown:find(expectedReleaseText,1,true))
        assert(#logs==0)
    ''')


def test_unresolved_or_missing_actor_keeps_normal_xp_visible_without_messages(ui):
    ui.execute('''
        start()
        local source=getClassString()
        actors[11].unresolved=true
        assert(render()==source)
        actors[11]=nil
        assert(render()==source and #logs==0)
    ''')


def test_missing_capability_does_not_register_or_change_menu(ui):
    ui.execute('''
        EEex_GameObject_Get=nil
        assert(not N.Install{runtime=R,reset=reset})
        assert(not N.Install{runtime=R,reset=reset})
        assert(#EEex_Menu_BeforeMainFileLoadedListeners==0)
        assert(#EEex_Menu_AfterMainFileLoadedListeners==0)
        assert(EEex_Menu_GetItemFunction(menu.reference_onOpen)==originalOpen)
        assert(EEex_Menu_GetItemVariant(target.text.text)==originalText and #logs==1)
    ''')
