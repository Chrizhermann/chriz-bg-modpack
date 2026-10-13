-- Uninstalled compatibility adapter. Only the eventual banking component calls
-- Install; independent recruitment components do not load or require this file.
local M={}
function M.Install(runtime)
    assert(not M.installed and type(runtime)=="table","Bank compatibility already installed/invalid")
    assert(type(runtime.ActiveTotal)=="function" and type(runtime.OwnedSet)=="function")
    for _,name in ipairs({"CBMBank_Catchup","CBMBank_ActiveXP","CBMBank_ImoenXPSet"}) do
        assert(_G[name]==nil,"Bank compatibility namespace already owned: "..name)
    end
    CBMBank_ActiveXP=runtime.ActiveTotal
    CBMBank_ImoenXPSet=function(sprite,target) return runtime.OwnedSet(sprite,target,1) end
    CBMBank_Catchup=function(sprite,target)
        local ok,why=pcall(function()
            local marker="CBM_SoARecruitXP"
            if EEex_Sprite_GetLocalInt(sprite,marker)~=0 then return end
            assert(EEex_Sprite_GetCharacterIndex(sprite)>=0,"Recruitment actor is not in the party")
            assert(runtime.OwnedSet(sprite,target,2),"Recruitment XP was not committed")
            -- Mark completion only AFTER the complete XP balance is committed.
            EEex_Sprite_SetLocalInt(sprite,marker,1)
        end)
        if not ok then runtime.Report(why) end
        -- No numeric action status: EEex_LuaAction supplies ACTION_DONE.
    end
    M.installed=true
    return M
end
return M
