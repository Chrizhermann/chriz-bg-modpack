-- Real EEex bank-carrier adapter; uninstalled. Only owned journal/receipt fields
-- change, no XP/levels/HP/proficiency/effect writes. Native screen owns choices.
local M={}
function M.Configure(wire,capture,bridge,ledger)
 assert(not M.wire and wire and capture and bridge and ledger and ledger.Append and ledger.Preview,"Manual receipt adapter already configured or missing dependencies")
 M.wire,M.capture,M.bridge,M.ledger=wire,capture,bridge,ledger
end
local function copy(x)local n,why=M.wire.WireSnapshot(x);assert(n,why);return n end
local function state(sprite,phase,unbound)
 local view,why=M.bridge.Query(sprite);assert(view,why)
 assert(view.phase==phase,"Unexpected native manual-screen phase")
 local aux=EEex_GetUDAux(sprite);local carrier=aux.CBMBank;local binding=aux.CBMBankLifetime
 assert(type(carrier)=="table" and not carrier.excluded and not carrier.pendingDual,"Unresolved bank carrier")
 assert(binding and binding.ownerKey==carrier.ownerKey and binding.incarnation==view.incarnation
  and (carrier.ownerKey==view.owner or (unbound and view.owner=="")),"Manual screen/save owner mismatch")
 return aux,carrier,view
end
local function pending(carrier,view)
 local p=carrier.pendingManualProgression
 assert(p and p.session==view.session and p.incarnation==view.incarnation and p.ownerKey==view.owner,
  "Missing matching native manual journal")
 return p
end
local function archive(carrier)
 local target=carrier.old and carrier.old.rewardReceipt or carrier
 -- Private pre-integration prototypes stored full completed receipts. Preserve
 -- every semantic record when converting them, never silently cap the list.
 for _,key in ipairs({"manualTransactions","manualProgressionReceipts"})do
  if target[key]then for _,receipt in ipairs(target[key])do M.ledger.Append(target,receipt)end;target[key]=nil end
 end
 return target
end
function M.Begin(sprite)
 local aux,current,v=state(sprite,"preparing",true)
 assert(not current.pendingManualProgression,"Unresolved manual progression journal retained")
 assert(M.bridge.BindOwner(sprite,current.ownerKey),"Saved owner could not bind native screen")
 aux,current,v=state(sprite,"preparing")
 local nextState=copy(current)
 archive(nextState).lastManualSnapshot=nil -- new pending BEFORE supersedes diagnostic AFTER
 nextState.pendingManualProgression={schema=1,stage="preview",ownerKey=v.owner,incarnation=v.incarnation,
  session=v.session,ledgerRevision=current.revision,before=M.capture.CaptureState(sprite)}
 aux.CBMBank=copy(nextState);return true
end
function M.PrepareCommit(sprite)
 local aux,current,v=state(sprite,"committing");local p=pending(current,v)
 assert(p.stage=="preview" and p.ledgerRevision==current.revision,"Manual journal changed during preview")
 assert(v.hpStatus==1,"Native HP samples are incomplete")
 local hp=M.bridge.HP(sprite);assert(hp and hp.status==1,"Missing native HP batch")
 local samples={};for i=0,hp.count-1 do
  local sample=M.bridge.HPSample(sprite,i);assert(sample,"Missing native per-level HP sample")
  samples[#samples+1]=sample
 end
 hp.samples=samples;hp.cached=v.hpCached
 local choices={};for i=0,v.choiceCount-1 do
  local choice=M.bridge.Choice(sprite,i);assert(choice and choice.status==1,"Incomplete native proficiency choice")
  -- Preserve serializer-safe signed word bits, not guessed allocation ownership.
  for _,key in ipairs({"requested","before","after"})do choice[key]=choice[key]%4294967296 end
  choices[#choices+1]=choice
 end
 local n=copy(current);local q=n.pendingManualProgression
 q.stage="committing";q.hp=hp;q.choices=choices;q.preview=M.ledger.Preview(M.capture.CaptureState(sprite))
 aux.CBMBank=copy(n);return true
end
function M.Complete(sprite)
 local aux,current,v=state(sprite,"committing");local p=pending(current,v)
 -- Native CLAB rewards may themselves award XP during commit. Retain those root
 -- account updates; the unchanged owner/session journal establishes this commit.
 assert(p.stage=="committing","Stale manual commit journal")
 local n=copy(current);local receipt=n.pendingManualProgression
 receipt.stage="committed";receipt.after=M.capture.CaptureState(sprite)
 n.pendingManualProgression=nil
 -- Existing-dual adoption uses the same semantic ledger on the carrier itself;
 -- it never receives a fabricated clean retired-allocation baseline.
 M.ledger.Append(archive(n),receipt)
 aux.CBMBank=copy(n);return true
end
function M.Cancel(sprite)
 local aux,current,v=state(sprite,"canceling");local p=pending(current,v)
 assert(p.stage=="preview","Cannot cancel a native commit with uncertain outcome")
 local n=copy(current);n.pendingManualProgression=nil;aux.CBMBank=copy(n);return true
end
function M.Uncertain(sprite)
 local aux,current,v=state(sprite,"uncertain");pending(current,v)
 local n=copy(current);n.pendingManualProgression.stage="uncertain";aux.CBMBank=copy(n);return true
end
return M
