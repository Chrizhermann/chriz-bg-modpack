-- UNINSTALLED. Two exact native active-picker predicate callsites only. The
-- compiled wrapper delegates ordinary screens and projects owned previews.
local M={}
local function exact(at,hex)
 for i=1,#hex,2 do assert(EEex_ReadU8(at+(i-1)/2)==tonumber(hex:sub(i,i+1),16),"Native HLA predicate callsite changed")end
end
function M.Preflight(o,image,stamp,size)
 assert(o and o.profiles and image,"Native HLA profiles required")
 local found
 for _,p in ipairs(o.profiles)do if p.gameTimestamp==stamp and p.gameSize==size then
  assert(not found,"Ambiguous native HLA profile");found=p
 end end
 assert(found,"Unreviewed native HLA engine profile")
 for _,f in pairs(found.functions)do exact(image+f.rva,f.bytes)end
 assert(EEex_Read64(image+found.listVtable)==image+found.listDestructor,"Native HLA list destructor changed")
 local patches={}
 for _,call in ipairs(found.activeCalls)do
  exact(image+call.contextRva,call.contextBytes)
  patches[#patches+1]={rva=call.rva,bytes=call.bytes,address=image+call.rva,size=5}
 end
 return {profile=found,patches=patches,sites=patches,image=image}
end
function M.Install(o)
 if o.prepared then o={researchOnly=true,profile=o.prepared.profile,image=o.prepared.image,target=o.predicate}end
 assert(not M.installed and o.researchOnly==true and o.profile and o.image and o.target,"Explicit native HLA predicate setup required")
 for _,call in ipairs(o.profile.activeCalls)do exact(o.image+call.contextRva,call.contextBytes)end
 local thunk=EEex_JITNear{"jmp ",o.target,"#ENDL"}
 local patches={}
 for _,call in ipairs(o.profile.activeCalls)do
  local at=o.image+call.rva;local delta=thunk-(at+5)
  assert(delta>=-2147483648 and delta<=2147483647,"Native HLA thunk outside rel32 range")
  patches[#patches+1]={at=at+1,before=EEex_Read32(at+1),after=delta}
 end
 EEex_DisableCodeProtection()
 local ok,why=pcall(function()for _,p in ipairs(patches)do EEex_Write32(p.at,p.after)end end)
 if not ok then
  local restored,problem=pcall(function()for _,p in ipairs(patches)do EEex_Write32(p.at,p.before)end end)
  EEex_EnableCodeProtection()
  if not restored then error("HLA predicate patch state uncertain: "..tostring(why).."; "..tostring(problem))end
  error("HLA predicate patch rolled back: "..tostring(why))
 end
 EEex_EnableCodeProtection();M.installed=true;M.patches=patches;return M
end
return M
