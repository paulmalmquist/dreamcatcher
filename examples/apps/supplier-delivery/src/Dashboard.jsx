// SYNTHETIC dashboard. WORK-CONNECT: governed-query-gateway.
// Fetch from your same-origin authenticated backend, never directly from BigQuery.
export default function Dashboard({rows=[],loading=false,error=null}) {
  if (loading) return <p role="status">Loading governed data…</p>;
  if (error) return <p role="alert">Data is unavailable. Refresh your access or contact the data steward.</p>;
  return <section aria-label="Supplier Delivery"><h1>Supplier Delivery</h1>
    <p>Synthetic example · One row per po_line_id</p>
    <table><thead><tr><th scope="col">po_line_id</th><th scope="col">program_id</th><th scope="col">supplier_alias</th><th scope="col">days_late</th><th scope="col">updated_at</th></tr></thead>
    <tbody>{rows.map(row=><tr key={row.po_line_id}><td>{String(row.po_line_id ?? '—')}</td><td>{String(row.program_id ?? '—')}</td><td>{String(row.supplier_alias ?? '—')}</td><td>{String(row.days_late ?? '—')}</td><td>{String(row.updated_at ?? '—')}</td></tr>)}</tbody></table>
    {rows.length===0 && <p>No authorized records match your filters.</p>}
  </section>;
}
