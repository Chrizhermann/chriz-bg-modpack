-- Effective KEY/override resource verification through the engine resource
-- registry. Inert until called by the private host; no files/game/save writes.
local M={}
function M.Digest(name,extension)
 assert(type(name)=="string"and #name>0 and #name<=8,"Invalid dependency resref")
 assert(extension=="ITM"or extension=="SPL"or extension=="EFF","Unsupported policy dependency")
 assert(type(EEex_Resource_Fetch)=="function"and type(CBMS_NativeResourceSHA256)=="function",
  "Effective native resource hash bindings are unavailable")
 local resource=EEex_Resource_Fetch(name,extension)
 if not resource then return nil,"Policy dependency is missing: "..name.."."..extension end
 -- EEex_Resource_Demand intentionally returns EFF+8; use the actual CRes
 -- method so the digest includes the external signature and all file bytes.
 local data=resource:Demand()
 if not data then return nil,"Policy dependency cannot be demanded: "..name.."."..extension end
 local size=resource.nSize
 -- The shipped LuaJIT provider can expose uint32 through signed lua_Integer.
 if type(size)=="number"and size<0 and size>=-2147483648 then size=size+4294967296 end
 assert(type(size)=="number"and size%1==0 and size>0 and size<=4294967295,
  "Policy dependency has an invalid native size")
 local digest,why=CBMS_NativeResourceSHA256(data,size)
 if not digest then return nil,why end
 assert(type(digest)=="string"and #digest==64 and digest:match("^[0-9a-f]+$"),
  "Native resource hash returned an invalid SHA256")
 return digest
end
return M
