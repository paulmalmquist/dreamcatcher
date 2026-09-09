document.querySelector('#filters').addEventListener('submit',async e=>{
 e.preventDefault();const status=document.querySelector('#status'),target=document.querySelector('#results'),button=e.currentTarget.querySelector('button');
 button.disabled=true;status.textContent='Loading governed data…';target.replaceChildren();
 try{
  const response=await fetch('/api/dashboard',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(Object.fromEntries(new FormData(e.currentTarget)))});
  if(!response.ok)throw Error();const {rows,truncated}=await response.json();
  status.textContent=rows.length?`${rows.length} authorized rows${truncated?' · result capped':''}`:'No authorized records match your filters.';
  const table=document.createElement('table'),head=document.createElement('thead'),body=document.createElement('tbody'),header=document.createElement('tr'),fields=Object.keys(rows[0]??{});
  for(const field of fields){const th=document.createElement('th');th.scope='col';th.textContent=field;header.append(th)}head.append(header);
  for(const row of rows){const tr=document.createElement('tr');for(const field of fields){const td=document.createElement('td');td.textContent=String(row[field]??'—');tr.append(td)}body.append(tr)}
  table.append(head,body);target.append(table);
 }catch{status.textContent='Data unavailable. Check access, data freshness, or contact the data steward.'}
 finally{button.disabled=false}
});
