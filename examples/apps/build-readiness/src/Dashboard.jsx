// SYNTHETIC dashboard. WORK-CONNECT: governed-query-gateway.
// Fetch from your same-origin authenticated backend, never directly from BigQuery.
export default function Dashboard({rows=[],loading=false,error=null}) {
  if (loading) return <p role="status">Loading governed data…</p>;
  if (error) return <p role="alert">Data is unavailable. Refresh your access or contact the data steward.</p>;
  return <section aria-label="Build Readiness"><h1>Build Readiness</h1>
    <p>Synthetic example · One row per assembly_id</p>
    <table><thead><tr><th scope="col">assembly_id</th><th scope="col">program_id</th><th scope="col">system_name</th><th scope="col">readiness_pct</th><th scope="col">updated_at</th></tr></thead>
    <tbody>{rows.map(row=><tr key={row.assembly_id}><td>{String(row.assembly_id ?? '—')}</td><td>{String(row.program_id ?? '—')}</td><td>{String(row.system_name ?? '—')}</td><td>{String(row.readiness_pct ?? '—')}</td><td>{String(row.updated_at ?? '—')}</td></tr>)}</tbody></table>
    {rows.length===0 && <p>No authorized records match your filters.</p>}
  </section>;
}
