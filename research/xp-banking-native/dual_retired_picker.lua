-- Detached old-class choices. This module neither reads nor writes an actor.
-- Native installed rules supply complete legal rows, budgets and current basis.
local M={menuName="CBMD_OLD_PICKER"}
local function integer(value,low,high,label)
 assert(type(value)=="number" and value==math.floor(value) and value>=low and value<=high,
  "Invalid "..label);return value
end
local function clone(value)
 if type(value)~="table"then return value end
 local copy={};for k,v in pairs(value)do copy[k]=clone(v)end;return copy
end
local function rows(input,kind)
 assert(type(input)=="table","Missing "..kind.." choices")
 local result,seen={},{}
 for i,row in ipairs(input)do
  assert(type(row)=="table" and type(row.label)=="string" and #row.label>0,"Invalid choice label")
  local id=kind=="proficiencies" and integer(row.stat,89,134,"proficiency stat")or row.id
  if kind=="skills"then
   assert((type(id)=="string"and #id>0)or(type(id)=="number"and id%1==0 and id>=0 and id<=4294967295),
    "Invalid skill identity")
  end
  assert(not seen[id],"Duplicate "..kind.." choice");seen[id]=true
  local bound=kind=="proficiencies"and 7 or 255
  result[i]={label=row.label,value=integer(row.value,0,bound,"current choice value"),
   limit=integer(row.limit,0,bound,"installed choice limit"),delta=0}
  result[i][kind=="proficiencies"and"stat"or"id"]=id
 end
 -- A sparse/non-array input would silently hide choices in the UI.
 for key in pairs(input)do assert(type(key)=="number"and key%1==0 and key>=1 and key<=#result,
  "Choice rows must form an ordered array")end
 return result
end
function M.New()
 local state,canChooseHLA,onClose
 local picker={}
 local function hlaEligible(id,selected)
  local ok,why=canChooseHLA(id,clone(selected))
  assert(type(ok)=="boolean","Native HLA eligibility did not return a decision")
  return ok,why
 end
 local function hlaWithout(index)
  local id=state.hlas[index].id;local selected=clone(state.hlaSelections)
  for i=#selected,1,-1 do
   if selected[i]==id then table.remove(selected,i);return selected end
  end
 end
 local function group(kind)
  assert(state,"No old-class choices are open")
  assert(kind=="proficiencies"or kind=="skills","Invalid choice group")
  return state[kind],kind=="proficiencies"and"unusedProfPoints"or"unusedSkillPoints"
 end
 function picker.Begin(prepared)
  assert(not state,"Finish or cancel the current old-class choices first")
  assert(type(prepared)=="table"and type(prepared.className)=="string"and #prepared.className>0,
   "Current old-class rules required")
  local before=integer(prepared.oldLevel,1,255,"old class level")
  local target=integer(prepared.target,before+1,255,"selected old class level")
  local nextState={className=prepared.className,oldLevel=before,target=target,
   unusedProfPoints=integer(prepared.profPoints,0,4294967295,"proficiency budget"),
   unusedSkillPoints=integer(prepared.skillPoints,0,4294967295,"skill budget"),
   proficiencies=rows(prepared.proficiencies,"proficiencies"),skills=rows(prepared.skills,"skills")}
  nextState.unusedHlaPoints=integer(prepared.hlaPoints or 0,0,4294967295,"HLA budget")
  nextState.hlas={};nextState.hlaSelections={}
  local seen={}
  for i,row in ipairs(prepared.hlas or{})do
   assert(type(row)=="table"and type(row.label)=="string"and #row.label>0 and type(row.descriptor)=="table",
    "Complete detached HLA row required")
   integer(row.id,0,4294967295,"HLA row identity");assert(not seen[row.id],"Duplicate HLA row identity");seen[row.id]=true
   nextState.hlas[i]={id=row.id,label=row.label,description=row.description or"",descriptor=clone(row.descriptor),delta=0}
  end
  for key in pairs(prepared.hlas or{})do
   assert(type(key)=="number"and key%1==0 and key>=1 and key<=#nextState.hlas,"HLA rows must form an ordered array")
  end
  assert(nextState.unusedHlaPoints==0 or type(prepared.canChooseHLA)=="function","Native old HLA eligibility required")
  assert(prepared.onClose==nil or type(prepared.onClose)=="function","Invalid detached picker cleanup")
  canChooseHLA=prepared.canChooseHLA
  onClose=prepared.onClose
  state=nextState;return picker.View()
 end
 function picker.IsOpen()return state~=nil end
 function picker.View()return state and clone(state)or nil end
 function picker.CanAdjust(kind,index,amount)
  if not state or(kind~="proficiencies"and kind~="skills"and kind~="hlas")or type(index)~="number"or index%1~=0
   or type(amount)~="number"or amount%1~=0 or amount==0 then return false end
  if kind=="hlas"then
   local row=state.hlas[index];if not row or(amount~=1 and amount~=-1)then return false end
   if amount==1 then return state.unusedHlaPoints>0 and hlaEligible(row.id,state.hlaSelections)end
   local proposed=hlaWithout(index);if not proposed then return false end
   -- Removing a prerequisite must not leave an invalid sequence. Native rules
   -- decide each replayed prefix; the picker does not reinterpret kit rules.
   local prefix={}
   for _,id in ipairs(proposed)do
    if not hlaEligible(id,prefix)then return false end
    prefix[#prefix+1]=id
   end
   return true
  end
  local entries,budget=group(kind);local row=entries[index]
  if not row then return false end
  if amount<0 then return row.delta+amount>=0 end
  -- Values already above an installed cap are preserved. They are not a
  -- prerequisite failure or permission to add still more pips.
  return amount<=state[budget]and row.value+row.delta+amount<=row.limit
 end
 function picker.Adjust(kind,index,amount)
  if not picker.CanAdjust(kind,index,amount)then return false end
  if kind=="hlas"then
   local row=state.hlas[index]
   if amount==1 then state.hlaSelections[#state.hlaSelections+1]=row.id
   else state.hlaSelections=hlaWithout(index)end
   row.delta=row.delta+amount;state.unusedHlaPoints=state.unusedHlaPoints-amount;return true
  end
  local entries,budget=group(kind)
  entries[index].delta=entries[index].delta+amount;state[budget]=state[budget]-amount
  return true
 end
 function picker.Exhausted(kind)
  if kind=="hlas"then
   assert(state,"No old-class choices are open")
   for _,row in ipairs(state.hlas)do if hlaEligible(row.id,state.hlaSelections)then return false end end
   return true
  end
  local entries=group(kind)
  for _,row in ipairs(entries)do if row.value+row.delta<row.limit then return false end end
  return true
 end
 function picker.CanContinue()
  return state~=nil and(state.unusedProfPoints==0 or picker.Exhausted("proficiencies"))
   and(state.unusedSkillPoints==0 or picker.Exhausted("skills"))
   and(state.unusedHlaPoints==0 or picker.Exhausted("hlas"))
 end
 function picker.Choices()
  assert(state,"No old-class choices are open")
  local result={proficiencies={},skills={},hlas={},unusedProfPoints=state.unusedProfPoints,
   unusedSkillPoints=state.unusedSkillPoints,unusedHlaPoints=state.unusedHlaPoints}
  for _,kind in ipairs({"proficiencies","skills"})do
   for _,row in ipairs(state[kind])do
    result[kind][#result[kind]+1]=kind=="proficiencies"and{stat=row.stat,delta=row.delta}or{id=row.id,delta=row.delta}
   end
  end
  local byId={};for _,row in ipairs(state.hlas)do byId[row.id]=row end
  for _,id in ipairs(state.hlaSelections)do
   result.hlas[#result.hlas+1]={id=id,descriptor=clone(byId[id].descriptor)}
  end
  return result
 end
 function picker.Cancel()
  local close=onClose;state=nil;canChooseHLA=nil;onClose=nil
  if close then close()end
 end
 return picker
end

-- Explicit presentation adapter. Loading this module has no global/UI effects.
-- The owner registers CBMDOldPickerContinue and performs actor/session checks;
-- the menu never impersonates a native level-up or invokes a dual-class reset.
function M.Bind(picker,globals)
 globals=globals or _G
 assert(type(picker)=="table"and type(picker.Begin)=="function","Detached picker required")
 local names={"CBMDOldPickerProfRows","CBMDOldPickerSkillRows","CBMDOldPickerProfRow","CBMDOldPickerSkillRow",
  "CBMDOldPickerTitle","CBMDOldPickerHelp","CBMDOldPickerProfBudget","CBMDOldPickerSkillBudget",
  "CBMDOldPickerRefresh","CBMDOldPickerCanAdjust","CBMDOldPickerAdjust","CBMDOldPickerCanContinue",
  "CBMDOldPickerCancel","CBMDOldPickerClosed","CBMDOldPickerHlaRows","CBMDOldPickerHlaRow",
  "CBMDOldPickerHlaBudget","CBMDOldPickerHlaPage","CBMDOldPickerHasHlas","CBMDOldPickerHlaDetail"}
 for _,name in ipairs(names)do assert(globals[name]==nil,"Old-class picker UI name is already owned: "..name)end
 local function refresh()
  local view=picker.View()
  globals.CBMDOldPickerProfRows=view and view.proficiencies or{}
  globals.CBMDOldPickerSkillRows=view and view.skills or{}
  globals.CBMDOldPickerHlaRows=view and view.hlas or{}
  globals.CBMDOldPickerHasHlas=view and(view.unusedHlaPoints>0 or #view.hlaSelections>0)or false
  globals.CBMDOldPickerTitle=view and string.format("%s: level %d to %d",view.className,view.oldLevel,view.target)or"Old-class level up"
  globals.CBMDOldPickerHelp="Choose the old class's earned improvements. Continue opens the remaining level-up choices. Cancel discards these selections."
  local function budget(n,full)
   if n==0 then return "All points assigned"end
   return tostring(n).." points remaining"..(full and" (all available choices are at their limits)"or"")
  end
  globals.CBMDOldPickerProfBudget=view and budget(view.unusedProfPoints,picker.Exhausted("proficiencies"))or""
  globals.CBMDOldPickerSkillBudget=view and budget(view.unusedSkillPoints,picker.Exhausted("skills"))or""
  globals.CBMDOldPickerHlaBudget=view and budget(view.unusedHlaPoints,
   view.unusedHlaPoints>0 and picker.Exhausted("hlas"))or""
 end
 globals.CBMDOldPickerProfRow=1;globals.CBMDOldPickerSkillRow=1;globals.CBMDOldPickerHlaRow=1
 globals.CBMDOldPickerHlaPage=false
 globals.CBMDOldPickerHlaDetail=function()
  local row=globals.CBMDOldPickerHlaRows[globals.CBMDOldPickerHlaRow]
  return row and row.description or""
 end
 globals.CBMDOldPickerRefresh=refresh
 local function selected(kind)
  if kind=="hlas"then return globals.CBMDOldPickerHlaRow end
  return kind=="proficiencies"and globals.CBMDOldPickerProfRow or globals.CBMDOldPickerSkillRow
 end
 globals.CBMDOldPickerCanAdjust=function(kind,amount)return picker.CanAdjust(kind,selected(kind),amount)end
 globals.CBMDOldPickerAdjust=function(kind,amount)
  local changed=picker.Adjust(kind,selected(kind),amount);refresh();return changed
 end
 globals.CBMDOldPickerCanContinue=function()return picker.CanContinue()end
 globals.CBMDOldPickerClosed=function()picker.Cancel();refresh()end
 globals.CBMDOldPickerCancel=function()
  picker.Cancel();refresh()
  assert(type(globals.Infinity_PopMenu)=="function","Native menu close API unavailable")
  globals.Infinity_PopMenu(M.menuName)
 end
 refresh()
 return {Refresh=refresh,ResetSelection=function()
  globals.CBMDOldPickerProfRow=1;globals.CBMDOldPickerSkillRow=1;globals.CBMDOldPickerHlaRow=1
  globals.CBMDOldPickerHlaPage=false;refresh()
 end}
end
return M
