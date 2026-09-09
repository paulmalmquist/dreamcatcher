import {useCallback,useEffect,useState} from 'react';
import {Button} from '@/components/ui/button';
import {Input} from '@/components/ui/input';
import {Textarea} from '@/components/ui/textarea';
import {api,download,type Identity} from './api';

type Submission={id:string;version:string;status:string;source_digest:string;findings:string[]};
type Grant={subject:string;permission:string};
type Overview={revision:number;enabled:number;classification:string;submissions:Submission[];grants:Grant[];deployments:{id:string;status:string;environment:string;url:string|null}[]};
type Proposal={id:string;status:string;proposal:{summary:string;changes:{path:string;content:string}[]}|null};
type Agent={agent_id:string;submission_id:string;shared_skills:string[];changes:Proposal[]};

export function HostedRegistration({onCreated}:{onCreated:()=>Promise<void>}){
 const [busy,setBusy]=useState(false),[error,setError]=useState('');
 return <form className="upload-form hosted-registration" onSubmit={async e=>{
  e.preventDefault();const data=Object.fromEntries(new FormData(e.currentTarget));setBusy(true);setError('');
  try{await api('/v2/apps','POST',data);await onCreated()}catch(e){setError((e as Error).message)}finally{setBusy(false)}
 }}><h3>Or register a containerized app</h3><p className="muted">Create its private workspace, then upload source in the Release tab.</p>
 <label>Name<Input name="name" required maxLength={70}/></label>
 <label>Description<Textarea name="description" required maxLength={300}/></label>
 <label>Category<select name="category">{['Manufacturing','Supply chain','Test & launch','Data & AI'].map(c=><option key={c}>{c}</option>)}</select></label>
 <label>Sensitivity<select name="classification"><option value="internal">Internal · explicit app access</option><option value="restricted">Restricted · explicit reviewer access too</option></select></label>
 <Button className="primary-button" disabled={busy}>{busy?'Creating…':'Create hosted app'}</Button>{error&&<p role="alert" className="form-error">{error}</p>}</form>;
}

export function HostedPanel({appId,user,onChange}:{appId:string;user:Identity;onChange:()=>Promise<void>}){
 const [data,setData]=useState<Overview|null>(null),[agent,setAgent]=useState<Agent|null>(null),[grants,setGrants]=useState('[]');
 const [error,setError]=useState(''),[busy,setBusy]=useState(false),[prompt,setPrompt]=useState(''),[version,setVersion]=useState('1.0.1'),[developerToken,setDeveloperToken]=useState('');
 const refresh=useCallback(async()=>{
  const [overview,context]=await Promise.all([api<Overview>(`/v2/apps/${appId}/overview`),api<Agent>(`/v2/apps/${appId}/agent`).catch(()=>null)]);
  setData(overview);setGrants(JSON.stringify(overview.grants,null,2));setAgent(context);
 },[appId]);
 useEffect(()=>{let current=true;setData(null);setAgent(null);setDeveloperToken('');setError('');
  Promise.all([api<Overview>(`/v2/apps/${appId}/overview`),api<Agent>(`/v2/apps/${appId}/agent`).catch(()=>null)])
   .then(([overview,context])=>{if(current){setData(overview);setGrants(JSON.stringify(overview.grants,null,2));setAgent(context)}})
   .catch(e=>{if(current)setError(e.message)});return()=>{current=false};
 },[appId]);
 async function action(work:()=>Promise<unknown>){setBusy(true);setError('');try{await work();await refresh();await onChange()}catch(e){setError((e as Error).message)}finally{setBusy(false)}}
 const base=`/v2/apps/${appId}`;
 return <div className="hosted-panel">{error&&<p role="alert" className="form-error">{error}</p>}
 {!data?<p className="muted">App owners, editors, or authorized reviewers can manage releases here.</p>:<>
 <div className="contract-banner"><strong>Container control plane</strong><p>Source is never executed here. Builds and deployments wait for trusted workers; approval is a separate human action.</p><code>{appId}</code></div>
 <div className="release-buttons"><Button variant="outline" disabled={busy} onClick={()=>action(refresh)}>Refresh status</Button>
 <Button variant="outline" disabled={busy} onClick={()=>action(()=>api(`${base}/${data.enabled?'suspend':'resume'}`,'POST'))}>{data.enabled?'Suspend app':'Resume app'}</Button></div>
 <label>Upload source ZIP (up to 8 MiB)<Input type="file" accept=".zip" disabled={busy} onChange={e=>{const file=e.target.files?.[0];if(!file)return;const form=new FormData();form.append('file',file);void action(()=>api(`${base}/submissions`,'POST',form));e.target.value=''}}/></label>
 {data.submissions.map(s=><article className="release-record" key={s.id}><div><strong>v{s.version}</strong><span className="badge">{s.status}</span></div><code title={s.source_digest}>Source {s.source_digest.slice(0,20)}…</code>
 {s.findings.map(f=><p className="finding" key={f}>{f}</p>)}<div className="release-buttons">
 <Button variant="outline" disabled={busy} onClick={()=>action(()=>download(`${base}/submissions/${s.id}/source`,`source-${s.version}.zip`))}>Export source</Button>
 {['admin','reviewer'].includes(user.role)&&<Button variant="outline" disabled={busy||s.status!=='built'||s.findings.length>0} onClick={()=>action(()=>api(`${base}/submissions/${s.id}/approve`,'POST'))}>Approve</Button>}
 <Button variant="outline" disabled={busy||!['built','approved'].includes(s.status)||s.findings.length>0} onClick={()=>action(()=>api(`${base}/submissions/${s.id}/deploy`,'POST',{environment:'preview'}))}>Private preview</Button>
 <Button className="primary-button" disabled={busy||s.status!=='approved'||s.findings.length>0} onClick={()=>action(()=>api(`${base}/submissions/${s.id}/deploy`,'POST',{environment:'production'}))}>Promote</Button>
 {['admin','reviewer'].includes(user.role)&&<Button variant="outline" disabled={busy||s.status==='revoked'} onClick={()=>action(()=>api(`${base}/submissions/${s.id}/revoke`,'POST'))}>Revoke</Button>}
 </div></article>)}
 <h3>Deployments</h3>{data.deployments.length?data.deployments.map(d=><p key={d.id}>{d.environment} · {d.status}{d.url&&d.status==='ready'&&<> · <a href={d.url} target="_blank" rel="noopener noreferrer">Open authenticated app</a></>}</p>):<p className="muted">No deployment has been requested.</p>}
 <h3>Sharing capabilities</h3><p className="muted">discover, use, edit, deploy, share, and review are separate. App access never grants data access. Saving replaces the complete grant list.</p>
 <label>Grants (JSON)<Textarea className="json-editor" value={grants} onChange={e=>setGrants(e.target.value)}/></label><p className="muted">Example: {JSON.stringify({subject:'group:Manufacturing',permission:'use'})}</p>
 <Button variant="outline" disabled={busy} onClick={()=>action(()=>api(`${base}/grants`,'PUT',{expected_revision:data.revision,grants:JSON.parse(grants)}))}>Save capabilities</Button>
 <h3>App maintainer</h3>{agent?<><p className="muted">Stable agent {agent.agent_id.slice(0,12)} · {agent.shared_skills.join(', ')}</p>
 <label>UI change request<Textarea value={prompt} onChange={e=>setPrompt(e.target.value)} placeholder="Add an assembly filter without changing query permissions" maxLength={6000}/></label>
 <Button className="primary-button" disabled={busy||prompt.length<5} onClick={()=>action(()=>api(`${base}/agent/changes`,'POST',{submission_id:agent.submission_id,prompt,component:''}))}>Request proposed change</Button>
 <p className="muted">A configured model worker proposes UI-only changes. It cannot alter authentication, SQL permissions, or deployments.</p>
 <label>Candidate version<Input value={version} onChange={e=>setVersion(e.target.value)} pattern="[0-9]+\.[0-9]+\.[0-9]+"/></label>
 {agent.changes.map(change=><article className="release-record" key={change.id}><strong>{change.status}</strong>{change.proposal&&<><p>{change.proposal.summary}</p>{change.proposal.changes.map(file=><details key={file.path}><summary>{file.path}</summary><pre className="result-json">{file.content}</pre></details>)}<Button disabled={busy||change.status!=='proposed'} onClick={()=>action(()=>api(`${base}/agent/changes/${change.id}/candidate`,'POST',{version}))}>Create candidate for a new build</Button></>}</article>)}</>:<p className="muted">The first source upload provisions its maintainer context.</p>}
 <h3>CLI handoff</h3><p className="muted">A one-hour token for this app’s upload and inspection commands only. Keep it in your terminal, never in source or the deployed app.</p>
 <Button variant="outline" disabled={busy} onClick={()=>action(async()=>{const r=await api<{token:string}>(`${base}/developer-token`,'POST');setDeveloperToken(r.token)})}>Create developer token</Button>
 {developerToken&&<><pre className="result-json">{developerToken}</pre><Button variant="outline" onClick={()=>setDeveloperToken('')}>Hide token</Button></>}
 </> }</div>;
}

type Product={source:string;owner:string;revision:number;classification:string;grain:string[];observation:{expires:number}|null};
export function DataProducts(){
 const [rows,setRows]=useState<Product[]>([]),[error,setError]=useState('');
 useEffect(()=>{let active=true;api<Product[]>('/v2/data-products').then(v=>{if(active)setRows(v)}).catch(e=>{if(active)setError(e.message)});return()=>{active=false}},[]);
 return <section className="data-products"><h2>Certified data products</h2><p className="muted">Exact BigQuery views, accountable owners, output grain, and time-bounded security observations. A registered name alone is not proof.</p>
 {error&&<p className="form-error" role="alert">{error}</p>}{rows.map(p=><article className="release-record" key={p.source}><strong>{p.source}</strong><p>Revision {p.revision} · {p.classification} · Grain: {p.grain.join(', ')}</p><p>{p.owner}</p><span className="badge">{p.observation&&p.observation.expires>Date.now()/1000?'Recent worker observation':'Fresh observation required'}</span></article>)}
 {!rows.length&&!error&&<p>No certified BigQuery sources are visible yet. Connect your work catalog using integrations/CONNECTIONS.json.</p>}</section>;
}
