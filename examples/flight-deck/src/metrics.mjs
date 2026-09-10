/** Demonstration metric contract: unweighted mean, one assembly × program row.
 * WORK-CONNECT: replace with SME-approved semantics and golden cases at work.
 */
export function summarizeReadiness(rows,truncated=false){
 if(truncated)throw Error('Partial results cannot certify a dashboard total. Refine the governed query.');
 const keys=new Set();let sum=0;
 for(const row of rows){
  if(!row.assembly_id||!row.program_id)throw Error('Missing assembly × program key');
  const key=JSON.stringify([row.program_id,row.assembly_id]);
  if(keys.has(key))throw Error('Duplicate assembly × program grain');keys.add(key);
  const value=row.readiness_pct;
  if(typeof value!=='number'||!Number.isFinite(value)||value<0||value>100)throw Error('Readiness must be a number in percent units (0–100)');
  sum+=value;
 }
 return {visibleAssemblies:rows.length,readiness:rows.length?Math.round(sum/rows.length):null};
}
