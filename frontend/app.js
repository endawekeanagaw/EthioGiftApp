'use strict';
let token=sessionStorage.getItem('gb_token');
let user=JSON.parse(sessionStorage.getItem('gb_user')||'null');
let programList=[],merchantList=[],cashierMerchants=[],authMode='login',selectedOrder=null,workingPayment=false;
const $=id=>document.getElementById(id);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const money=n=>'ETB '+Number(n).toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2});
const makeKey=()=>globalThis.crypto?.randomUUID?.()||'GB-'+Math.random().toString(36).slice(2)+Date.now();
function notify(message,bad=false){$('notice').textContent=message;$('notice').classList.toggle('error',bad);$('notice').scrollIntoView({behavior:'smooth',block:'nearest'});}
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
function tab(id){const b=document.querySelector(`[data-tab="${id}"]`);if(!b||b.hidden)return;document.querySelectorAll('[data-tab]').forEach(n=>n.classList.toggle('active',n===b));document.querySelectorAll('.view').forEach(n=>n.hidden=n.id!==id);if(id==='orders')loadOrders();if(id==='wallet')loadWallet();if(id==='admin')loadAdmin();}
document.querySelectorAll('[data-tab]').forEach(b=>b.onclick=()=>tab(b.dataset.tab));
async function start(){
  if(!token)return;
  const me=await api('/me');user=me;sessionStorage.setItem('gb_user',JSON.stringify(me));
  $('auth').hidden=true;$('dashboard').hidden=false;$('logout').hidden=false;$('userChip').hidden=false;
  $('userChip').textContent=me.name+' · '+me.role;$('welcome').textContent='Hello, '+me.name.split(' ')[0]+' 👋';
  $('adminTab').hidden=me.role!=='admin';$('posTab').hidden=!['admin','merchant'].includes(me.role);
  await refresh();
  if(['admin','merchant'].includes(me.role)){cashierMerchants=await api('/staff/merchants');renderCashierMerchants();}
  tab('shop');
}
async function refresh(){
  [programList,merchantList]=await Promise.all([api('/programs'),api('/merchants')]);
  $('program').innerHTML=programList.map(p=>`<option value="${p.id}">${esc(p.name)}</option>`).join('');
  $('programs').innerHTML=programList.length?programList.map((p,i)=>`<article class="giftcard ${p.kind==='UNIVERSAL'?'universal':''}"><div class="card-top"><span class="card-kicker">${p.kind==='UNIVERSAL'?'✦ UNIVERSAL GIFT':'✦ MERCHANT GIFT'}</span><h4>${esc(p.name)}</h4><span class="card-kicker">${p.kind==='UNIVERSAL'?'ONE GIFT. MANY POSSIBILITIES.':'PERSONAL. THOUGHTFUL. DIGITAL.'}</span></div><div class="card-content"><span class="badge">${p.accepted_merchant_ids.length} accepting merchant${p.accepted_merchant_ids.length===1?'':'s'}</span><p>${p.kind==='UNIVERSAL'?'Spend across its participating merchant network.':'Perfect for their favorite shop.'}</p><button class="btn outlined" onclick="chooseProgram(${p.id})">Choose this gift →</button></div></article>`).join(''):'<p>No programs yet. Ask an admin to create a gift program.</p>';
  const picker=$('merchantPicker');picker.innerHTML=merchantList.map(m=>`<label class="merchant-choice"><input type="checkbox" value="${m.id}"> ${esc(m.name)} <small>#${m.id}</small></label>`).join('')||'<span class="soft">Create a merchant first.</span>';
  $('staffMerchant').innerHTML=merchantList.map(m=>`<option value="${m.id}">${esc(m.name)}</option>`).join('');
  $('merchantDirectory').innerHTML=merchantList.map(m=>`<div class="line"><strong>#${m.id}</strong> · ${esc(m.name)}</div>`).join('')||'<span class="soft">No merchants available.</span>';
  renderCashierMerchants();
}
function renderCashierMerchants(){let source=user?.role==='admin'?merchantList:cashierMerchants;$('redeemMerchant').innerHTML=source.map(m=>`<option value="${m.id}">${esc(m.name)}</option>`).join('');}
function chooseProgram(id){tab('shop');$('program').value=id;$('buyPanel').scrollIntoView({behavior:'smooth'});}
$('buyForm').onsubmit=event=>handleForm(event,async()=>{
  const order=await api('/orders','POST',{program_id:Number($('program').value),amount_etb:$('amount').value,recipient_phone:$('recipient').value.trim()||null,message:$('giftMessage').value});
  showPayment(order);notify('Order '+order.code+' created. Complete your simulated checkout.');
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
  <div class="bill"><div><span>Order</span><strong>${esc(order.code)}</strong></div><div><span>Gift</span><strong>${esc(order.program)}</strong></div><div><span>For</span><strong>${esc(order.recipient)}</strong></div><div><span>Gift amount</span><strong>${money(order.amount_etb)}</strong></div></div>
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
      $('successBody').innerHTML=`<div class="success-mark">✓</div><h2 id="successTitle" class="center">Gift purchased successfully!</h2><p class="soft center">Your payment was simulated successfully, and a digital gift was issued to <strong>${esc(result.recipient)}</strong>.</p>
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
  try{let orders=await api('/orders');$('orderList').innerHTML=orders.length?orders.map(o=>`<article class="order-row"><div><h4>${esc(o.program)} <span class="badge ${esc(o.status)}">${esc(o.status)}</span></h4><p>${esc(o.code)} · For ${esc(o.recipient)} · ${new Date(o.created_at).toLocaleString()}</p><strong>${money(o.amount_etb)}</strong>${o.card_code?`<p>Gift card: <code>${esc(o.card_code)}</code></p>`:''}</div><div class="order-actions">${o.status==='PENDING'?`<button class="btn solid" onclick="payOrder(${o.id})">Complete checkout</button>`:''}${o.status==='FAILED'?`<button class="btn outlined" onclick="retryOrder(${o.id})">Retry payment</button>`:''}${o.status==='PAID'?'<span class="badge PAID">✓ Gift issued</span>':''}</div></article>`).join(''):'<div class="panel"><p class="soft">You have no orders yet. Visit the Gift Shop to buy your first gift.</p></div>';}catch(err){notify(err.message,true);}
}
async function payOrder(id){try{const o=await api('/orders/'+id);showPayment(o);}catch(err){notify(err.message,true);}}
async function retryOrder(id){try{const o=await api('/orders/'+id+'/retry','POST');showPayment(o);}catch(err){notify(err.message,true);}}
$('refreshOrders').onclick=loadOrders;
async function loadWallet(){
  try{const cards=await api('/wallet');$('walletCards').innerHTML=cards.length?cards.map(c=>`<article class="giftcard ${c.kind==='UNIVERSAL'?'universal':''}"><div class="card-top"><span class="card-kicker">✦ ${esc(c.kind.replace('_',' '))}</span><div><h4>${esc(c.program)}</h4><strong>${money(c.balance_etb)}</strong></div><span class="card-kicker">DIGITAL GIFT CARD</span></div><div class="card-content"><span class="badge ${esc(c.status)}">${esc(c.status.replaceAll('_',' '))}</span><p>Original value ${money(c.original_etb)}</p><div class="card-code">${esc(c.code)}</div><div class="card-actions" style="margin-top:15px"><button class="btn outlined" onclick="copyCode('${esc(c.code)}')">Copy code</button><button class="btn outlined" onclick="sendGift(${c.id})" ${c.status==='FULLY_REDEEMED'?'disabled':''}>Send gift</button><button class="btn outlined" onclick="showHistory(${c.id})">History</button>${['admin','merchant'].includes(user.role)?`<button class="btn outlined" onclick="useCard('${esc(c.code)}')">POS</button>`:''}</div></div></article>`).join(''):'<div class="panel"><p class="soft">Your wallet is empty. Buy a gift for yourself, or ask someone to send one to your registered phone.</p></div>';}catch(err){notify(err.message,true);}
}
function copyCode(code){if(navigator.clipboard?.writeText){navigator.clipboard.writeText(code).then(()=>notify('Card code copied to clipboard.')).catch(()=>notify('Copy the code manually: '+code));}else{notify('Gift code: '+code);}}
async function sendGift(id){const phone=prompt('Enter the recipient\'s registered GiftBridge phone number:');if(!phone)return;try{const r=await api('/cards/'+id+'/send','POST',{recipient_phone:phone});notify('🎁 '+r.message+' Recipient: '+r.recipient);await loadWallet();}catch(err){notify(err.message,true);}}
async function showHistory(id){try{const entries=await api('/cards/'+id+'/history');alert(entries.length?entries.map(x=>`${x.action} · ${x.detail} · ${money(x.amount_etb)} · ${new Date(x.at).toLocaleString()}`).join('\n'):'No redemptions or transfers yet.');}catch(err){notify(err.message,true);}}
function useCard(code){$('redeemCode').value=code;tab('redeem');}
$('refreshWallet').onclick=loadWallet;
$('redeemForm').onsubmit=event=>handleForm(event,async()=>{
  const r=await api('/redemptions','POST',{card_code:$('redeemCode').value.trim(),merchant_id:Number($('redeemMerchant').value),amount_etb:$('redeemAmount').value,idempotency_key:makeKey()});
  notify('✓ Redemption '+r.status+'. Remaining gift balance: '+money(r.balance_etb));
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
if(token)start().catch(error=>{console.error('Session expired:',error);logout();});
