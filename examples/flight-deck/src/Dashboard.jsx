import React, {useEffect, useState} from 'react';
import {createRoot} from 'react-dom/client';

function Dashboard(){
 const [program,setProgram]=useState('program-a');
 const [rows,setRows]=useState([]),[error,setError]=useState(''),[busy,setBusy]=useState(true),[refresh,setRefresh]=useState(0);
 useEffect(()=>{
  const request=new AbortController();setBusy(true);setError('');setRows([]);
  fetch('/api/dashboard',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({program_id:program}),signal:request.signal})
   .then(async r=>{if(!r.ok)throw Error('Access unavailable. Launch again from Dreamcatcher or contact your app owner.');return r.json()})
   .then(data=>{setRows(data.rows);setBusy(false)})
   .catch(e=>{if(e.name!=='AbortError'){setError(e.message);setBusy(false)}});
  return()=>request.abort();
 },[program,refresh]);
 const readiness=rows.length?Math.round(rows.reduce((n,r)=>n+Number(r.readiness_pct),0)/rows.length):null;
 return <main>
  <header><span className="brand">dreamcatcher <span>/ flight deck</span></span><span className="badge">SYNTHETIC LAB</span></header>
  <section className="heading"><div><p className="eyebrow">MANUFACTURING / GOVERNED ANALYTICS</p><h1>Build readiness</h1><p>Assembly readiness for the programs you can access.</p></div>
   <div className="controls"><label>Program<select aria-label="Program" value={program} onChange={e=>setProgram(e.target.value)}><option value="program-a">Program A</option><option value="program-b">Program B</option></select></label><button onClick={()=>setRefresh(v=>v+1)}>Refresh data</button></div>
  </section>
  <div aria-live="polite">{busy?<p>Checking access and loading governed data…</p>:error?<p role="alert" className="error">{error}</p>:<>
   <section className="metrics"><article><span>Readiness</span><strong>{readiness===null?'—':readiness+'%'}</strong><p>Average across visible assemblies</p></article><article><span>Visible assemblies</span><strong>{rows.length}</strong><p>Only rows returned by the gateway</p></article><article><span>Data contract</span><strong className="contract">Assembly × program</strong><p>bq-build-readiness@1.0.0</p></article></section>
   <section className="table-card"><h2>Assembly detail</h2>{rows.length?<table><thead><tr><th>Assembly</th><th>System</th><th>Readiness</th><th>Observed</th></tr></thead><tbody>{rows.map(row=><tr key={row.assembly_id}><td>{row.assembly_id}</td><td>{row.system_name}</td><td><progress max="100" value={Number(row.readiness_pct)}/><span>{row.readiness_pct}%</span></td><td>{row.updated_at}</td></tr>)}</tbody></table>:<p>No authorized rows for this program.</p>}</section>
  </>}</div>
  <footer>DEMO DATA ONLY · No live BigQuery connection · App access and data access are independent</footer>
 </main>;
}
createRoot(document.getElementById('root')).render(<Dashboard/>);
