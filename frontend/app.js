'use strict';
let token=sessionStorage.getItem('gb_token');
let user=JSON.parse(sessionStorage.getItem('gb_user')||'null');
let programList=[],merchantList=[],cashierMerchants=[],authMode='login',selectedOrder=null,workingPayment=false,selectedDesign='emerald',catalogFilter='ALL',merchantRows=[];
const $=id=>document.getElementById(id);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const money=n=>'ETB '+Number(n).toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2});
const makeKey=()=>globalThis.crypto?.randomUUID?.()||'GB-'+Math.random().toString(36).slice(2)+Date.now();
function notify(message,bad=false){$('notice').textContent=message;$('notice').classList.toggle('error',bad);}
async function api(path,method='GET',body){
  let response=await fetch('/api'+path,{method,headers:{'Content-Type':'application/json',...(token?{Authorization:'Bearer '+token}:{})},...(body!==undefined?{body:JSON.stringify(body)}:{})});
  let result=await response.json().catch(()=>({detail:'Unable to read server response'}));
  if(!response.ok){let detail=result.detail;throw Error(typeof detail==='string'?detail:JSON.stringify(detail||'Request failed'));}
  return result;
}
function setBusy(button,busy){button.disabled=busy;button.dataset.original??=button.textContent;button.textContent=busy?'Working...':button.dataset.original;}
async function handleForm(event,action){event.preventDefault();let button=event.submitter;try{if(button)setBusy(button,true);await action();}catch(error){notify(error.message,true);}finally{if(button)setBusy(button,false);}}
function showAuth(mode){authMode=mode;$('nameLabel').hidden=mode!=='register';$('loginTab').classList.toggle('active',mode==='login');$('registerTab').classList.toggle('active',mode==='register');$('authSubmit').textContent=mode==='login'?'Sign in →':'Create account →';}
$('loginTab').onclick=()=>showAuth('login');$('registerTab').onclick=()=>showAuth('register');
$('authForm').onsubmit=event=>handleForm(event,async()=>{
  if(authMode==='register'){
    await api('/auth/register','POST',{name:$('name').value,phone:$('phone').value,password:$('password').value});
    notify('Account created successfully! Please sign in.');showAuth('login');return;
  }
  const response=await api('/auth/login','POST',{phone:$('phone').value,password:$('password').value});
  token=response.access_token;user=response.user;sessionStorage.setItem('gb_token',token);sessionStorage.setItem('gb_user',JSON.stringify(user));
  await start();notify('Welcome back, '+user.name+'!');
});
function logout(){sessionStorage.removeItem('gb_token');sessionStorage.removeItem('gb_user');token=null;user=null;selectedOrder=null;$('auth').hidden=false;$('dashboard').hidden=true;$('logout').hidden=true;$('userChip').hidden=true;closeAllModals();notify('Signed out successfully.');}
$('logout').onclick=logout;
function tab(id){const b=document.querySelector(`[data-tab="${id}"]`);if(!b||b.hidden)return;document.querySelectorAll('[data-tab]').forEach(n=>n.classList.toggle('active',n===b));document.querySelectorAll('.view').forEach(n=>n.hidden=n.id!==id);if(id==='orders')loadOrders();if(id==='wallet')loadWallet();if(id==='admin')loadAdmin();if(id==='inbox')loadInbox();if(id==='merchant')loadMerchant();}
document.querySelectorAll('[data-tab]').forEach(b=>b.onclick=()=>tab(b.dataset.tab));
async function start(){
  if(!token)return;
  const me=await api('/me');user=me;sessionStorage.setItem('gb_user',JSON.stringify(me));
  $('auth').hidden=true;$('dashboard').hidden=false;$('logout').hidden=false;$('userChip').hidden=false;
  $('userChip').textContent=me.name+' · '+me.role;$('welcome').textContent='Hello, '+me.name.split(' ')[0]+' 👋';
  $('adminTab').hidden=me.role!=='admin';$('posTab').hidden=!['admin','merchant'].includes(me.role);$('merchantTab').hidden=!['admin','merchant'].includes(me.role);$('senderName').value=me.name;
  await refresh();
  if(['admin','merchant'].includes(me.role)){cashierMerchants=await api('/staff/merchants');renderCashierMerchants();}
  tab('shop');loadInbox().catch(()=>{});
}
async function refresh(){
  [programList,merchantList]=await Promise.all([api('/programs'),api('/merchants')]);
  $('program').innerHTML=programList.map(p=>`<option value="${p.id}">${esc(p.name)}</option>`).join('');
  renderPrograms();updatePreview();
  const picker=$('merchantPicker');picker.innerHTML=merchantList.map(m=>`<label class="merchant-choice"><input type="checkbox" value="${m.id}"> ${esc(m.name)} <small>#${m.id}</small></label>`).join('')||'<span class="soft">Create a merchant first.</span>';
  $('staffMerchant').innerHTML=merchantList.map(m=>`<option value="${m.id}">${esc(m.name)}</option>`).join('');
  $('branchMerchant').innerHTML=$('staffMerchant').innerHTML;
  renderStudioSelect();
  $('merchantDirectory').innerHTML=merchantList.map(m=>`<div class="line"><strong>#${m.id}</strong> · ${esc(m.name)}</div>`).join('')||'<span class="soft">No merchants available.</span>';
  renderCashierMerchants();
}
function renderCashierMerchants(){let source=user?.role==='admin'?merchantList:cashierMerchants;$('redeemMerchant').innerHTML=source.map(m=>`<option value="${m.id}">${esc(m.name)}</option>`).join('');}
function chooseProgram(id){tab('shop');$('program').value=id;updatePreview();$('buyPanel').scrollIntoView({behavior:'smooth'});}
function renderPrograms(){
  const search=$('searchPrograms').value.trim().toLowerCase();
  const filtered=programList.filter(p=>(catalogFilter==='ALL'||p.kind===catalogFilter) && (!search||p.name.toLowerCase().includes(search)));
  $('programs').innerHTML=filtered.length?filtered.map((p,i)=>`<article class="giftcard catalog-card ${p.kind==='UNIVERSAL'?'universal':''}"><div class="card-top"><span class="card-kicker">${p.kind==='UNIVERSAL'?'✦ THE UNIVERSAL EDITION':'✦ A FAVORITE PLACE'}</span><div class="catalog-symbol">${p.kind==='UNIVERSAL'?'✧':'❋'}</div><h4>${esc(p.name)}</h4><span class="card-kicker">${p.kind==='UNIVERSAL'?'ONE GIFT, SO MANY POSSIBILITIES':'THOUGHTFUL. PERSONAL. DIGITAL.'}</span></div><div class="card-content"><span class="badge">${p.accepted_merchant_ids.length} ${p.accepted_merchant_ids.length===1?'location':'participating merchants'}</span><p>${p.kind==='UNIVERSAL'?'Give them the freedom to choose across participating stores.':'A little happiness from a place they love.'}</p><button class="btn outlined wide" onclick="chooseProgram(${p.id})">Personalize this gift →</button></div></article>`).join(''):'<div class="empty-state">No gifts match your search. Try another category or merchant.</div>';
}
$('searchPrograms').addEventListener('input',renderPrograms);
document.querySelectorAll('.filter-chips [data-filter]').forEach(btn=>btn.onclick=()=>{catalogFilter=btn.dataset.filter;document.querySelectorAll('.filter-chips [data-filter]').forEach(b=>b.classList.toggle('selected',b===btn));renderPrograms();});
document.querySelectorAll('.design-option').forEach(btn=>btn.onclick=()=>{selectedDesign=btn.dataset.design;document.querySelectorAll('.design-option').forEach(b=>b.classList.toggle('selected',b===btn));updatePreview();});
for(const id of ['amount','occasion','recipient','senderName'])$(id).addEventListener('input',updatePreview);
function updatePreview(){
  const selected=programList.find(p=>p.id===Number($('program').value));const box=$('giftPreview');
  box.className='purchase-preview design-'+selectedDesign;
  box.innerHTML=`<span>✦ GIFTBRIDGE / ${esc($('occasion').options[$('occasion').selectedIndex]?.textContent||'GIFT')}</span><strong>${esc(selected?.name||'GiftBridge gift')}</strong><b>${money($('amount').value||0)}</b><small>From ${esc($('senderName').value||'Someone special')} · SANDBOX PREVIEW</small>`;
}
$('program').addEventListener('change',updatePreview);

$('buyForm').onsubmit=event=>handleForm(event,async()=>{
  const order=await api('/orders','POST',{program_id:Number($('program').value),amount_etb:$('amount').value,recipient_phone:$('recipient').value.trim()||null,message:$('giftMessage').value,occasion:$('occasion').value,design:selectedDesign,sender_name:$('senderName').value});
  showPayment(order);notify('Your gift is wrapped! Complete your simulated checkout.');
});
function openModal(id){$(id).hidden=false;document.body.style.overflow='hidden';}
function closeModal(id){$(id).hidden=true;if($('paymentModal').hidden&&$('successModal').hidden)document.body.style.overflow='';}
function closeAllModals(){closeModal('paymentModal');closeModal('successModal');}
$('closePayment').onclick=()=>closeModal('paymentModal');$('closeSuccess').onclick=()=>closeModal('successModal');
for(const id of ['paymentModal','successModal']){$(id).addEventListener('click',e=>{if(e.target===$(id)&&!workingPayment)closeModal(id);});}
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&!workingPayment)closeAllModals();});
function showPayment(order){
  selectedOrder=order;
  $('paymentBody').innerHTML=`<div class="modal-icon">🎁</div><span class="section-tag">SANDBOX CHECKOUT</span><h2 id="payTitle">Complete your gift</h2><p class="soft">This is a payment simulation. Choose a demo channel and simulate a success or a failure.</p>
  <div class="bill"><div><span>Order</span><strong>${esc(order.code)}</strong></div><div><span>Gift</span><strong>${esc(order.program)}</strong></div><div><span>For</span><strong>${esc(order.recipient)}</strong></div><div><span>Occasion</span><strong>${esc(order.occasion.replaceAll('_',' '))}</strong></div><div><span>Gift amount</span><strong>${money(order.amount_etb)}</strong></div></div>
  <label>Simulated payment method<select id="simChannel"><option>M-PESA (simulated)</option><option>telebirr (simulated)</option><option>Dashen Bank (simulated)</option><option>Bank card (simulated)</option></select></label>
  <div class="modal-actions" style="margin-top:20px"><button id="paySuccess" class="btn solid">✓ Simulate successful payment</button><button id="payFailed" class="btn outlined">Simulate failed payment</button></div>
  <p class="soft tiny center">No external API calls, real bank requests or charges.</p>`;
  $('paySuccess').onclick=()=>pay('SUCCESS');$('payFailed').onclick=()=>pay('FAILED');openModal('paymentModal');
}
async function pay(outcome){
  if(workingPayment||!selectedOrder)return;workingPayment=true;
  const successBtn=$('paySuccess'),failedBtn=$('payFailed');successBtn.disabled=failedBtn.disabled=true;
  try{
    const result=await api('/orders/'+selectedOrder.id+'/simulate-payment','POST',{outcome,channel:$('simChannel').value});
    closeModal('paymentModal');selectedOrder=null;
    await loadOrders();
    if(result.status==='PAID'){
      $('successBody').innerHTML=`<div class="success-mark">✓</div><h2 id="successTitle" class="center">Gift purchased successfully!</h2><p class="soft center">Your simulated payment succeeded. A digital gift has been delivered to <strong>${esc(result.recipient)}</strong> in their GiftBridge inbox and wallet.</p>
      <div class="bill"><div><span>Gift</span><strong>${esc(result.program)}</strong></div><div><span>Gift value</span><strong>${money(result.amount_etb)}</strong></div><div><span>Card code</span><strong>${esc(result.card_code)}</strong></div><div><span>Payment</span><strong>SIMULATED · SUCCESS</strong></div></div>
      <div class="modal-actions"><button class="btn solid" id="afterPayOrders">${result.recipient_phone===user.phone?'View my receipt →':'View purchase receipt →'}</button><button class="btn outlined" id="afterPayWallet">${result.recipient_phone===user.phone?'Open my wallet':'Open my wallet (gifts received)'}</button></div>`;
      $('afterPayWallet').onclick=()=>{closeModal('successModal');tab('wallet');};
      $('afterPayOrders').onclick=()=>{closeModal('successModal');tab('orders');};
      openModal('successModal');notify('Success! Gift card '+result.card_code+' issued.');
    }else{
      notify('Payment simulation failed. The order is saved but no gift was issued. You can retry it from My Orders.',true);tab('orders');
    }
  }catch(err){notify(err.message,true);}
  finally{workingPayment=false;if(successBtn?.isConnected)successBtn.disabled=false;if(failedBtn?.isConnected)failedBtn.disabled=false;}
}
async function loadOrders(){
  try{let orders=await api('/orders');$('orderList').innerHTML=orders.length?orders.map(o=>`<article class="order-row"><div><h4>${esc(o.program)} <span class="badge ${esc(o.status)}">${esc(o.status)}</span></h4><p>${esc(o.code)} · For ${esc(o.recipient)} · ${new Date(o.created_at).toLocaleString()}</p><strong>${money(o.amount_etb)}</strong><p>${esc(o.occasion.replaceAll('_',' '))} · ${esc(o.message||'A thoughtful gesture')}</p>${o.card_code?`<p>Gift card: <code>${esc(o.card_code)}</code></p>`:''}</div><div class="order-actions">${o.status==='PENDING'?`<button class="btn solid" onclick="payOrder(${o.id})">Complete checkout</button>`:''}${o.status==='FAILED'?`<button class="btn outlined" onclick="retryOrder(${o.id})">Retry payment</button>`:''}${o.status==='PAID'?'<span class="badge PAID">✓ Gift issued</span>':''}</div></article>`).join(''):'<div class="panel"><p class="soft">You have no orders yet. Visit the Gift Shop to buy your first gift.</p></div>';}catch(err){notify(err.message,true);}
}
async function payOrder(id){try{const o=await api('/orders/'+id);showPayment(o);}catch(err){notify(err.message,true);}}
async function retryOrder(id){try{const o=await api('/orders/'+id+'/retry','POST');showPayment(o);}catch(err){notify(err.message,true);}}
$('refreshOrders').onclick=loadOrders;
async function loadWallet(){
  try{
    const [cards,summary]=await Promise.all([api('/wallet'),api('/wallet/summary')]);
    $('walletCards').innerHTML=cards.length?cards.map(c=>`<article class="giftcard wallet-card"><div class="card-top design-${esc(c.design)}"><span class="card-kicker">✦ ${esc(c.kind.replace('_',' '))}</span><div><span class="wallet-occasion">${esc(c.occasion.replaceAll('_',' '))}</span><h4>${esc(c.program)}</h4><strong>${money(c.balance_etb)}</strong></div><span class="card-kicker">A GIFT FOR YOU</span></div><div class="card-content"><span class="badge ${esc(c.status)}">${esc(c.status.replaceAll('_',' '))}</span><p>From <strong>${esc(c.sender)}</strong> · Original ${money(c.original_etb)}</p><div class="card-code">${esc(c.code)}</div><div class="card-actions" style="margin-top:15px"><button class="btn solid" onclick="unwrapGift(${c.id})">Open gift ✨</button><button class="btn outlined" onclick="showRedemptionCode(${c.id})" ${c.balance_etb<=0?'disabled':''}>Redeem PIN</button><button class="btn outlined" onclick="sendGift(${c.id})" ${c.balance_etb<=0?'disabled':''}>Send</button><button class="btn outlined" onclick="showHistory(${c.id})">Activity</button></div></div></article>`).join(''):'<div class="empty-state"><span>🎁</span><h3>Your first gift is waiting to happen</h3><p>Shop for yourself or receive a thoughtful surprise from someone else.</p><button class="btn solid" id="emptyShop">Explore gifts →</button></div>';
    $('walletCards').dataset.total=summary.balance_etb;
    if($('emptyShop'))$('emptyShop').onclick=()=>tab('shop');
  }catch(err){notify(err.message,true);}
}
async function unwrapGift(id){
  try{
    const c=(await api('/wallet')).find(x=>x.id===id);if(!c)return;
    $('successBody').innerHTML=`<div class="reveal-top design-${esc(c.design)}"><span>✦ GIFTBRIDGE · ${esc(c.occasion.replaceAll('_',' '))}</span><div class="reveal-icon">🎁</div><h2 id="successTitle">You have a gift!</h2><p>From ${esc(c.sender)}</p></div><h3 class="center">${esc(c.program)} · ${money(c.balance_etb)}</h3><blockquote class="gift-note">${esc(c.message||'Wishing you joy, today and always.')}</blockquote><p class="soft center">Your gift is safely in your demo wallet. Show a fresh one-time PIN to the cashier when ready to redeem.</p><button id="revealClose" class="btn solid wide">Keep celebrating ✨</button>`;
    $('revealClose').onclick=()=>closeModal('successModal');openModal('successModal');
  }catch(e){notify(e.message,true);}
}
async function showRedemptionCode(id){
  try{
    const r=await api('/cards/'+id+'/redemption-pass','POST');
    $('successBody').innerHTML=`<span class="section-tag">ONE-TIME REDEMPTION</span><h2 class="center" id="successTitle">Ready to redeem</h2><p class="soft center">Show both values to your cashier. This PIN expires in five minutes and works only once.</p><div class="pin-display">${esc(r.redeem_pin)}</div><div class="bill"><div><span>Gift code</span><strong>${esc(r.card_code)}</strong></div><div><span>Expires</span><strong>5 minutes</strong></div></div><p class="soft center">Generating another PIN immediately invalidates this one.</p><button class="btn solid wide" id="pinDone">Done</button>`;
    $('pinDone').onclick=()=>closeModal('successModal');openModal('successModal');
  }catch(e){notify(e.message,true);}
}
async function sendGift(id){const phone=prompt('Recipient registered phone number (251...):');if(!phone)return;try{const r=await api('/cards/'+id+'/send','POST',{recipient_phone:phone});notify('🎁 '+r.message+' Recipient: '+r.recipient);await loadWallet();}catch(err){notify(err.message,true);}}
async function showHistory(id){try{const entries=await api('/cards/'+id+'/history');$('successBody').innerHTML=`<span class="section-tag">GIFT ACTIVITY</span><h2 id="successTitle">Gift history</h2>${entries.length?entries.map(x=>`<div class="history-row"><strong>${esc(x.action)}</strong><span>${esc(x.detail)}</span><small>${new Date(x.at).toLocaleString()} · ${money(x.amount_etb)}</small></div>`).join(''):'<p class="soft">No activity yet.</p>'}<button class="btn solid wide" id="historyDone">Close</button>`;$('historyDone').onclick=()=>closeModal('successModal');openModal('successModal');}catch(e){notify(e.message,true);}}
$('refreshWallet').onclick=loadWallet;
$('redeemForm').onsubmit=event=>handleForm(event,async()=>{
  const r=await api('/redemptions','POST',{card_code:$('redeemCode').value.trim(),merchant_id:Number($('redeemMerchant').value),amount_etb:$('redeemAmount').value,redeem_pin:$('redeemPin').value.trim(),idempotency_key:makeKey()});
  $('redeemPin').value='';
  $('successBody').innerHTML=`<div class="success-mark">✓</div><h2 id="successTitle" class="center">Gift redeemed!</h2><p class="soft center">Demo transaction captured successfully.</p><div class="bill"><div><span>Receipt</span><strong>${esc(r.receipt)}</strong></div><div><span>Merchant</span><strong>${esc(r.merchant)}</strong></div><div><span>Amount</span><strong>${money(r.amount_etb)}</strong></div><div><span>Remaining</span><strong>${money(r.balance_etb)}</strong></div></div><button id="closeReceipt" class="btn solid wide">Done</button>`;
  $('closeReceipt').onclick=()=>closeModal('successModal');openModal('successModal');notify('✓ Redemption completed: '+r.receipt);
  $('redeemCode').value='';
});
async function loadAdmin(){
  if(user?.role!=='admin')return;
  try{
    const [stats,settlement]=await Promise.all([api('/admin/overview'),api('/admin/settlements')]);
    $('metrics').innerHTML=Object.entries(stats).map(([k,v])=>`<div class="metric">${esc(k.replaceAll('_',' '))}<strong>${k.endsWith('_etb')?money(v):Number(v).toLocaleString()}</strong></div>`).join('');
    $('settlements').innerHTML='<table><thead><tr><th>Merchant</th><th>Gross ETB</th><th>Demo fee</th><th>Payable ETB</th><th>Status</th></tr></thead><tbody>'+settlement.map(x=>`<tr><td>${esc(x.merchant)}</td><td>${money(x.gross_etb)}</td><td>${money(x.fee_etb)}</td><td>${money(x.payable_etb)}</td><td>${esc(x.status)}</td></tr>`).join('')+'</tbody></table>';
  }catch(err){notify(err.message,true);}
}
$('refreshAdmin').onclick=async()=>{await refresh();await loadAdmin();};
$('merchantForm').onsubmit=event=>handleForm(event,async()=>{
  const r=await api('/admin/merchants','POST',{name:$('merchantName').value});$('merchantName').value='';await refresh();await loadAdmin();notify('✓ '+r.name+' created. You can now publish a gift program for this merchant.');
});
$('newProgramKind').onchange=()=>{$('programHint').textContent=$('newProgramKind').value==='MERCHANT_SPECIFIC'?'Choose exactly one merchant.':'Choose two or more participating merchants.';};
$('programForm').onsubmit=event=>handleForm(event,async()=>{
  const ids=[...document.querySelectorAll('#merchantPicker input:checked')].map(x=>Number(x.value));
  const kind=$('newProgramKind').value;
  if(kind==='MERCHANT_SPECIFIC'&&ids.length!==1)throw Error('Please choose exactly one merchant for a merchant-specific gift.');
  if(kind==='UNIVERSAL'&&ids.length<2)throw Error('Please choose at least two merchants for a universal gift.');
  const response=await api('/admin/programs','POST',{name:$('newProgramName').value,kind,merchant_id:kind==='MERCHANT_SPECIFIC'?ids[0]:null,accepted_merchant_ids:ids});
  $('newProgramName').value='';await refresh();await loadAdmin();notify('✓ '+response.message+' It is now available in the Gift Shop.');
});
$('staffForm').onsubmit=event=>handleForm(event,async()=>{
  const r=await api('/admin/staff','POST',{user_phone:$('staffPhone').value,merchant_id:Number($('staffMerchant').value)});$('staffPhone').value='';notify('✓ '+r.message+' Ask the cashier to sign out and sign in again.');
});

async function loadInbox(){
  if(!token)return;
  try{const items=await api('/notifications');
    $('unreadCount').hidden=!items.some(x=>!x.read);$('unreadCount').textContent=items.filter(x=>!x.read).length;
    $('inboxList').innerHTML=items.length?items.map(n=>`<article class="notification ${n.read?'':'new'}"><div class="notification-emoji">${n.event_type==='REDEEMED'?'✓':'🎁'}</div><div><h4>${esc(n.title)}</h4><p>${esc(n.body)}</p><small>${new Date(n.at).toLocaleString()}</small></div><div>${n.read?'':`<button class="btn outlined" onclick="markRead(${n.id})">Mark read</button>`}</div></article>`).join(''):'<div class="empty-state">Your inbox is quiet. Beautiful moments will show up here.</div>';
  }catch(e){if($('inbox').hidden)return;notify(e.message,true);}
}
async function markRead(id){try{await api('/notifications/'+id+'/read','POST');await loadInbox();}catch(e){notify(e.message,true);}}
$('refreshInbox').onclick=loadInbox;
function renderStudioSelect(){
  const choices=user?.role==='admin'?merchantList:cashierMerchants;
  const selected=$('merchantStudioSelect').value;
  $('merchantStudioSelect').innerHTML=choices.map(m=>`<option value="${m.id}">${esc(m.name)}</option>`).join('');
  if(choices.some(m=>String(m.id)===selected))$('merchantStudioSelect').value=selected;
}
async function loadMerchant(){
  try{
    if(['admin','merchant'].includes(user.role))cashierMerchants=await api('/staff/merchants');
    renderStudioSelect();const mid=Number($('merchantStudioSelect').value);if(!mid)return;
    const [stats,rows,branches]=await Promise.all([api('/merchant/overview?merchant_id='+mid),api('/merchant/redemptions?merchant_id='+mid),api('/branches?merchant_id='+mid)]);
    merchantRows=rows;
    $('merchantMetrics').innerHTML=[['Redemptions',stats.redemptions],['Gross redeemed',money(stats.gross_etb)],['Demo merchant payable',money(stats.payable_etb)],['Branches',stats.branches]].map(([k,v])=>`<div class="metric">${esc(k)}<strong>${esc(v)}</strong></div>`).join('');
    $('merchantRedemptions').innerHTML=rows.length?'<table><thead><tr><th>Receipt</th><th>Gift</th><th>Amount</th><th>Demo payable</th><th>Date</th></tr></thead><tbody>'+rows.map(r=>`<tr><td>${esc(r.receipt)}</td><td>${esc(r.card_code)}</td><td>${money(r.amount_etb)}</td><td>${money(r.payable_etb)}</td><td>${new Date(r.at).toLocaleString()}</td></tr>`).join('')+'</tbody></table>':'<p class="soft">No redemptions yet. They will appear after a cashier captures a gift.</p>';
    $('merchantBranches').innerHTML=branches.length?branches.map(b=>`<div class="line">⌁ <strong>${esc(b.name)}</strong> · ${esc(b.city)}</div>`).join(''):'<p class="soft">No branches added yet.</p>';
  }catch(e){notify(e.message,true);}
}
$('merchantStudioSelect').onchange=loadMerchant;
$('refreshMerchant').onclick=loadMerchant;
$('exportMerchantCsv').onclick=()=>{
  const escCsv=v=>'"'+String(v??'').replaceAll('"','""')+'"';
  const rows=[['Receipt','Gift card','Amount ETB','Fee ETB','Payable ETB','Date'],...merchantRows.map(r=>[r.receipt,r.card_code,r.amount_etb,r.fee_etb,r.payable_etb,r.at])];
  const csv=rows.map(row=>row.map(escCsv).join(',')).join('\r\n');const blob=new Blob([csv],{type:'text/csv;charset=utf-8'});const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download='giftbridge-demo-redemptions.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1500);
};
$('branchForm').onsubmit=e=>handleForm(e,async()=>{
  const r=await api('/admin/branches','POST',{merchant_id:Number($('branchMerchant').value),name:$('branchName').value,city:$('branchCity').value});
  $('branchName').value='';notify('✓ '+r.message);await loadMerchant();
});

if(token)start().catch(error=>{console.error('Session expired:',error);logout();});
