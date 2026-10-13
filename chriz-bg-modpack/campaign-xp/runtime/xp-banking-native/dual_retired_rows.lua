-- Installed-rule model for the detached picker; no character mutation.
local M={}
local fallbackClasses={[1]="Mage",[2]="Fighter",[3]="Cleric",[4]="Thief",[11]="Druid",[12]="Ranger"}
local function text(ref,fallback)
 local n=tonumber(ref)
 if n and n%1==0 and n>=0 and n<=4294967295 and n~=4294967295 then
  local value=Infinity_FetchString(n)
  if type(value)=="string"and #value>0 then return value end
 end
 return fallback
end
local function tableWork(name,fn)
 local data=EEex_Resource_Load2DA(name);assert(data,"Installed "..name.." table unavailable")
 local ok,result=pcall(fn,data)
 data:free()
 if not ok then error(result)end
 return result
end
local function className(account)
 local ok,label=pcall(tableWork,"CLASTEXT",function(t)
  local _,height=t:getDimensions()
  for i=0,height-1 do
   local row=t:getRowLabel(i)
   if tonumber(t:getAtLabels("CLASSID",row))==account.oldClass and tonumber(t:getAtLabels("KITID",row))==16384 then
    return text(t:getAtLabels("MIXED",row),fallbackClasses[account.oldClass]or row)
   end
  end
  return fallbackClasses[account.oldClass]or"Old class"
 end)
 if ok then return label end
 -- A missing display label cannot invalidate earned class improvements.
 print("[CBM campaign XP] Old-class name unavailable in CLASTEXT; using a fallback label.")
 return fallbackClasses[account.oldClass]or"Old class"
end
function M.New(skillRows,hla)
 assert(skillRows and type(skillRows.Read)=="function"and hla and type(hla.Open)=="function",
  "Concrete native old skill and HLA providers required")
 local builder={}
 function builder.ValidateSkills(sprite,account,choices,beforeSkills)
  local changed=false;for _,choice in ipairs(choices.skills)do if choice.delta>0 then changed=true end end
  if not changed then return true end
  local current=skillRows.Read(sprite,account)
  for _,choice in ipairs(choices.skills)do
   local row=current[choice.id+1]
   assert(row and row.id==choice.id and choice.delta>=0 and choice.delta%1==0,"Invalid owned old skill choice")
   assert(row.value==beforeSkills[choice.id+1],"Old skill basis changed; reopen the choices")
   if choice.delta>0 then
    assert(row.percentage>0 and row.value+choice.delta<=row.limit,"Installed old skill eligibility changed; reopen the choices")
   end
  end
  return true
 end
 function builder.Build(sprite,account,target,rules,manual)
  local plan,why=rules.Plan(sprite,account);assert(plan,why)
  assert(plan.oldLevel==account.oldLevel and plan.target==target,"Installed old progression changed")
  local beforeSkills=manual.ReadSkills(sprite)
  assert(type(beforeSkills)=="table"and #beforeSkills==7,"Complete native base-skill snapshot required")
  local prepared={className=className(account),oldLevel=account.oldLevel,target=target,
   profPoints=plan.profPoints,skillPoints=plan.skillPoints,proficiencies={},skills={}}
  if plan.profPoints>0 then
   prepared.proficiencies=tableWork("WEAPPROF",function(t)
    local _,height=t:getDimensions();local rows,seen={},{}
    for i=0,height-1 do
     local label=t:getRowLabel(i);local stat=tonumber(t:getAtLabels("ID",label))
     -- Only native weapon/style stat IDs belong to this allocation. Aliased
     -- rows have one owned value; retain the first installed display order.
     if stat and stat%1==0 and stat>=89 and stat<=134 and not seen[stat]then
      seen[stat]=true
      local limit,problem=rules.Cap(sprite,account,stat);assert(limit~=nil,problem)
      rows[#rows+1]={stat=stat,label=text(t:getAtLabels("NAME_REF",label),label),
       value=manual.ReadOld(sprite,stat),limit=limit}
     end
    end
    return rows
   end)
  end
  if plan.skillPoints>0 then
   for _,row in ipairs(skillRows.Read(sprite,account))do
    assert(beforeSkills[row.id+1]==row.value,"Native skill basis changed while preparing choices")
    if row.percentage>0 then
     prepared.skills[#prepared.skills+1]={id=row.id,label=text(row.nameStrref,"Skill "..tostring(row.id+1)),
      value=row.value,limit=row.limit}
    end
   end
  end
  -- Native catalog owns eligibility, including installed kit/alignment rules,
  -- previous markers and deferred choices. Row indexes are never saved alone.
  local view,problem=hla.Open(sprite,account,target);assert(view,problem)
  local function close()
   local done,why=view.Close();assert(done,why or"Native HLA catalog cleanup is uncertain")
   return true
  end
  local ok,result=pcall(function()
   assert(type(view.Close)=="function"and type(view.CanChoose)=="function","Incomplete native HLA catalog")
   prepared.hlaPoints=view.points;prepared.hlas={}
   for _,row in ipairs(view.rows)do
    assert(type(row.descriptor)=="table","Missing durable native HLA descriptor")
    prepared.hlas[#prepared.hlas+1]={id=row.id,label=row.label or text(row.descriptor.nameStrref,"High-level ability"),
     description=row.description or"",descriptor=row.descriptor}
   end
   prepared.canChooseHLA=view.CanChoose;prepared.onClose=close
   return prepared
  end)
  if not ok then close();error(result)end
  return result,beforeSkills
 end
 return builder
end
return M
