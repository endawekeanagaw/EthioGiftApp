'use strict';
let token=sessionStorage.getItem('gb_token');
let user=JSON.parse(sessionStorage.getItem('gb_user')||'null');
let merchantAccess=[], scannerStream=null, scanLoopActive=false;
let programList=[],merchantList=[],cashierMerchants=[],authMode='login',selectedOrder=null,workingPayment=false,selectedDesign='emerald',catalogFilter='ALL',categoryFilter='ALL',favoriteIds=new Set(),merchantRows=[],walletItems=[];
const $=id=>document.getElementById(id);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const money=n=>'ETB '+(Math.abs(Number(n))<0.005?0:Number(n)).toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2});
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
function tab(id){const b=document.querySelector(`[data-tab="${id}"]`);if(!b||b.hidden)return;document.querySelectorAll('[data-tab]').forEach(n=>n.classList.toggle('active',n===b));document.querySelectorAll('.view').forEach(n=>n.hidden=n.id!==id);if(id==='orders')loadOrders();if(id==='wallet')loadWallet();if(id==='admin'){loadAdmin();if(typeof loadRiskOps==='function')loadRiskOps();}if(id==='inbox')loadInbox();if(id==='merchant'){loadMerchant();loadMerchantTools();}if(id==='business')loadMerchantApplications();if(id==='admin')loadApplicationQueue();if(id!=='redeem')stopQrScanner();}
document.querySelectorAll('[data-tab]').forEach(b=>b.onclick=()=>tab(b.dataset.tab));
async function start(){
  if(!token)return;
  const me=await api('/me');user=me;sessionStorage.setItem('gb_user',JSON.stringify(me));
  $('auth').hidden=true;$('dashboard').hidden=false;$('logout').hidden=false;$('userChip').hidden=false;
  $('userChip').textContent=me.name+' · '+me.role;$('welcome').textContent='Hello, '+me.name.split(' ')[0]+' 👋';
  merchantAccess=await api('/merchant/access');
  $('adminTab').hidden=me.role!=='admin';$('posTab').hidden=merchantAccess.length===0;$('merchantTab').hidden=merchantAccess.length===0;$('senderName').value=me.name;
  await refresh();
  favoriteIds=new Set((await api('/favorites')).program_ids);renderPrograms();
  if(merchantAccess.length){cashierMerchants=await api('/staff/merchants');renderCashierMerchants();renderStudioSelect();await loadRedeemBranches();}
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
function renderCashierMerchants(){let source=merchantAccess;$('redeemMerchant').innerHTML=source.map(m=>`<option value="${m.id}">${esc(m.name)}</option>`).join('');}
function chooseProgram(id){tab('shop');$('program').value=id;updatePreview();$('buyPanel').scrollIntoView({behavior:'smooth'});}
function renderPrograms(){
  const search=$('searchPrograms').value.trim().toLowerCase();
  const filtered=programList.filter(p=>(catalogFilter==='ALL'||p.kind===catalogFilter||(catalogFilter==='FAVORITES'&&favoriteIds.has(p.id)))
    &&(categoryFilter==='ALL'||p.category===categoryFilter)
    &&(!search||(p.name+' '+p.description+' '+p.category).toLowerCase().includes(search)));
  $('programs').innerHTML=filtered.length?filtered.map(p=>`<article class="giftcard catalog-card ${p.kind==='UNIVERSAL'?'universal':''}">
    <div class="card-top"><span class="card-kicker">${p.kind==='UNIVERSAL'?'✦ THE UNIVERSAL EDITION':'✦ A FAVORITE PLACE'}</span>
    <button class="fav-heart ${favoriteIds.has(p.id)?'active':''}" type="button" aria-label="${favoriteIds.has(p.id)?'Remove saved gift':'Save gift'}" aria-pressed="${favoriteIds.has(p.id)}" onclick="toggleFavorite(${p.id})">${favoriteIds.has(p.id)?'♥':'♡'}</button>
    <div class="catalog-symbol">${esc(p.emoji||'🎁')}</div><h4>${esc(p.name)}</h4><span class="card-kicker">${esc(p.category||'SHOPPING')}</span></div>
    <div class="card-content"><span class="badge">${p.accepted_merchant_ids.length} ${p.accepted_merchant_ids.length===1?'participating merchant':'participating merchants'}</span>
    <p>${esc(p.description|| (p.kind==='UNIVERSAL'?'One gift, many possibilities.':'A meaningful gift from a favorite place.'))}</p>
    <button class="btn outlined wide" onclick="chooseProgram(${p.id})">Personalize this gift →</button></div></article>`).join(''):
    '<div class="empty-state"><span>♡</span><h3>No matching gifts yet</h3><p>Explore other categories or save some favorites.</p><button class="btn outlined" onclick="clearGiftFilters()">Show all gifts</button></div>';
}
async function toggleFavorite(programId){
  try{
    if(favoriteIds.has(programId)){await api('/favorites/'+programId,'DELETE');favoriteIds.delete(programId);notify('Removed from saved gifts.');}
    else{await api('/favorites/'+programId,'POST');favoriteIds.add(programId);notify('Saved to your favorite gifts ♥');}
    renderPrograms();
  }catch(e){notify(e.message,true);}
}
function clearGiftFilters(){catalogFilter='ALL';categoryFilter='ALL';$('searchPrograms').value='';document.querySelectorAll('[data-filter]').forEach(b=>b.classList.toggle('selected',b.dataset.filter==='ALL'));document.querySelectorAll('[data-category]').forEach(b=>b.classList.toggle('active',b.dataset.category==='ALL'));renderPrograms();}
$('searchPrograms').addEventListener('input',renderPrograms);
document.querySelectorAll('.filter-chips [data-filter]').forEach(btn=>btn.onclick=()=>{catalogFilter=btn.dataset.filter;document.querySelectorAll('.filter-chips [data-filter]').forEach(b=>b.classList.toggle('selected',b===btn));renderPrograms();});
document.querySelectorAll('[data-category]').forEach(btn=>btn.onclick=()=>{categoryFilter=btn.dataset.category;document.querySelectorAll('[data-category]').forEach(b=>b.classList.toggle('active',b===btn));renderPrograms();});
$('heroExplore').onclick=()=>{if(!token){$('auth').scrollIntoView({behavior:'smooth'});return;}tab('shop');$('shop').scrollIntoView({behavior:'smooth'});};
document.querySelectorAll('[data-amount]').forEach(btn=>btn.onclick=()=>{$('amount').value=btn.dataset.amount;updatePreview();});
document.querySelectorAll('.design-option').forEach(btn=>btn.onclick=()=>{selectedDesign=btn.dataset.design;document.querySelectorAll('.design-option').forEach(b=>b.classList.toggle('selected',b===btn));updatePreview();});
for(const id of ['amount','occasion','recipient','senderName','giftMessage'])$(id).addEventListener('input',updatePreview);
function updatePreview(){
  const selected=programList.find(p=>p.id===Number($('program').value));const box=$('giftPreview');
  box.className='purchase-preview design-'+selectedDesign;
  box.innerHTML=`<span>✦ GIFTBRIDGE / ${esc($('occasion').options[$('occasion').selectedIndex]?.textContent||'GIFT')}</span><strong>${esc(selected?.name||'GiftBridge gift')}</strong><b>${money($('amount').value||0)}</b><small>From ${esc($('senderName').value||'Someone special')} · SANDBOX PREVIEW</small>`;
  $('previewMessage').textContent=$('giftMessage').value.trim()||'Your thoughtful message appears here.';
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
  <p id="gatewayProgress" class="sandbox-progress" aria-live="polite">Ready · No actual payment will be initiated</p>
  <div class="modal-actions" style="margin-top:20px"><button id="paySuccess" class="btn solid">✓ Simulate successful payment</button><button id="payFailed" class="btn outlined">Simulate failed payment</button></div>
  <p class="soft tiny center">No external API calls, real bank requests or charges. Your recipient receives a demo gift in their in-app wallet.</p>`;
  $('paySuccess').onclick=()=>pay('SUCCESS');$('payFailed').onclick=()=>pay('FAILED');openModal('paymentModal');
}
async function pay(outcome){
  if(workingPayment||!selectedOrder)return;workingPayment=true;
  const successBtn=$('paySuccess'),failedBtn=$('payFailed');successBtn.disabled=failedBtn.disabled=true;
  try{
    // v0.6 uses an explicit payment intent and sandbox gateway event.
    // No customer money is collected; this is not a real provider integration.
    const channel=$('simChannel').value;
    const idem=makeKey();
    $('gatewayProgress').textContent='1/3 · Creating a simulated payment intent…';
    const intent=await api('/payments/intents','POST',{order_id:selectedOrder.id,channel,idempotency_key:idem});
    $('gatewayProgress').textContent='2/3 · Processing a sandbox gateway event…';
    const processed=await api('/payments/intents/'+intent.id+'/simulate','POST',{outcome});
    $('gatewayProgress').textContent='3/3 · Checking gift issuance and status…';
    const result=processed.order||await api('/orders/'+selectedOrder.id);
    closeModal('paymentModal');selectedOrder=null;
    await loadOrders();
    if(result.status==='PAID'){
      $('successBody').innerHTML=`<div class="success-mark">✓</div><h2 id="successTitle" class="center">Gift purchased successfully!</h2><p class="soft center">Your simulated payment succeeded. A digital gift has been delivered to <strong>${esc(result.recipient)}</strong> in their GiftBridge inbox and wallet.</p>
      <div class="bill"><div><span>Gift</span><strong>${esc(result.program)}</strong></div><div><span>Gift value</span><strong>${money(result.amount_etb)}</strong></div><div><span>Card code</span><strong>${esc(result.card_code)}</strong></div><div><span>Payment</span><strong>SIMULATED · SUCCESS</strong></div><div><span>Gateway</span><strong>Verified sandbox event (no funds)</strong></div></div>
      <div class="modal-actions"><button class="btn solid" id="afterPayReceipt">↓ Download demo receipt</button><button class="btn outlined" id="afterPayShare">↗ Share gift announcement</button><button class="btn outlined" id="afterPayOrders">View my orders</button></div>`;
      $('afterPayReceipt').onclick=()=>downloadPurchaseReceipt(result.id);
      $('afterPayShare').onclick=()=>shareGiftAnnouncement(result);
      $('afterPayOrders').onclick=()=>{closeModal('successModal');tab('orders');};
      openModal('successModal');notify('Success! Gift card '+result.card_code+' issued.');
    }else{
      notify('Payment simulation failed. The order is saved but no gift was issued. You can retry it from My Orders.',true);tab('orders');
    }
  }catch(err){notify(err.message,true);}
  finally{workingPayment=false;if(successBtn?.isConnected)successBtn.disabled=false;if(failedBtn?.isConnected)failedBtn.disabled=false;}
}
async function loadOrders(){
  try{let orders=await api('/orders');$('orderList').innerHTML=orders.length?orders.map(o=>`<article class="order-row"><div><h4>${esc(o.program)} <span class="badge ${esc(o.status)}">${esc(o.status)}</span></h4><p>${esc(o.code)} · For ${esc(o.recipient)} · ${new Date(o.created_at).toLocaleString()}</p><strong>${money(o.amount_etb)}</strong><p>${esc(o.occasion.replaceAll('_',' '))} · ${esc(o.message||'A thoughtful gesture')}</p>${o.card_code?`<p>Gift card: <code>${esc(o.card_code)}</code></p>`:''}</div><div class="order-actions">${o.status==='PENDING'?`<button class="btn solid" onclick="payOrder(${o.id})">Complete checkout</button>`:''}${o.status==='FAILED'?`<button class="btn outlined" onclick="retryOrder(${o.id})">Retry payment</button>`:''}${o.status==='PAID'?`<button class="btn outlined" onclick="downloadPurchaseReceipt(${o.id})">↓ Receipt</button><button class="btn outlined" onclick="shareGiftAnnouncementById(${o.id})">↗ Share</button>`:''}</div></article>`).join(''):'<div class="panel"><p class="soft">You have no orders yet. Visit the Gift Shop to buy your first gift.</p></div>';}catch(err){notify(err.message,true);}
}
async function payOrder(id){try{const o=await api('/orders/'+id);showPayment(o);}catch(err){notify(err.message,true);}}
async function retryOrder(id){try{const o=await api('/orders/'+id+'/retry','POST');showPayment(o);}catch(err){notify(err.message,true);}}
$('refreshOrders').onclick=loadOrders;
async function loadWallet(){
  try{
    const [cards,summary]=await Promise.all([api('/wallet'),api('/wallet/summary')]);
    walletItems=cards;
    $('walletSummary').innerHTML=`<div class="wallet-balance"><span>My available gift balance</span><strong>${money(summary.balance_etb)}</strong><small>Demo gift value · No cash equivalent</small></div><div class="wallet-count"><span>My gifts</span><strong>${cards.length}</strong><small>Across participating demonstration brands</small></div>`;
    renderWallet();
  }catch(err){notify(err.message,true);}
}
function renderWallet(){
  const search=$('walletSearch').value.trim().toLowerCase(),status=$('walletStatus').value;
  const cards=walletItems.filter(c=>(status==='ALL'||(status==='AVAILABLE'?c.balance_etb>0:c.balance_etb===0))&&(!search||(c.program+' '+c.code+' '+c.sender).toLowerCase().includes(search)));
  $('walletCards').innerHTML=cards.length?cards.map(c=>`<article class="giftcard wallet-card"><div class="card-top design-${esc(c.design)}"><span class="card-kicker">✦ ${esc(c.kind.replace('_',' '))}</span><div><span class="wallet-occasion">${esc(c.occasion.replaceAll('_',' '))}</span><h4>${esc(c.program)}</h4><strong>${money(c.balance_etb)}</strong></div><span class="card-kicker">A GIFT FOR YOU</span></div>
    <div class="card-content"><span class="badge ${esc(c.status)}">${esc(c.status.replaceAll('_',' '))}</span><p>From <strong>${esc(c.sender)}</strong> · Original ${money(c.original_etb)}</p><div class="card-code">${esc(c.code)}</div>
    <div class="gift-progress" title="Remaining share of original value"><span style="width:${Math.min(100,Math.max(0,100*c.balance_etb/Math.max(c.original_etb,0.01)))}%"></span></div>
    <div class="card-actions" style="margin-top:15px"><button class="btn solid" onclick="unwrapGift(${c.id})">Open gift ✨</button><button class="btn outlined" onclick="showRedemptionCode(${c.id})" ${c.balance_etb<=0?'disabled':''}>Redeem PIN</button><button class="btn outlined" onclick="sendGift(${c.id})" ${c.balance_etb<=0?'disabled':''}>Send</button><button class="btn outlined" onclick="showHistory(${c.id})">Activity</button></div></div></article>`).join(''):
    '<div class="empty-state"><span>🎁</span><h3>No gifts found</h3><p>Try another filter or discover something thoughtful.</p><button class="btn solid" id="emptyShop">Explore gifts →</button></div>';
  if($('emptyShop'))$('emptyShop').onclick=()=>tab('shop');
}
$('walletSearch').addEventListener('input',renderWallet);
$('walletStatus').addEventListener('change',renderWallet);
async function unwrapGift(id){
  try{
    const c=(await api('/wallet')).find(x=>x.id===id);if(!c)return;
    $('successBody').innerHTML=`<div class="reveal-top design-${esc(c.design)}"><span>✦ GIFTBRIDGE · ${esc(c.occasion.replaceAll('_',' '))}</span><div class="reveal-icon">🎁</div><h2 id="successTitle">You have a gift!</h2><p>From ${esc(c.sender)}</p></div><h3 class="center">${esc(c.program)} · ${money(c.balance_etb)}</h3><blockquote class="gift-note">${esc(c.message||'Wishing you joy, today and always.')}</blockquote><p class="soft center">Your gift is safely in your demo wallet. Show a fresh one-time PIN to the cashier when ready to redeem.</p><button id="revealShare" class="btn outlined wide">↗ Share a thank-you</button><button id="revealClose" class="btn solid wide">Keep celebrating ✨</button>`;
    $('revealShare').onclick=()=>shareText(`Thank you for the thoughtful ${c.program} gift! 🎁 GiftBridge Ethiopia demo`);$('revealClose').onclick=()=>closeModal('successModal');openModal('successModal');
  }catch(e){notify(e.message,true);}
}
async function showRedemptionCode(id){
  try{
    const r=await api('/cards/'+id+'/redemption-pass','POST');
    $('successBody').innerHTML=`<span class="section-tag">ONE-TIME REDEMPTION</span><h2 class="center" id="successTitle">Ready to redeem</h2><p class="soft center">Show both values to your cashier. This PIN expires in five minutes and works only once.</p><div class="pin-display">${esc(r.redeem_pin)}</div><div class="bill"><div><span>Gift code</span><strong>${esc(r.card_code)}</strong></div><div><span>Expires</span><strong>5 minutes</strong></div></div><p class="soft center">Generating another PIN immediately invalidates this one.</p><button class="btn solid wide" id="pinDone">Done</button>`;
    $('pinDone').onclick=()=>closeModal('successModal');openModal('successModal');
    try{const qr=await api('/cards/'+id+'/qr');if(!$('successModal').hidden){const image=document.createElement('img');image.src='data:image/png;base64,'+qr.png_base64;image.alt='Gift card QR for cashier; PIN required separately';image.className='wallet-qr';$('successBody').insertBefore(image,$('successBody').querySelector('.pin-display'));}}catch(err){console.warn('QR unavailable:',err.message);}
  }catch(e){notify(e.message,true);}
}
async function sendGift(id){const phone=prompt('Recipient registered phone number (251...):');if(!phone)return;try{const r=await api('/cards/'+id+'/send','POST',{recipient_phone:phone});notify('🎁 '+r.message+' Recipient: '+r.recipient);await loadWallet();}catch(err){notify(err.message,true);}}
async function showHistory(id){try{const entries=await api('/cards/'+id+'/history');$('successBody').innerHTML=`<span class="section-tag">GIFT ACTIVITY</span><h2 id="successTitle">Gift history</h2>${entries.length?entries.map(x=>`<div class="history-row"><strong>${esc(x.action)}</strong><span>${esc(x.detail)}</span><small>${new Date(x.at).toLocaleString()} · ${money(x.amount_etb)}</small></div>`).join(''):'<p class="soft">No activity yet.</p>'}<button class="btn solid wide" id="historyDone">Close</button>`;$('historyDone').onclick=()=>closeModal('successModal');openModal('successModal');}catch(e){notify(e.message,true);}}
$('refreshWallet').onclick=loadWallet;
$('redeemForm').onsubmit=event=>handleForm(event,async()=>{
  const r=await api('/redemptions','POST',{card_code:$('redeemCode').value.trim(),merchant_id:Number($('redeemMerchant').value),branch_id:$('redeemBranch').value?Number($('redeemBranch').value):null,amount_etb:$('redeemAmount').value,redeem_pin:$('redeemPin').value.trim(),idempotency_key:makeKey()});
  $('redeemPin').value='';
  $('successBody').innerHTML=`<div class="success-mark">✓</div><h2 id="successTitle" class="center">Gift redeemed!</h2><p class="soft center">Demo transaction captured successfully.</p><div class="bill"><div><span>Receipt</span><strong>${esc(r.receipt)}</strong></div><div><span>Merchant</span><strong>${esc(r.merchant)}</strong></div><div><span>Amount</span><strong>${money(r.amount_etb)}</strong></div><div><span>Remaining</span><strong>${money(r.balance_etb)}</strong></div></div><button id="downloadRedeemReceipt" class="btn outlined wide">↓ Download demo receipt</button><button id="closeReceipt" class="btn solid wide">Done</button>`;
  $('downloadRedeemReceipt').onclick=()=>downloadRedemptionReceipt(r.id);$('closeReceipt').onclick=()=>closeModal('successModal');openModal('successModal');notify('✓ Redemption completed: '+r.receipt);
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
  const response=await api('/admin/programs','POST',{name:$('newProgramName').value,kind,merchant_id:kind==='MERCHANT_SPECIFIC'?ids[0]:null,accepted_merchant_ids:ids,category:$('newProgramCategory').value,description:$('newProgramDescription').value,emoji:$('newProgramEmoji').value});
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
  const choices=merchantAccess;
  const selected=$('merchantStudioSelect').value;
  $('merchantStudioSelect').innerHTML=choices.map(m=>`<option value="${m.id}">${esc(m.name)}</option>`).join('');
  if(choices.some(m=>String(m.id)===selected))$('merchantStudioSelect').value=selected;
}
async function loadMerchant(){
  try{
    if(merchantAccess.length)cashierMerchants=await api('/staff/merchants');
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
  const escCsv=v=>{let x=String(v??'');if(/^[\s]*[=+@\-\t\r]/.test(x))x="'"+x;return '"'+x.replaceAll('"','""')+'"';};
  const rows=[['Receipt','Gift card','Amount ETB','Fee ETB','Payable ETB','Date'],...merchantRows.map(r=>[r.receipt,r.card_code,r.amount_etb,r.fee_etb,r.payable_etb,r.at])];
  const csv=rows.map(row=>row.map(escCsv).join(',')).join('\r\n');const blob=new Blob([csv],{type:'text/csv;charset=utf-8'});const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download='giftbridge-demo-redemptions.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1500);
};
$('branchForm').onsubmit=e=>handleForm(e,async()=>{
  const r=await api('/admin/branches','POST',{merchant_id:Number($('branchMerchant').value),name:$('branchName').value,city:$('branchCity').value});
  $('branchName').value='';notify('✓ '+r.message);await loadMerchant();
});

// v0.4: share a friendly announcement. Never share a card code or one-time redemption PIN.
async function shareText(message){
  try{
    if(navigator.share){await navigator.share({title:'GiftBridge Ethiopia',text:message});return;}
    if(navigator.clipboard?.writeText){await navigator.clipboard.writeText(message);notify('Gift announcement copied. Paste it into your messaging app.');return;}
    prompt('Copy this message:',message);
  }catch(e){if(e.name!=='AbortError')notify('Could not share: '+e.message,true);}
}
function shareGiftAnnouncement(order){
  shareText(`🎁 A thoughtful ${order.program} gift worth ${money(order.amount_etb)} is waiting for ${order.recipient} in GiftBridge Ethiopia (demo). Sign in to the recipient account to open it. No real payment was made.`);
}
async function shareGiftAnnouncementById(id){try{shareGiftAnnouncement(await api('/orders/'+id));}catch(e){notify(e.message,true);}}
function escapeHtmlText(value){return esc(value);}
function receiptHTML(data){
  const rows=Object.entries(data).filter(([key])=>!['demo_only','disclaimer','receipt_type'].includes(key)).map(([key,value])=>
    `<tr><th>${escapeHtmlText(key.replaceAll('_',' '))}</th><td>${escapeHtmlText(value??'—')}</td></tr>`).join('');
  return `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>${escapeHtmlText(data.reference)} · GiftBridge Demo</title><style>
    body{font-family:Arial,sans-serif;color:#193f2e;max-width:700px;margin:60px auto;padding:24px;background:#f8faf6}
    .paper{background:white;padding:40px;border:1px solid #dbe7dd;border-radius:20px}
    h1{font-size:27px}small{color:#728577}th{text-align:left;text-transform:capitalize;color:#67796f;font-weight:500}
    table{border-collapse:collapse;width:100%;margin:26px 0}td,th{padding:13px 9px;border-bottom:1px solid #e6ede7;overflow-wrap:anywhere}
    td{text-align:right;font-weight:700}.stamp{font-size:12px;border:2px solid #bb6b48;color:#994526;border-radius:10px;padding:12px;margin-top:24px;font-weight:700}
    @media print{body{margin:0;background:white}.paper{border:0}}
    </style></head><body><div class="paper"><small>✦ GIFTBRIDGE ETHIOPIA · SANDBOX</small><h1>${data.receipt_type==='PURCHASE'?'Gift purchase':'Gift redemption'} receipt</h1><p><strong>${escapeHtmlText(data.reference)}</strong></p><table>${rows}</table><div class="stamp">${escapeHtmlText(data.disclaimer)}</div><p><small>For developer testing only. Not proof of payment or a tax invoice. Print this page to save as PDF.</small></p></div></body></html>`;
}
function downloadHTML(filename,html){const blob=new Blob([html],{type:'text/html;charset=utf-8'});const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=filename;document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),2000);}
async function downloadPurchaseReceipt(id){try{const d=await api('/orders/'+id+'/receipt');downloadHTML(d.reference+'.html',receiptHTML(d));notify('Demo receipt downloaded. Open in your browser and print/save as PDF.');}catch(e){notify(e.message,true);}}
async function downloadRedemptionReceipt(id){try{const d=await api('/redemptions/'+id+'/receipt');downloadHTML(d.reference+'.html',receiptHTML(d));notify('Demo redemption receipt downloaded.');}catch(e){notify(e.message,true);}}
const localeTexts={
 en:{heroEyebrow:'THE JOY OF GIVING, REIMAGINED',heroFirst:'Give a moment.',heroSecond:'Make it memorable.',heroCopy:'Choose a favorite brand or the freedom of a GiftBridge universal gift. Send it in moments. Make someone\'s day.',explore:'Explore gifts →',findGift:'Find the perfect gift',dashboardSub:'Your next thoughtful gesture starts here.',discover:'Discover gifts',orders:'My orders',wallet:'My wallet',inbox:'Inbox',buyGift:'Buy a digital gift'},
 am:{heroEyebrow:'የስጦታ ባህላችንን በዲጂታል እናዘምን',heroFirst:'ደስታን ይስጡ።',heroSecond:'ትዝታን ይፍጠሩ።',heroCopy:'ከተለያዩ የንግድ ቦታዎች የስጦታ ካርድ ይምረጡ፤ ወይም ለተቀባዩ ሰፊ ምርጫ የሚሰጥ የGiftBridge ስጦታ ይላኩ።',explore:'ስጦታዎችን ይመልከቱ →',findGift:'ተስማሚውን ስጦታ ይምረጡ',dashboardSub:'ቀጣዩ ልዩ ስጦታዎ እዚህ ይጀምራል።',discover:'ስጦታዎች',orders:'ትዕዛዞቼ',wallet:'የስጦታ ቦርሳዬ',inbox:'መልዕክቶች',buyGift:'ዲጂታል ስጦታ ይግዙ'}
};
function setLanguage(lang){const selected=localeTexts[lang]?lang:'en';localStorage.setItem('gb_lang',selected);document.documentElement.lang=selected;
 document.querySelectorAll('[data-i18n]').forEach(el=>{el.textContent=localeTexts[selected][el.dataset.i18n]||localeTexts.en[el.dataset.i18n]||'';});$('languageSelect').value=selected;
}
$('languageSelect').onchange=e=>setLanguage(e.target.value);
setLanguage(localStorage.getItem('gb_lang')||'en');

if(token)start().catch(error=>{console.error('Session expired:',error);logout();});
