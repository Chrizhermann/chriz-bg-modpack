-- Uninstalled durable HLA queue. Native delivery is allowed only at the real
-- manual commit boundary, after actual old-class reactivation. An interrupted
-- delivery is retained for explicit reconciliation, never guessed or retried.
local M={}
local function uint(n)return type(n)=="number"and n>=0 and n<=4294967295 and n%1==0 end
local function dense(list)
 assert(type(list)=="table","Ordered old HLA receipt list required")
 local count=0;for k in pairs(list)do assert(uint(k)and k>=1,"Invalid HLA receipt index");count=count+1 end
 assert(count==#list,"Sparse old HLA receipt list")
 return list
end
local function valid(entry)
 assert(type(entry)=="table"and uint(entry.id),"Invalid old HLA selection receipt")
 local d=entry.descriptor
 assert(type(d)=="table"and d.schema==1,"Unsupported old HLA descriptor")
 for _,k in ipairs({"nameStrref","minLevel","maxLevel","maxRank"})do
  assert(uint(d[k]),"Native HLA descriptor requires uint32 field "..k)
 end
 for _,k in ipairs({"icon","effect","prerequisite","excludedBy","alignment"})do
  assert(type(d[k])=="string"and not d[k]:find("\0",1,true),"Invalid native HLA text "..k)
 end
 assert(#d.icon<=8,"Invalid native HLA icon resource")
 return entry
end
function M.New(o)
 assert(o and o.wire and o.manual and o.native and o.identity and o.account,"Concrete old HLA dependencies required")
 local queue={}
 local function copy(x)local n,e=o.wire.WireSnapshot(x);assert(n,e);return n end
 local function state(sprite)
  local identity,e=o.identity.Query(sprite);assert(identity,e)
  assert(identity.eligible and identity.canMutate and not identity.serializing,"Old HLA owner is not mutable")
  local aux=EEex_GetUDAux(sprite);local c=aux.CBMBank;local b=aux.CBMBankLifetime
  assert(type(c)=="table"and not c.excluded and not c.initializing and not c.chrPending,"Unresolved old HLA carrier")
  o.account.Validate(c)
  assert(c.kind=="dual"and b and b.incarnation==identity.incarnation and b.ownerKey==c.ownerKey
   and b.origin~="chr_import","Old HLA save owner/lifetime mismatch")
  for _,entry in ipairs(dense(c.old.pendingHLAs or{}))do valid(entry)end
  return aux,c,identity
 end
 local function manual(sprite,phase)
  local aux,c,identity=state(sprite)
  local v,e=o.manual.Query(sprite);assert(v,e)
  local p=c.pendingManualProgression
  assert(v.phase==phase and v.incarnation==identity.incarnation and v.owner==c.ownerKey
   and p and p.ownerKey==v.owner and p.incarnation==v.incarnation and p.session==v.session,
   "Old HLA delivery has no matching native manual session")
  return aux,c,p,v
 end
 function queue.Pending(sprite)
  local _,c=state(sprite)
  assert(not c.old.pendingHLADelivery,"Interrupted old HLA delivery needs reconciliation")
  return copy(c.old.pendingHLAs or{})
 end
 function queue.Preview(sprite)
  local _,c=state(sprite)
  assert(not c.old.pendingHLADelivery,"Interrupted old HLA delivery needs reconciliation")
  local result=copy(c.old.pendingHLAs or{})
  local p=c.pendingManualProgression
  if p then
   local v,e=o.manual.Query(sprite);assert(v,e)
   assert(v.incarnation==p.incarnation and v.owner==c.ownerKey and p.ownerKey==c.ownerKey
    and v.session==p.session and (p.stage=="preview"or p.stage=="committing"),"Stale old HLA preview")
   if p.retired and not p.retired.hlasEnqueued then
    for _,entry in ipairs(dense(p.retired.choices.hlas))do result[#result+1]=copy(valid(entry))end
   end
  end
  return result
 end
 function queue.Prepare(sprite)
  local aux,c,p,v=manual(sprite,"committing")
  assert(p.stage=="committing"and not p.oldHLA and not c.old.pendingHLADelivery,"Repeated old HLA preparation")
  local n=copy(c);local q=n.pendingManualProgression
  n.old.pendingHLAs=n.old.pendingHLAs or{}
  local added=0
  if q.retired then
   local r=q.retired;local a=r.account
   assert(a.ownerKey==c.ownerKey and a.incarnation==v.incarnation and a.oldClass==c.old.class
    and a.activeClass==c.old.newClass and a.hasCleanReceipt==true,"Old HLA choices lack an earned old-class receipt")
   for _,entry in ipairs(dense(r.choices.hlas))do
    local item=copy(valid(entry))
    item.source={schema=1,ownerKey=c.ownerKey,session=v.session,oldClass=a.oldClass,oldKit=a.oldKit,
     beforeLevel=a.oldLevel,afterLevel=r.target}
    n.old.pendingHLAs[#n.old.pendingHLAs+1]=item;added=added+1
   end
   r.hlasEnqueued=true
  end
  q.oldHLA={schema=1,stage="prepared",count=#n.old.pendingHLAs,added=added}
  -- Reserve/validate the complete persistent delivery journal before native
  -- level-up starts; no late serializer surprise after granting abilities.
  n.old.pendingHLADelivery={schema=1,stage="delivering",ownerKey=v.owner,incarnation=v.incarnation,
   session=v.session,count=q.oldHLA.count,completedBatches=0}
  n=copy(n);n.old.pendingHLADelivery=nil
  aux.CBMBank=n;return true
 end
 function queue.Commit(sprite)
  local aux,c,p,v=manual(sprite,"committing")
  local prepared=p.oldHLA
  assert(p.stage=="committing"and prepared and prepared.stage=="prepared"
   and prepared.count==#(c.old.pendingHLAs or{})and not c.old.pendingHLADelivery,"Old HLA commit was already attempted or changed")
  local n=copy(c)
  if prepared.count==0 or o.manual.Dormant(sprite,c.old.class)then
   n.pendingManualProgression.oldHLA.stage=prepared.count==0 and"complete"or"deferred"
   aux.CBMBank=copy(n);return true
  end
  n.old.pendingHLADelivery={schema=1,stage="delivering",ownerKey=v.owner,incarnation=v.incarnation,
   session=v.session,count=prepared.count,completedBatches=0}
  aux.CBMBank=copy(n) -- durable intent precedes every possible native side effect
  local ok,status,batches=pcall(o.native.Deliver,sprite,c.old.class,v.owner,copy(n.old.pendingHLAs))
  local _,current,now,currentView=manual(sprite,"committing")
  local journal=current.old.pendingHLADelivery
  assert(journal and journal.session==v.session and currentView.session==v.session
   and journal.count==prepared.count,"Old HLA journal changed during native delivery")
  local updated=copy(current) -- retain XP/other account updates made by native AP rewards
  if not ok or status~=1 then
   updated.old.pendingHLADelivery.stage="uncertain"
   updated.old.pendingHLADelivery.completedBatches=uint(batches)and batches or 0
   updated.pendingManualProgression.oldHLA.stage="uncertain"
   aux.CBMBank=copy(updated)
   error("Old HLA delivery needs reconciliation; the saved queue was retained ("..tostring(ok and status or"native exception")..")")
  end
  assert(uint(batches)and batches==math.ceil(prepared.count/24),"Native HLA batch receipt is incomplete")
  updated.old.pendingHLAs={};updated.old.pendingHLADelivery=nil
  updated.pendingManualProgression.oldHLA.stage="complete"
  updated.pendingManualProgression.oldHLA.completedBatches=batches
  aux.CBMBank=copy(updated);return true
 end
 return queue
end
return M
