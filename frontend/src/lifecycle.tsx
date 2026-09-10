import {useState} from 'react';
import {Button} from '@/components/ui/button';
import {Input} from '@/components/ui/input';
import {api} from './api';

export type LifecyclePolicy={support_contact:string;review_due:number;profile:string;queries_per_minute:number;min_refresh_seconds:number;revision:number};
export function LifecycleEditor({appId,policy,canShare,onChange}:{appId:string;policy:LifecyclePolicy|null;canShare:boolean;onChange:()=>Promise<void>}){
 const [busy,setBusy]=useState(false),[error,setError]=useState('');
 const save: React.FormEventHandler<HTMLFormElement> = async event => {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  setBusy(true); setError('');
  try {
   await api(`/v2/apps/${appId}/lifecycle`, 'PUT', {
    support_contact: form.get('contact'),
    review_due: Date.parse(String(form.get('due')) + 'T23:59:59Z') / 1000,
    profile: form.get('profile'), queries_per_minute: Number(form.get('rpm')),
    min_refresh_seconds: Number(form.get('refresh')), expected_revision: policy?.revision ?? 0,
   });
   await onChange();
  } catch (error) { setError((error as Error).message); }
  finally { setBusy(false); }
 };
 return <details className="release-record"><summary>Ownership, review deadline & query limits</summary><p className="muted">An overdue review blocks runtime access. Production requires lifecycle policy. Saving invalidates existing app sessions.</p>{!canShare?<p>Only an app owner or someone with share permission can change this policy.</p>:<form key={policy?.revision??0} className="upload-form" onSubmit={save}><label>Support contact<Input name="contact" required minLength={3} maxLength={200} defaultValue={policy?.support_contact??''}/></label><label>Review due (UTC)<Input type="date" name="due" required defaultValue={policy?new Date(policy.review_due*1000).toISOString().slice(0,10):''}/></label><label>Runtime profile<select aria-label="Runtime profile" name="profile" defaultValue={policy?.profile??'custom-backend'}><option value="custom-backend">Custom backend</option><option value="standard-dashboard">Standard dashboard · trusted runtime verification required</option></select></label><label>App query requests per minute<Input type="number" min={1} max={1000} name="rpm" defaultValue={policy?.queries_per_minute??120}/></label><label>Minimum refresh interval (seconds)<Input type="number" min={0} max={3600} name="refresh" defaultValue={policy?.min_refresh_seconds??0}/></label><Button disabled={busy} variant="outline">Save lifecycle policy</Button></form>}{error&&<p role="alert" className="form-error">{error}</p>}</details>;
}

export function AnalyticalReviewForm({appId,submissionId,onChange}:{appId:string;submissionId:string;onChange:()=>Promise<void>}){
 const [busy,setBusy]=useState(false),[error,setError]=useState('');
 const recordReview: React.FormEventHandler<HTMLFormElement> = async event => {
  event.preventDefault();
  const form = Object.fromEntries(new FormData(event.currentTarget));
  setBusy(true); setError('');
  try {
   await api(`/v2/apps/${appId}/submissions/${submissionId}/analytical-review`, 'POST', form);
   await onChange();
  } catch (error) { setError((error as Error).message); }
  finally { setBusy(false); }
 };
 return <details className="release-record"><summary>Record independent analytical review</summary><p className="muted">Review grain, joins, units, filters, empty/partial data, and golden results against SME-approved metrics. This records your review; it does not run or certify a test automatically.</p><form className="upload-form" onSubmit={recordReview}><label>Retained golden-test evidence URI<Input name="evidence_uri" required placeholder="gs://company-evidence/review.json" maxLength={1000}/></label><label>Evidence SHA-256<Input name="evidence_sha256" required pattern="[a-f0-9]{64}" maxLength={64}/></label><Button disabled={busy} variant="outline">Record reviewed evidence</Button></form>{error&&<p role="alert" className="form-error">{error}</p>}</details>;
}
