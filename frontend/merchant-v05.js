/* GiftBridge v0.5 merchant ecosystem. Local sandbox, no real KYC or settlement. */
const gbMerchantRole = mid => merchantAccess.find(m => m.id === Number(mid));
const gbCanManage = mid => ['OWNER','MANAGER','ADMIN'].includes(gbMerchantRole(mid)?.role);
let gbBranches = [];
let gbReport = null;

async function loadMerchantApplications(){
  if(!token)return;
  try{
    const items=await api('/merchant/applications/my');
    $('myApplications').innerHTML=items.length?items.map(x=>`<div class="application-card"><div class="application-title"><strong>${esc(x.business_name)}</strong><span class="status-pill status-${esc(x.status.toLowerCase())}">${esc(x.status)}</span></div><p class="soft">${esc(x.category)} · ${esc(x.city)} · Submitted ${new Date(x.submitted_at).toLocaleDateString()}</p>${x.review_note?`<p class="review-note">Reviewer note: ${esc(x.review_note)}</p>`:''}${x.status==='APPROVED'?`<p class="success-copy">✓ Merchant approved. Sign out and back in to access the Merchant studio.</p>`:''}</div>`).join(''):'<div class="empty-state">No application yet. Submit the form to begin.</div>';
  }catch(e){notify(e.message,true);}
}
$('reloadApplications').onclick=loadMerchantApplications;
$('applyMerchantForm').onsubmit=e=>handleForm(e,async()=>{
  const result=await api('/merchant/applications','POST',{
    business_name:$('applyBusinessName').value.trim(),category:$('applyCategory').value,
    city:$('applyCity').value.trim(),contact_phone:$('applyContact').value.trim(),
    description:$('applyDescription').value.trim()
  });
  $('applyMerchantForm').reset();await loadMerchantApplications();
  notify(`✓ Application #${result.id} submitted successfully. An admin can review it in Management.`);
});

async function loadApplicationQueue(){
  if(user?.role!=='admin')return;
  try{
    const items=await api('/admin/applications');
    const pending=items.filter(x=>x.status==='PENDING');
    $('reviewQueue').innerHTML=items.length?items.map(a=>`<article class="application-card"><div class="application-title"><strong>#${a.id} ${esc(a.business_name)}</strong><span class="status-pill status-${esc(a.status.toLowerCase())}">${esc(a.status)}</span></div>
      <p class="soft">${esc(a.category)} · ${esc(a.city)} · ${esc(a.applicant_name)} (${esc(a.applicant_phone)})</p><p>${esc(a.description||'No description added')}</p>
      ${a.status==='PENDING'?`<div class="approval-actions"><button class="btn solid" onclick="reviewMerchantApplication(${a.id},'APPROVED')">✓ Approve</button><button class="btn outlined" onclick="reviewMerchantApplication(${a.id},'REJECTED')">Decline</button></div>`:`<p class="soft">${esc(a.review_note||'Reviewed · No additional note')}</p>`}</article>`).join(''):'<div class="empty-state">No merchant applications yet.</div>';
    $('reloadReviewQueue').textContent='↻ Refresh queue'+(pending.length?` (${pending.length} pending)`:'');
  }catch(e){notify(e.message,true);}
}
async function reviewMerchantApplication(id,decision){
  const note=decision==='REJECTED'?prompt('Enter a reason for declining this merchant application:'):prompt('Optional approval note (demo only):','');
  if(note===null|| (decision==='REJECTED'&&!note.trim()))return;
  try{
    const result=await api('/admin/applications/'+id+'/review','POST',{decision,note:note.trim()});
    notify(`${result.business_name}: ${decision==='APPROVED'?'approved':'declined'}.`);
    await refresh();await loadApplicationQueue();await loadAdmin();
  }catch(e){notify(e.message,true);}
}
$('reloadReviewQueue').onclick=loadApplicationQueue;

async function loadRedeemBranches(){
  const mid=Number($('redeemMerchant').value),access=gbMerchantRole(mid);
  if(!mid)return;
  try{
    const branches=await api('/branches?merchant_id='+mid);
    let eligible=branches;
    if(access?.role==='CASHIER'&&access.branch_id){eligible=branches.filter(b=>b.id===access.branch_id);}
    $('redeemBranch').innerHTML=`<option value="">${access?.role==='CASHIER'&&access.branch_id?'Choose assigned branch':'Unspecified (legacy / admin POS)'}</option>`+eligible.map(b=>`<option value="${b.id}">${esc(b.name)} · ${esc(b.city)}</option>`).join('');
    if(access?.role==='CASHIER'&&eligible.length===1)$('redeemBranch').value=eligible[0].id;
  }catch(e){notify(e.message,true);}
}
$('redeemMerchant').addEventListener('change',loadRedeemBranches);

function stopQrScanner(){
  scanLoopActive=false;
  if(scannerStream){scannerStream.getTracks().forEach(track=>track.stop());scannerStream=null;}
  const video=$('qrCamera');video.pause();video.srcObject=null;video.hidden=true;
  $('scanQrButton').textContent='▣ Scan customer QR';
}
async function startQrScanner(){
  if(scanLoopActive){stopQrScanner();return;}
  if(!('BarcodeDetector' in window)||!navigator.mediaDevices?.getUserMedia){
    notify('QR camera scanning is not supported here. Please type the card code manually.',true);return;
  }
  try{
    scannerStream=await navigator.mediaDevices.getUserMedia({video:{facingMode:'environment'}});
    const video=$('qrCamera');video.srcObject=scannerStream;video.hidden=false;await video.play();
    const detector=new BarcodeDetector({formats:['qr_code']});
    scanLoopActive=true;$('scanQrButton').textContent='Stop camera';
    $('scanHelp').textContent='Point the camera at the customer’s GiftBridge QR, then enter their one-time PIN.';
    const scan=async()=>{
      if(!scanLoopActive)return;
      try{
        const items=await detector.detect(video);
        const code=items.map(i=>i.rawValue).find(v=>v?.startsWith('GB-CARD:'));
        if(code){$('redeemCode').value=code.slice('GB-CARD:'.length);stopQrScanner();notify('✓ Gift code scanned. Ask the customer for their one-time PIN.');return;}
      }catch(e){console.warn('QR frame:',e.message);}
      if(scanLoopActive)requestAnimationFrame(scan);
    };requestAnimationFrame(scan);
  }catch(e){stopQrScanner();notify('Camera could not start: '+e.message,true);}
}
$('scanQrButton').onclick=startQrScanner;
window.addEventListener('pagehide',stopQrScanner);

async function loadMerchantTools(){
  if(!merchantAccess.length)return;
  const merchantId=Number($('merchantStudioSelect').value);
  const canManage=gbCanManage(merchantId);
  $('merchantOwnerArea').hidden=!canManage;
  if(!canManage)return;
  try{
    const [report,team,branches]=await Promise.all([
      api('/merchant/report?merchant_id='+merchantId+'&days='+Number($('reportDays').value)),
      api('/merchant/team?merchant_id='+merchantId),api('/branches?merchant_id='+merchantId)
    ]);
    gbReport=report;gbBranches=branches;
    $('merchantReportMetrics').innerHTML=[
      ['Issued merchant gifts',money(report.merchant_specific_sales_etb)],
      ['Gross redeemed',money(report.redeemed_etb)],
      ['Demo fees',money(report.fee_etb)],
      ['Demo payable',money(report.estimated_payable_etb)]
    ].map(([k,v])=>`<div class="metric">${esc(k)}<strong>${esc(v)}</strong></div>`).join('');
    const max=Math.max(1,...report.daily.map(x=>x.redeemed_etb));
    $('merchantDailyChart').innerHTML=report.daily.length?report.daily.map(x=>`<div class="day-bar" title="${esc(x.date)} · ${money(x.redeemed_etb)}"><span class="bar-date">${esc(x.date.slice(5))}</span><span class="bar-track"><span class="bar-fill" style="width:${Math.max(2,100*x.redeemed_etb/max)}%"></span></span><strong>${money(x.redeemed_etb)}</strong></div>`).join(''):'<p class="soft">No redemptions in this period yet.</p>';
    $('merchantBranchReport').innerHTML=report.branches.length?report.branches.map(x=>`<div class="line"><strong>${esc(x.branch)}</strong> · ${x.transactions} redemption(s) <span class="row-amount">${money(x.redeemed_etb)}</span></div>`).join(''):'<p class="soft">No branch activity yet.</p>';
    const role=gbMerchantRole(merchantId)?.role;
    $('merchantTeamList').innerHTML=team.length?team.map(t=>`<div class="team-row"><div><strong>${esc(t.name)}</strong> <span class="soft">${esc(t.role)}</span><br><small>${esc(t.phone)}${t.branch?' · '+esc(t.branch):''}</small></div>${t.role==='OWNER'?'<span class="status-pill status-approved">Owner</span>':`<button class="btn outlined" onclick="changeMerchantTeam(${t.id},${!t.active})">${t.active?'Deactivate':'Reactivate'}</button>`}</div>`).join(''):'<p class="soft">No team members yet.</p>';
    $('merchantStaffBranch').innerHTML=branches.map(b=>`<option value="${b.id}">${esc(b.name)} · ${esc(b.city)}</option>`).join('');
    [...$('merchantStaffRole').options].find(o=>o.value==='MANAGER').hidden=role==='MANAGER';
    if(role==='MANAGER')$('merchantStaffRole').value='CASHIER';
  }catch(e){notify(e.message,true);}
}
$('merchantStudioSelect').addEventListener('change',loadMerchantTools);
$('reportDays').onchange=loadMerchantTools;
$('merchantNewBranchForm').onsubmit=e=>handleForm(e,async()=>{
  await api('/merchant/branches','POST',{merchant_id:Number($('merchantStudioSelect').value),name:$('merchantBranchName').value,city:$('merchantBranchCity').value});
  $('merchantBranchName').value='';notify('✓ Branch added.');await loadMerchant();await loadMerchantTools();
});
$('merchantNewProgramForm').onsubmit=e=>handleForm(e,async()=>{
  const p=await api('/merchant/programs','POST',{merchant_id:Number($('merchantStudioSelect').value),
    name:$('merchantGiftName').value,category:$('merchantGiftCategory').value,
    description:$('merchantGiftDescription').value,emoji:$('merchantGiftEmoji').value});
  notify('✓ '+p.name+' published in GiftBridge demo.');$('merchantGiftName').value='';await refresh();await loadMerchantTools();
});
$('merchantStaffRole').onchange=()=>{$('merchantStaffBranch').disabled=$('merchantStaffRole').value==='MANAGER';};
$('merchantTeamForm').onsubmit=e=>handleForm(e,async()=>{
  const role=$('merchantStaffRole').value;
  await api('/merchant/team','POST',{merchant_id:Number($('merchantStudioSelect').value),
    user_phone:$('merchantStaffPhone').value.trim(),role,
    branch_id:role==='CASHIER'?Number($('merchantStaffBranch').value):null});
  $('merchantStaffPhone').value='';notify('✓ Staff member assigned. They can sign in to use their permissions.');await loadMerchantTools();
});
async function changeMerchantTeam(id,active){
  try{await api('/merchant/team/'+id,'PATCH',{active});notify(active?'Team member reactivated.':'Team member deactivated.');await loadMerchantTools();}catch(e){notify(e.message,true);}
}
