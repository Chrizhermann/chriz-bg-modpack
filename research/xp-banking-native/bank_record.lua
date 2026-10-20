-- Presentation only. The default CHARACTER Class panel is scrollable and shows
-- classlevel.*.details (including XP), followed by kitDesc. No UI.MENU edits,
-- coordinates, translated-text matching, actor writes, or polling notices.
local M={installed=false}
local bindings={}
local opener
local function report(reason)
    if M.logged then return end
    M.logged=true
    print("[CBM campaign XP] Banked XP record display unavailable: "..tostring(reason)..
        "; notices and CBMBank_Status() remain available.")
end
local function details()
    local character=characters and characters[currentID]
    local levels=character and character.classlevel
    if type(levels)~="table" then return nil end
    local parts={}
    for _,key in ipairs({"first","second","third"}) do
        local level=levels[key]
        if level then
            if type(level.details)~="string" or level.details=="" then return nil end
            parts[#parts+1]=level.details
        end
    end
    if #parts==0 then return nil end
    return table.concat(parts,"\n\n")
end
local function insertionPoint(text)
    local prefix=details()
    if type(text)~="string" or not prefix then return nil end
    local first,last=text:find(prefix,1,true)
    -- Duplicate class-detail blocks are ambiguous. Extra headings, descriptions,
    -- translations, and different numbers of classes otherwise remain intact.
    if not first or text:find(prefix,last+1,true) then return nil end
    return last
end
local function number(n)
    local s=string.format("%.0f",n)
    local grouped=s:reverse():gsub("(%d%d%d)","%1,"):reverse()
    return (grouped:gsub("^,",""))
end
local function explanation(view)
    if view.policy=="chapter_caps" then
        local ch=view.phase:match("^CH(%d+)$")
        local label=ch and ("Chapter "..ch) or view.phase
        local cap=label.." usable XP limit: "..number(view.cap).."."
        local release=view.phase=="CH22"
            and "Final chapter XP limit reached. Other installed XP limits still apply."
            or "Banked XP becomes usable as later chapters raise the cap. Other installed XP limits still apply."
        return cap.."\n"..release
    end
    local campaign=({BG1="BG1",SOD="SoD",SOA="SoA",TOB="ToB"})[view.phase]
    local capped=view.phase=="BG1" or view.phase=="SOD"
        or (view.phase=="SOA" and view.policy=="bg1_sod_soa")
    local cap=capped and (campaign.." usable XP limit: "..number(view.cap)..".")
        or ("No campaign cap in "..campaign..". Installed XP limit: "..number(view.cap)..".")
    local release
    if view.phase=="BG1" then
        release="Banked XP becomes usable as later campaigns raise or remove the cap."
    elseif view.phase=="SOD" then
        release="Banked XP becomes usable in SoA"..
            (view.policy=="bg1_sod_soa" and " up to its cap; the campaign cap ends in ToB." or "; the campaign cap ends there.")
    elseif capped then
        release="Banked XP becomes usable in ToB when the campaign cap ends."
    else
        release="Any remaining bank is subject to installed XP limits."
    end
    return cap.."\n"..release..(capped and " Other installed XP limits still apply." or "")
end
function M.Decorate(text)
    if not M.installed then return text end
    local ok,result=pcall(function()
        local at=insertionPoint(text)
        if not at then report("class XP text could not be located");return text end
        if type(currentID)~="number" then return text end
        -- currentID is CScreenCharacter's actor ID, not the world selection or
        -- a portrait slot. Never retain a sprite userdata between renders.
        local sprite=EEex_GameObject_Get(currentID)
        if not sprite then return text end
        local view=M.runtime.RecordView(sprite,M.reset.NativeCap(sprite))
        if not view then return text end
        return text:sub(1,at).."\n\nBanked XP: "..number(view.bank).."\n"..
            explanation(view)..text:sub(at+1)
    end)
    if not ok then report(result);return text end
    return result
end
local function attachText(menu)
    if #bindings>0 then return end
    if type(getClassString)~="function" then report("class XP getter is missing");return end
    local expected=getClassString()
    if not insertionPoint(expected) then report("class XP text could not be located");return end
    local found
    local item=menu.items
    while item do
        -- Evaluate only scrollable text bindings, at record-open time AFTER the
        -- game's onOpen has initialized characters[currentID]. The Class tab
        -- need not be active. This is EEex_Options' FindItemByText pattern.
        if item.type==uiItemType.ITEM_TEXT and item.scrollbar.bam:get()~="" then
            local variant=item.text.text
            local callback=EEex_Menu_GetItemVariant(variant)
            if type(callback)=="function" then
                local ok,text=pcall(callback)
                if ok and text==expected then
                    if found then report("multiple class XP text elements");return end
                    found={index=variant.value.luaFunc,original=callback}
                end
            end
        end
        item=item.next
    end
    if not found then report("CHARACTER class XP text element is missing");return end
    found.wrapper=function(...) return M.Decorate(found.original(...)) end
    EEex_SetLuaRegistryIndex(found.index,found.wrapper)
    bindings[1]=found
end
local function afterLoad()
    if not M.installed then return end
    local menu=EEex_Menu_Find("CHARACTER")
    if not menu then report("CHARACTER menu is missing");return end
    local original=EEex_Menu_GetItemFunction(menu.reference_onOpen)
    if opener and original==opener.wrapper then return end
    opener={reference=menu.reference_onOpen,original=original}
    local owned=opener
    owned.wrapper=function(...)
        local result
        if original then result=original(...) end
        if M.installed then
            local ok,why=pcall(attachText,menu)
            if not ok then report(why) end
        end
        return result
    end
    EEex_Menu_SetItemFunction(owned.reference,owned.wrapper)
end
local function beforeLoad()
    -- Native menu objects and Lua registry entries will be discarded/rebuilt.
    -- Do not dereference the old objects after a main-file reload.
    bindings={};opener=nil
end
local function onLoaded()
    local ok,why=pcall(afterLoad)
    if not ok then report(why) end
end
function M.Install(o)
    if M.installed then return true end
    for _,name in ipairs({"EEex_Menu_Find","EEex_Menu_GetItemFunction","EEex_Menu_SetItemFunction",
        "EEex_Menu_GetItemVariant","EEex_GetLuaRegistryIndex","EEex_SetLuaRegistryIndex",
        "EEex_Menu_AddBeforeMainFileLoadedListener","EEex_Menu_AddAfterMainFileLoadedListener",
        "EEex_GameObject_Get"}) do
        if type(_G[name])~="function" then report("missing "..name);return false end
    end
    if type(uiItemType)~="table" or uiItemType.ITEM_TEXT==nil then
        report("scrollable text capability is missing");return false
    end
    M.runtime,M.reset=o.runtime,o.reset
    M.installed=true
    local ok,why=pcall(function()
        EEex_Menu_AddBeforeMainFileLoadedListener(beforeLoad)
        EEex_Menu_AddAfterMainFileLoadedListener(onLoaded)
    end)
    if not ok then M.Remove();report(why);return false end
    return true
end
function M.Remove()
    M.installed=false
    for _,binding in ipairs(bindings) do
        if EEex_GetLuaRegistryIndex(binding.index)==binding.wrapper then
            EEex_SetLuaRegistryIndex(binding.index,binding.original)
        end
    end
    if opener and EEex_Menu_GetItemFunction(opener.reference)==opener.wrapper then
        if opener.original then EEex_Menu_SetItemFunction(opener.reference,opener.original)
        else opener.reference.value=0 end
    end
    for _,entry in ipairs({{"EEex_Menu_BeforeMainFileLoadedListeners",beforeLoad},
        {"EEex_Menu_AfterMainFileLoadedListeners",onLoaded}}) do
        local list=_G[entry[1]]
        if type(list)=="table" then
            for i=#list,1,-1 do if list[i]==entry[2] then table.remove(list,i) end end
        end
    end
    beforeLoad()
end
return M
