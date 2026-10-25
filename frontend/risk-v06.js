// GiftBridge v0.6 — operations console (local demonstration only)
'use strict';
async function loadRiskOps(){
  if(user?.role!=='admin')return;
  try{
    const [recon,activity,alerts]=await Promise.all([
      api('/admin/reconciliation'), api('/admin/payment-activity'), api('/admin/fraud-alerts')]);
    $('riskSummary').innerHTML=[
      ['Reconciliation',recon.result],
      ['Outstanding demo gifts',money(recon.outstanding_etb)],
      ['Ledger liability',money(recon.ledger_liability_etb)],
      ['Open fraud alerts',alerts.filter(a=>a.status==='OPEN').length]
    ].map(([key,val])=>`<div class="metric">${esc(key)}<strong>${esc(val)}</strong></div>`).join('');
    $('reconFindings').innerHTML=recon.findings.length
      ?`<div class="ops-warning"><strong>✕ Reconciliation requires investigation</strong>${recon.findings.map(f=>`<p>${esc(f)}</p>`).join('')}</div>`
      :'<div class="ops-success"><strong>✓ Demo ledger reconciles</strong><p>Issued value = redeemed + outstanding; paid orders have issued cards; events balance to zero.</p></div>';
    $('paymentActivity').innerHTML=activity.length?activity.slice(0,15).map(a=>`<div class="ops-item">
      <strong>${esc(a.order_code)} · ${money(a.amount_etb)}</strong><br>
      <span class="soft">${esc(a.provider)} · ${esc(a.status)} · ${esc(a.reference)}</span></div>`).join('')
      :'<p class="soft">No v0.6 payment intents yet. Legacy v0.5 payments remain in the original order history.</p>';
    $('fraudQueue').innerHTML=alerts.length?alerts.map(a=>`<article class="ops-item">
      <strong>${esc(a.control_id)} · ${esc(a.title)}</strong><br><small>${esc(a.severity)} · ${esc(a.status)}</small>
      <p class="soft">${esc(a.detail)}</p>
      ${a.note?`<p class="soft">Review: ${esc(a.note)}</p>`:''}
      <div class="ops-actions">
       ${a.status==='OPEN'?`<button class="btn outlined" onclick="reviewGiftAlert(${a.id},'INVESTIGATING')">Investigate</button>`:''}
       ${!['RESOLVED','FALSE_POSITIVE'].includes(a.status)?`<button class="btn outlined" onclick="reviewGiftAlert(${a.id},'RESOLVED')">Resolve</button><button class="btn outlined" onclick="reviewGiftAlert(${a.id},'FALSE_POSITIVE')">False positive</button>`:''}
      </div></article>`).join(''):'<p class="soft">No fraud alerts. Large-value gifts or repeat failures can generate demo alerts.</p>';
  }catch(error){notify('Risk center: '+error.message,true);}
}
async function reviewGiftAlert(id,status){
  const note=status==='INVESTIGATING'?'Review started':prompt('Enter the resolution reason (required):');
  if(note===null||!note.trim())return;
  try{await api('/admin/fraud-alerts/'+id+'/review','POST',{status,note:note.trim()});
    notify('Risk case updated.');await loadRiskOps();}
  catch(error){notify(error.message,true);}
}
$('refreshRisk').onclick=loadRiskOps;
