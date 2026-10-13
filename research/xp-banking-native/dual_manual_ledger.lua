-- Completed semantic reward history, not a rollback recipe. No engine calls.
-- Fixed packet schema plus printable lossless integers keeps long campaigns
-- within the real marshal field budget without trimming earned records.
local M={}
local skills={"m_lockPickingBase","m_trapsBase","m_pickPocketBase","m_moveSilentlyBase",
 "m_hideInShadowsBase","m_detectIllusionBase","m_setTrapsBase"}
local MAX=9007199254740991
local function uint(n)
 assert(type(n)=="number"and n>=0 and n<=MAX and n%1==0,"Invalid ledger integer")
 local out={}
 repeat local digit=n%32;n=math.floor(n/32);out[#out+1]=string.char(33+digit+(n>0 and 32 or 0))until n==0
 return table.concat(out)
end
local function encode(value)
 local kind=type(value)
 if kind=="boolean"then return value and"t"or"f"end
 if kind=="number"then return(value<0 and"-"or"+")..uint(math.abs(value))end
 if kind=="string"then assert(not value:find("\0",1,true),"NUL in ledger text");return"s"..uint(#value)..value end
 assert(kind=="table"and getmetatable(value)==nil,"Unsupported ledger value")
 local count=0;for _ in pairs(value)do count=count+1 end
 if count==#value then
  local out={"a",uint(count)};for i=1,count do assert(value[i]~=nil,"Sparse ledger array");out[#out+1]=encode(value[i])end
  return table.concat(out)
 end
 local keys={};for k in pairs(value)do assert(type(k)=="string","Ledger map requires named fields");keys[#keys+1]=k end
 table.sort(keys);local out={"m",uint(#keys)}
 for _,k in ipairs(keys)do out[#out+1]=encode(k);out[#out+1]=encode(value[k])end
 return table.concat(out)
end
local function decode(text)
 assert(type(text)=="string","Packed ledger text required");local at=1
 local function take()
  local n,m=0,1
  for _=1,11 do
   local c=text:byte(at);assert(c and c>=33 and c<=96,"Malformed ledger integer");at=at+1;c=c-33
   n=n+(c%32)*m;assert(n<=MAX,"Ledger integer overflow")
   if c<32 then return n end;m=m*32
  end
  error("Truncated ledger integer")
 end
 local read
 read=function(depth)
  assert(depth<=16,"Ledger nesting overflow");local tag=text:sub(at,at);at=at+1
  if tag=="t"then return true elseif tag=="f"then return false end
  if tag=="+"then return take()elseif tag=="-"then return-take()end
  if tag=="s"then local n=take();assert(at+n-1<=#text,"Truncated ledger string");local s=text:sub(at,at+n-1);at=at+n;return s end
  assert(tag=="a"or tag=="m","Unknown ledger value")
  local n=take();assert(n<=#text,"Malformed ledger count");local out={}
  for i=1,n do if tag=="a"then out[i]=read(depth+1)else
   local k=read(depth+1);assert(type(k)=="string"and out[k]==nil,"Invalid ledger map key");out[k]=read(depth+1)
  end end
  return out
 end
 local result=read(1);assert(at==#text+1,"Unexpected ledger tail");return result
end
local function skillValues(state)
 local result={};for _,name in ipairs(skills)do result[#result+1]=assert(state.skills[name],"Missing native base skill")end
 return result
end
local function stateSummary(s)return{assert(s.class),assert(s.kit),assert(s.flags),assert(s.levels),assert(s.maxHPBase)}end
local function deltas(rows,key)
 local result={};for _,r in ipairs(rows)do if r.delta~=0 then result[#result+1]={r[key],r.delta}end end;return result
end
local function choices(rows)
 -- Repeated +/- clicks are intent history, not additional earned rewards.
 -- Preserve first basis and final accepted value for each class/stat bucket.
 local result,seen={},{}
 for _,r in ipairs(rows)do
  local key=table.concat({r.stat,r.inactive and 1 or 0,r.screenMode or 0,r.selectedClass or 0},":")
  local old=seen[key]
  if old then old[5]=r.requested;old[7]=r.after else
   old={r.stat,r.inactive,r.screenMode or 0,r.selectedClass or 0,r.requested,r.before,r.after};seen[key]=old;result[#result+1]=old
  end
 end
 return result
end
local function retired(r)
 if not r then return false end
 local a,c=r.account,r.choices
 return{a.oldClass,a.activeClass,a.oldKit,a.oldLevel,r.target,a.oldUsableXP,a.activeUsableXP,
  deltas(c.proficiencies,"stat"),deltas(c.skills,"id"),c.hlas,r.hp.total,r.hp.encoded,r.beforeSkills,
  c.unusedProfPoints,c.unusedSkillPoints,c.unusedHlaPoints,r.hlasEnqueued==true}
end
function M.Preview(s)
 -- The pending BEFORE contains full effect evidence. Native transaction code
 -- owns exact effect-node rollback; the preview needs only reward observations.
 return{class=s.class,kit=s.kit,flags=s.flags,levels=s.levels,maxHPBase=s.maxHPBase,
  skills=s.skills,legacyProficiencies=s.legacyProficiencies,proficiencies=s.proficiencies}
end
function M.Append(container,receipt)
 assert(receipt.stage=="committed"and receipt.ownerKey,"Completed native receipt required")
 local ledger=container.manualLedger
 if not ledger then ledger={schema=1,ownerKey=receipt.ownerKey,records={}};container.manualLedger=ledger end
 assert(ledger.schema==1 and ledger.ownerKey==receipt.ownerKey,"Completed reward ledger owner/schema changed")
 ledger.owners=ledger.owners or{}
 local ownerIndex
 for i,owner in ipairs(ledger.owners)do if owner==receipt.ownerKey then ownerIndex=i;break end end
 if not ownerIndex then ledger.owners[#ledger.owners+1]=receipt.ownerKey;ownerIndex=#ledger.owners end
 local hp=receipt.hp;local samples={};for _,s in ipairs(hp.samples)do samples[#samples+1]={s.level,s.hp}end
 local packet={3,receipt.session,receipt.incarnation,receipt.ledgerRevision,stateSummary(receipt.before),stateSummary(receipt.after),
  {hp.total,hp.cached==true,hp.beforeLevels,hp.afterLevels,samples},choices(receipt.choices),
  {skillValues(receipt.before),skillValues(receipt.preview),skillValues(receipt.after)},retired(receipt.retired),receipt.oldHLA or false,ownerIndex}
 local packed=encode(packet)
 if #packed>60000 then local parts={};for i=1,#packed,60000 do parts[#parts+1]=packed:sub(i,i+59999)end;packed=parts end
 ledger.records[#ledger.records+1]=packed
 -- Only this latest full AFTER snapshot is diagnostic. It is superseded by
 -- the next pending BEFORE, never used as a class-allocation ownership recipe.
 container.lastManualSnapshot={schema=1,session=receipt.session,incarnation=receipt.incarnation,state=receipt.after}
 return #ledger.records
end
function M.Read(ledger,index)
 assert(ledger and ledger.schema==1 and ledger.ownerKey,"Unsupported reward ledger")
 local raw=assert(ledger.records[index],"Missing reward record");if type(raw)=="table"then raw=table.concat(raw)end
 local p=decode(raw);assert((p[1]==2 or p[1]==3)and #p==12,"Unsupported reward packet")
 local owner=p[1]==2 and p[12]or(ledger.owners and ledger.owners[p[12]])
 assert(type(owner)=="string"and #owner==32 and owner:match("^[0-9a-f]+$"),"Missing historical reward owner")
 local function summary(a)return{class=a[1],kit=a[2],flags=a[3],levels=a[4],maxHPBase=a[5]}end
 local h=p[7];local out={schema=2,stage="committed",ownerKey=owner,session=p[2],incarnation=p[3],ledgerRevision=p[4],
  before=summary(p[5]),after=summary(p[6]),hp={total=h[1],cached=h[2],beforeLevels=h[3],afterLevels=h[4],samples={}},choices={},
  baseSkills={before=p[9][1],preview=p[9][2],after=p[9][3]},oldHLA=p[11]or nil,
  proficiencyEvidence=p[10]and"scoped_class_basis"or"unpartitioned_native_observation",
  baseSkillEvidence="native_base_snapshots; explicit old choices are separately owned"}
 for _,s in ipairs(h[5])do out.hp.samples[#out.hp.samples+1]={level=s[1],hp=s[2]}end
 for _,r in ipairs(p[8])do out.choices[#out.choices+1]={stat=r[1],inactive=r[2],screenMode=r[3],selectedClass=r[4],requested=r[5],before=r[6],after=r[7]}end
 local r=p[10]
 if r then
  local selected={proficiencies={},skills={},hlas=r[10],unusedProfPoints=r[14],unusedSkillPoints=r[15],unusedHlaPoints=r[16]}
  for _,d in ipairs(r[8])do selected.proficiencies[#selected.proficiencies+1]={stat=d[1],delta=d[2]}end
  for _,d in ipairs(r[9])do selected.skills[#selected.skills+1]={id=d[1],delta=d[2]}end
  out.retired={schema=1,account={ownerKey=owner,incarnation=p[3],revision=p[4],oldClass=r[1],activeClass=r[2],oldKit=r[3],
   oldLevel=r[4],oldUsableXP=r[6],activeUsableXP=r[7],hasCleanReceipt=true},target=r[5],choices=selected,
   hp={total=r[11],encoded=r[12]},beforeSkills=r[13],hlasEnqueued=r[17]}
 end
 return out
end
return M
