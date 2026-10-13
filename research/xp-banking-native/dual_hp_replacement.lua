-- Uninstalled, detached HP reconciliation. No engine call or actor mutation.
-- Receipts are native BASE-roll contributions. Never add CON bonuses here.
local M={}
local function int(n,lo,hi,what)
 assert(type(n)=="number" and n==math.floor(n) and n>=lo and n<=hi,"Invalid "..what);return n
end
local function samples(rows,what)
 assert(type(rows)=="table","Missing "..what)
 local out={};local last=0
 for _,r in ipairs(rows)do
  local level=int(r.level,1,255,what.." level")
  local hp=int(r.contribution or r.hp or r.rolledHP or r.rolled_hp,1,2147483647,what.." contribution")
  assert(level>last,"Unordered/duplicate "..what);last=level;out[level]=hp
 end
 return out
end
-- Only the caller's coherent owner/session ledger may supply these samples.
-- activeThrough is the ACTUAL active level, not XP-implied potential level.
-- afterOld must equal the actual manually selected target. prior replacements
-- are forbidden by beforeOld plus unique contiguous native old samples.
function M.Plan(beforeOld,afterOld,activeThrough,oldRolls,activeRolls)
 int(beforeOld,1,255,"old current level");int(afterOld,beforeOld,255,"old selected level")
 int(activeThrough,1,255,"active current level")
 local old,active=samples(oldRolls,"old rolls"),samples(activeRolls,"active rolls")
 local result={schema=1,policy="replace_active_with_old",fromLevel=beforeOld,toLevel=afterOld,
  signedEncoding="uint32_twos_complement",deltaBaseHPBits=0,replacements={}}
 local total=0
 for level in pairs(old)do assert(level>beforeOld and level<=afterOld,"Old sample outside selected interval")end
 for level=beforeOld+1,afterOld do
  assert(old[level],"Missing exact native old-class contribution")
  local removed=0
  if level<=activeThrough then
   assert(active[level],"Missing exact owned overlapping active contribution")
   removed=active[level]
  end
  local delta=old[level]-removed
  total=total+delta
  assert(total>=-2147483648 and total<=2147483647,"HP delta overflow")
  result.replacements[#result.replacements+1]={level=level,oldContribution=old[level],
   replacedActiveContribution=removed,deltaBits=delta%4294967296}
 end
 result.deltaBaseHPBits=total%4294967296
 return result
end
function M.Delta(plan)
 assert(plan.signedEncoding=="uint32_twos_complement","Unknown HP delta encoding")
 local n=int(plan.deltaBaseHPBits,0,4294967295,"HP delta bits")
 return n>=2147483648 and n-4294967296 or n
end
-- Native positive leveling adds the same gain to max and current HP. For a
-- negative replacement, preserve missing HP while keeping living actors alive.
-- Uses resulting DERIVED maximum supplied after normal recalculation; does not
-- infer it from base rolls or bypass unrelated HP effects/CON contributions.
function M.CurrentAfter(currentHP,delta,resultingMaximum)
 int(currentHP,-32768,32767,"native current HP")
 int(delta,-2147483648,2147483647,"base HP delta")
 int(resultingMaximum,1,32767,"resulting native maximum HP")
 if currentHP<=0 then return currentHP end
 return math.max(1,math.min(resultingMaximum,currentHP+delta))
end
return M
