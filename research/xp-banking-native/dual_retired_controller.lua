-- Uninstalled controller for the owned retired-class first page. This module
-- connects the REAL account provider, native installed-rules resolver and native
-- restricted-entry query. It deliberately opens no screen until the reversible
-- proficiency preview/commit adapter is complete; no fabricated reward callback.
local M={}
function M.New(runtime,rules,entry)
 assert(runtime and type(runtime.OldProgression)=="function" and rules and type(rules.Target)=="function"
  and entry and type(entry.Check)=="function","Concrete old progression modules required")
 local controller={}
 function controller.Preflight(sprite)
  local account,why=runtime.OldProgression(sprite)
  if not account then return nil,why end
  local target,problem=rules.Target(sprite,account)
  if not target then return nil,problem end
  if target<=account.oldLevel then return nil,"The old class has no level available" end
  if not account.hasCleanReceipt then return nil,"The old class has no captured pre-dual reward history" end
  local allowed,restriction=entry.Check(sprite,account,target)
  if not allowed then return nil,restriction end
  -- No HP, skills or aggregate pips equality gate. These may legitimately
  -- change through equipment and effects between page opens.
  return {schema=1,ownerKey=account.ownerKey,incarnation=account.incarnation,revision=account.revision,
   oldClass=account.oldClass,activeClass=account.activeClass,oldKit=account.oldKit,
   oldLevel=account.oldLevel,target=target,oldUsableXP=account.oldUsableXP,activeUsableXP=account.activeUsableXP}
 end
 function controller.Revalidate(sprite,prepared)
  assert(type(prepared)=="table" and prepared.schema==1,"Prepared retired page required")
  local now,why=controller.Preflight(sprite);if not now then return nil,why end
  for _,key in ipairs({"ownerKey","incarnation","revision","oldClass","activeClass","oldKit",
   "oldLevel","target","oldUsableXP","activeUsableXP"})do
   if now[key]~=prepared[key]then return nil,"The character or earned progression changed; reopen the old-class choices"end
  end
  return now
 end
 return controller
end
return M
