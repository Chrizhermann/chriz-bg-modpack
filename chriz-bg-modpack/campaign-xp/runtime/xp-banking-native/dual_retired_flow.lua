-- Uninstalled real account/rules/screen integration. Module loading is inert.
-- Native engine wrappers select the actor; the main game's menu is not patched.
local M={}
local keys={"ownerKey","incarnation","revision","oldClass","activeClass","oldKit","oldLevel","oldUsableXP","activeUsableXP"}
local function same(a,b)for _,k in ipairs(keys)do if a[k]~=b[k]then return false end end;return true end
function M.New(o)
 for _,n in ipairs({"runtime","rules","entry","manual","receipts","pickerModule","controllerModule","rows","wire","hla"})do assert(o[n],"Missing concrete retired flow module "..n)end
 assert(type(o.runtime.ManualOwnership)=="function","Concrete campaign/account manual ownership query required")
 local picker=o.pickerModule.New();local controller=o.controllerModule.New(o.runtime,o.rules,o.entry)
 local flow={};local page,launch;local presentation,menuLoader,hlaToken
 local function clearHLA()
  local token=hlaToken;hlaToken=nil -- cleanup is one-shot even on a native exception
  if token then assert(o.hla.ClearManual(token),"Scoped HLA context could not close")end
 end
 local function copy(x)local value,why=o.wire.WireSnapshot(x);assert(value,why);return value end
 local function pointer(s)return EEex_UDToPtr(s)end
 local function account(s)
  local ownership=o.runtime.ManualOwnership(s)
  if ownership=="passthrough"then return nil end
  assert(ownership=="owned","Unknown manual progression ownership")
  local a,why=o.runtime.OldProgression(s)
  if not a then local c=EEex_GetUDAux(s).CBMBank
   if c and (c.pendingManualProgression or c.pendingDual or c.pendingAward or c.pendingWrite
    or (c.kind=="dual" and not c.excluded))then error(why or "Unresolved earned progression")end
  end
  return a,why
 end
 local function due(s)
  local a=account(s);if not a then return nil end
  local target,why=o.rules.Target(s,a);assert(target,why)
  return a,target
 end
 function flow.Eligible(s)
  local a,target=due(s);if not a or target<=a.oldLevel then return 0 end
  local prepared=controller.Preflight(s);return prepared and 1 or -1
 end
 function flow.Route(s)
  local a,target=due(s);if not a or target<=a.oldLevel then return 0 end
  if picker.IsOpen()then return 1 end
  local prepared,why=controller.Preflight(s);assert(prepared,why)
  local model,beforeSkills=o.rows.Build(s,a,target,o.rules,o.manual)
  local begun,problem=pcall(picker.Begin,model)
  if not begun then if model.onClose then model.onClose()end;error(problem)end
  page={actor=pointer(s),sprite=s,account=copy(a),prepared=prepared,beforeSkills=copy(beforeSkills)}
  presentation.ResetSelection();Infinity_PushMenu(o.pickerModule.menuName);return 1
 end
 function flow.Continue()
  assert(page and picker.CanContinue(),"Incomplete old-class choices")
  local selected=copy(picker.Choices()) -- onclose discards the detached model
  local prepared,why=controller.Revalidate(page.sprite,page.prepared);assert(prepared,why)
  assert(o.rows.ValidateSkills(page.sprite,page.account,selected,page.beforeSkills))
  launch={actor=page.actor,account=copy(page.account),target=prepared.target,choices=selected,beforeSkills=copy(page.beforeSkills)}
  local sprite=page.sprite;page=nil
  local closed,problem=pcall(Infinity_PopMenu,o.pickerModule.menuName)
  if not closed then launch=nil;error(problem)end
  return o.entry.Open(sprite,launch.account,launch.target)
 end
 local function update(s,f)
  local aux=EEex_GetUDAux(s);local current=aux.CBMBank;local view=assert(o.manual.Query(s))
  assert(current and current.ownerKey==view.owner and current.pendingManualProgression
   and current.pendingManualProgression.session==view.session and current.pendingManualProgression.incarnation==view.incarnation,
   "Saved manual transaction no longer owns this actor")
  local nextState=copy(current);f(nextState,nextState.pendingManualProgression);aux.CBMBank=copy(nextState)
 end
 function flow.Begin(s)
  local ownership=o.runtime.ManualOwnership(s)
  if ownership=="passthrough"then assert(not launch,"Prepared old choices lost their bank ownership");return 2 end
  assert(ownership=="owned","Unknown manual progression ownership")
  -- Query the parent BEFORE publishing the manual journal, which deliberately
  -- makes ordinary account queries unavailable until Commit or Cancel.
  local a,target=due(s);local selected=launch
  if selected then assert(selected.actor==pointer(s) and a and same(selected.account,a) and selected.target==target,"Prepared old choices became stale")end
  local owned=a and a.hasCleanReceipt and o.manual.Dormant(s,a.oldClass)
  if owned and target>a.oldLevel then assert(selected,"Old-class choices must be completed before active choices")end
  if selected then assert(o.rows.ValidateSkills(s,a,selected.choices,selected.beforeSkills))end
  assert(o.receipts.Begin(s));launch=nil
  if not owned then
   if a then hlaToken=assert(o.hla.PrepareManual(s,a,target,{proficiencies={},skills={},hlas={}}))end
   return 1
  end
  selected=selected or {account=copy(a),target=target,choices={proficiencies={},skills={},hlas={},unusedProfPoints=0,unusedSkillPoints=0,unusedHlaPoints=0},beforeSkills=o.manual.ReadSkills(s)}
  -- The native manual HP cache keys levels, not changing CON bonuses. Reopening
  -- the same owed old interval must reuse its base rolls after an equipment/
  -- ability change too; keep original CON as evidence, not a reroll trigger.
  local cacheKey=table.concat({a.ownerKey,a.oldClass,a.oldKit,a.oldLevel,target},":")
  local constitution=o.manual.Constitution(s)
  local rolls;local carrier=EEex_GetUDAux(s).CBMBank;local cached=carrier.oldManualHPPreview
  if cached and cached.key==cacheKey then assert(cached.stage=="complete","An earlier native roll has an uncertain outcome");rolls=copy(cached.rolls)end
  update(s,function(n,p)
   p.retired={schema=1,account=copy(a),target=target,choices=copy(selected.choices),beforeSkills=copy(selected.beforeSkills)}
   if not rolls then n.oldManualHPPreview={schema=1,key=cacheKey,stage="rolling",constitutionAtRoll=constitution}end
  end)
  if not rolls then
   rolls=o.rules.Roll(s,a)
   update(s,function(n)n.oldManualHPPreview={schema=1,key=cacheKey,stage="complete",constitutionAtRoll=constitution,rolls=copy(rolls)}end)
  end
  update(s,function(_,p)p.retired.hp=copy(rolls)end)
  assert(o.manual.SelectOld(s,a,target,rolls,selected.choices,selected.beforeSkills))
  hlaToken=assert(o.hla.PrepareManual(s,a,target,selected.choices));return 1
 end
 function flow.PrepareCommit(s)
  assert(o.receipts.PrepareCommit(s));return o.runtime.PrepareOldHLAs(s)
 end
 function flow.Complete(s)
  assert(o.runtime.CommitOldHLAs(s))
  clearHLA()
  update(s,function(n)n.oldManualHPPreview=nil end)
  return o.receipts.Complete(s)
 end
 function flow.Cancel(s)launch=nil;clearHLA();return o.receipts.Cancel(s)end
 function flow.Uncertain(s)launch=nil;clearHLA();return o.receipts.Uncertain(s)end
 function flow.InstallUI(resource)
  assert(not presentation and type(resource)=="string" and #resource>0 and #resource<=8,"Explicit owned menu resource required")
  assert(CBMDOldPickerContinue==nil,"Old-class Continue callback already owned")
  assert(type(EEex_Menu_AddAfterMainFileLoadedListener)=="function"and type(EEex_Menu_AfterMainFileLoadedListeners)=="table",
   "Native main-menu load listener API unavailable")
  presentation=o.pickerModule.Bind(picker);CBMDOldPickerContinue=flow.Continue
  menuLoader=function()
   -- F5 rebuild invalidates only the detached page. The native manual session
   -- and its separate Cancel/Commit journal are not silently dismissed here.
   page=nil;launch=nil;picker.Cancel();presentation.ResetSelection()
   EEex_Menu_LoadFile(resource)
  end
  EEex_Menu_AddAfterMainFileLoadedListener(menuLoader)
 end
 function flow.UninstallUI()
  if menuLoader then
   -- Pinned EEex provides the public listener array but no removal helper.
   for i=#EEex_Menu_AfterMainFileLoadedListeners,1,-1 do
    if EEex_Menu_AfterMainFileLoadedListeners[i]==menuLoader then table.remove(EEex_Menu_AfterMainFileLoadedListeners,i)end
   end
   menuLoader=nil
  end
  page=nil;launch=nil;picker.Cancel()
  if CBMDOldPickerContinue==flow.Continue then CBMDOldPickerContinue=nil end
 end
 return flow
end
return M
