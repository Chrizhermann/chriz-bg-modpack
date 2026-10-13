-- PRIVATE, inert callback generator adapter. Never replaces EEex_GenLuaCall.
-- The pinned generator reserves 16 bytes after Win64's 32-byte home area for
-- lua_pcallk's ctx/k. Its final call mistakenly clears home slots 0/8 instead.
-- Set the real fifth/sixth arguments immediately at every generated pcallk call
-- (inside the generator's #ALIGN scope). Existing correct stores remain valid;
-- no English comments, source line numbers or generator version are matched.
local M={}
function M.GenLuaCall(name,meta)
    assert(type(EEex_GenLuaCall)=="function","Native EEex callback generator unavailable")
    local generated=EEex_GenLuaCall(name,meta)
    local calls=0
    local function detach(value)
        if type(value)=="table" then
            local copy={};for key,item in pairs(value) do copy[key]=detach(item) end;return copy
        elseif type(value)=="string" then
            return (value:gsub("[^\r\n]+",function(line)
                local at=line:find(";",1,true)
                local code,comment=at and line:sub(1,at-1) or line,at and line:sub(at) or ""
                local fixed,count=code:gsub("%f[%w]call%s+#L%(Hardcoded_lua_pcallk%)",function()
                    return "mov qword ptr ss:[rsp+32], 0 #ENDL "..
                        "mov qword ptr ss:[rsp+40], 0 #ENDL call #L(Hardcoded_lua_pcallk)"
                end)
                calls=calls+count;return fixed..comment
            end))
        end
        return value
    end
    local fixed=detach(generated)
    assert(calls>0,"Unrecognized native pcall generator; callback ABI must be reviewed")
    return fixed
end
return M
