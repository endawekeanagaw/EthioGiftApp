"""v0.6 acceptance tests: payment intents, signed sandbox events, risk, security.
Uses the disposable SQLite database created by tests/test_flows.py.
"""
import hashlib
import hmac
import json
import os
import time
from datetime import datetime, timedelta, timezone
from sqlalchemy import select, func
from tests import test_flows as base
from backend.main import (SessionLocal, Card, Entry, User, FraudAlert, LoginGuard,
                          PaymentIntent, PaymentEvent, GiftOrder, hash_pw)

post,get,signup,login=base.post,base.get,base.signup,base.login


def setup_actors(prefix):
    phones=[f'251966{prefix}{x:04d}' for x in range(1,5)]
    for i,phone in enumerate(phones[:3]):signup(phone,['Buyer','Recipient','Outsider'][i]+' v06')
    with SessionLocal() as s:
        s.add(User(phone=phones[3],name='Risk Admin v06',password_hash=hash_pw('DemoPass123!'),role='admin'))
        s.commit()
    buyer,recipient,other,admin=(login(x) for x in phones)
    merchant=post('/admin/merchants',{'name':'GiftBridge v06 test merchant '+prefix},admin)
    assert merchant.status_code==200, merchant.text
    mid=merchant.json()['id']
    program=post('/admin/programs',{'name':'v06 gifts '+prefix,'kind':'MERCHANT_SPECIFIC',
        'merchant_id':mid,'accepted_merchant_ids':[mid]},admin)
    assert program.status_code==200, program.text
    return phones,(buyer,recipient,other,admin),mid,program.json()['id']


def test_payment_intent_idempotency_and_reconciliation():
    phones,(buyer,receiver,other,admin),mid,pid=setup_actors('110')
    order=post('/orders',{'program_id':pid,'amount_etb':'150.00',
        'recipient_phone':phones[1],'message':'GiftBridge payment-intent flow'},buyer).json()
    iid=order['id']
    attempt={'order_id':iid,'channel':'M-PESA (simulated)','idempotency_key':'test-v06-payment-order-0001'}
    assert post('/payments/intents',attempt,other).status_code==404
    create=post('/payments/intents',attempt,buyer)
    assert create.status_code==201,create.text
    intent=create.json()
    assert intent['status']=='PENDING' and intent['amount_etb']==150
    assert post('/payments/intents',attempt,buyer).json()['id']==intent['id']
    assert post('/payments/intents',{**attempt,'channel':'telebirr (simulated)'},buyer).status_code==409
    assert get(f"/payments/intents/{intent['id']}",other).status_code==404
    assert get('/wallet',receiver).json()==[]
    result=post(f"/payments/intents/{intent['id']}/simulate",{'outcome':'SUCCESS'},buyer)
    assert result.status_code==200,result.text
    assert result.json()['order_status']=='PAID'
    same=post(f"/payments/intents/{intent['id']}/simulate",{'outcome':'SUCCESS'},buyer)
    assert same.status_code==200 and same.json()['status']=='ALREADY_PROCESSED'
    assert len(get('/wallet',receiver).json())==1
    assert get('/orders',buyer).json()[0]['attempts'][-1]['status']=='SUCCESS'
    with SessionLocal() as s:
        assert s.scalar(select(func.count()).select_from(Card).where(Card.owner_id==int(base.client.get('/api/me',headers=receiver).json()['id'])))==1
        assert s.scalar(select(func.count()).select_from(PaymentEvent).where(PaymentEvent.intent_id==intent['id']))==1
    report=get('/admin/reconciliation',admin)
    assert report.status_code==200,report.text
    assert report.json()['result']=='PASS',report.json()
    assert get('/admin/reconciliation',buyer).status_code==403
    assert any(row['id']==intent['id'] for row in get('/admin/payment-activity',admin).json())
    # High-value purchase creates a reviewable alert without blocking the sandbox gift.
    large=post('/orders',{'program_id':pid,'amount_etb':'10000.00'},buyer).json()
    large_intent=post('/payments/intents',{'order_id':large['id'], 'channel':'telebirr (simulated)',
                        'idempotency_key':'test-v06-highvalue-intent-1'},buyer).json()
    assert post('/payments/intents/'+str(large_intent['id'])+'/simulate',{'outcome':'SUCCESS'},buyer).status_code==200
    alerts=get('/admin/fraud-alerts',admin).json()
    alert=next(a for a in alerts if a['control_id']=='GBF001' and large['code'] in a['detail'])
    assert post(f"/admin/fraud-alerts/{alert['id']}/review",{'status':'RESOLVED'},admin).status_code==422
    assert post(f"/admin/fraud-alerts/{alert['id']}/review",{'status':'INVESTIGATING','note':'Review'},buyer).status_code==403
    closed=post(f"/admin/fraud-alerts/{alert['id']}/review",{'status':'FALSE_POSITIVE','note':'Known test gift'},admin)
    assert closed.status_code==200 and closed.json()['status']=='FALSE_POSITIVE'
    assert get('/admin/reconciliation',admin).json()['result']=='PASS'


def test_signed_sandbox_webhook_replay_and_failure_retry(monkeypatch):
    phones,(buyer,recipient,other,admin),mid,pid=setup_actors('120')
    order=post('/orders',{'program_id':pid,'amount_etb':'82'},buyer).json()
    intent=post('/payments/intents',{'order_id':order['id'],'channel':'Dashen Bank (simulated)',
        'idempotency_key':'test-v06-signed-event-key'},buyer).json()
    path='/api/payments/webhook/sandbox'
    monkeypatch.setenv('ENABLE_SANDBOX_WEBHOOK','true')
    monkeypatch.setenv('SANDBOX_WEBHOOK_SECRET','very-long-test-sandbox-webhook-secret')
    event={'amount_minor':8200,'event_reference':'event-v06-signed-try-one',
        'intent_id':intent['id'],'outcome':'FAILED','provider_reference':intent['provider_reference']}
    def send_event(e,stamp=None,signature_override=None):
        stamp=stamp or int(time.time())
        compact=json.dumps(e,sort_keys=True,separators=(',',':'))
        signature=hmac.new(os.environ['SANDBOX_WEBHOOK_SECRET'].encode(),
            f'{stamp}.{compact}'.encode(),hashlib.sha256).hexdigest()
        return base.client.post(path,json=e,headers={'X-GiftBridge-Timestamp':str(stamp),
            'X-GiftBridge-Signature':signature_override or signature})
    assert base.client.post(path,json=event).status_code==401
    assert send_event(event,signature_override='deadbeef').status_code==401
    assert send_event(event,stamp=int(time.time())-1000).status_code==401
    bad={**event,'amount_minor':9999}
    assert send_event(bad).status_code==409
    outcome=send_event(event)
    assert outcome.status_code==200,outcome.text
    assert outcome.json()['order_status']=='FAILED'
    assert send_event(event).json()['status']=='ALREADY_PROCESSED'
    assert get('/wallet',buyer).json()==[]
    assert post('/orders/'+str(order['id'])+'/retry',{},buyer).status_code==200
    new_intent=post('/payments/intents',{'order_id':order['id'],'channel':'Dashen Bank (simulated)',
        'idempotency_key':'test-v06-signed-event-key-new'},buyer)
    assert new_intent.status_code==201,new_intent.text
    new_intent=new_intent.json()
    assert new_intent['id']!=intent['id']
    assert post('/payments/intents/'+str(new_intent['id'])+'/simulate',{'outcome':'SUCCESS'},buyer).status_code==200
    assert len(get('/wallet',buyer).json())==1
    assert get('/admin/reconciliation',admin).json()['result']=='PASS'
    monkeypatch.delenv('ENABLE_SANDBOX_WEBHOOK')
    assert base.client.post(path,json=event).status_code==404


def test_failed_payment_velocity_and_login_protection():
    phones,(buyer,receiver,other,admin),mid,pid=setup_actors('130')
    for n in range(3):
        order=post('/orders',{'program_id':pid,'amount_etb':'100'},buyer).json()
        intent=post('/payments/intents',{'order_id':order['id'],'channel':'Bank card (simulated)',
          'idempotency_key':f'v06-failed-payment-velocity-{n}'},buyer).json()
        out=post('/payments/intents/'+str(intent['id'])+'/simulate',{'outcome':'FAILED'},buyer)
        assert out.status_code==200,out.text
    alerts=get('/admin/fraud-alerts',admin).json()
    assert any(a['control_id']=='GBF002' for a in alerts)
    assert get('/admin/reconciliation',admin).json()['result']=='PASS'
    for n in range(5):
        wrong=post('/auth/login',{'phone':phones[0],'password':'NotCorrect!'})
        assert wrong.status_code==401
    assert post('/auth/login',{'phone':phones[0],'password':'DemoPass123!'}).status_code==429
    with SessionLocal() as s:
        guard=s.get(LoginGuard,phones[0]);assert guard.failure_count==5
        guard.locked_until=datetime.now(timezone.utc)-timedelta(seconds=1)
        s.commit()
    assert post('/auth/login',{'phone':phones[0],'password':'DemoPass123!'}).status_code==200
    with SessionLocal() as s:assert s.get(LoginGuard,phones[0]) is None


def test_reconciliation_detects_tampering():
    phones,(buyer,recipient,other,admin),mid,pid=setup_actors('140')
    assert get('/admin/reconciliation',admin).json()['result']=='PASS'
    with SessionLocal() as s:
        x=Entry(event_id='V06-TAMPER-SANDBOX-ONLY',account='GIFT_LIABILITY',delta_minor=-200)
        s.add(x);s.commit();event_id=x.id
    report=get('/admin/reconciliation',admin).json()
    assert report['result']=='FAIL'
    assert report['unbalanced_events']
    assert 'Gift liability ledger differs from card balances' in report['findings']
    with SessionLocal() as s:
        s.delete(s.get(Entry,event_id));s.commit()
    assert get('/admin/reconciliation',admin).json()['result']=='PASS'


def test_invalid_pin_alert_and_legacy_route_conflict():
    phones,(buyer,recipient,other,admin),mid,pid=setup_actors('150')
    order=post('/orders',{'program_id':pid,'amount_etb':'120','recipient_phone':phones[1]},buyer).json()
    intent=post('/payments/intents',{'order_id':order['id'],'channel':'M-PESA (simulated)',
        'idempotency_key':'test-v06-no-cross-checkout'},buyer).json()
    assert post(f"/orders/{order['id']}/simulate-payment",{'outcome':'SUCCESS'},buyer).status_code==409
    assert post('/payments/intents/'+str(intent['id'])+'/simulate',{'outcome':'SUCCESS'},buyer).status_code==200
    c=get('/wallet',recipient).json()[0]
    pin=post('/cards/'+str(c['id'])+'/redemption-pass',{},recipient).json()['redeem_pin']
    bad='11111111' if pin!='11111111' else '22222222'
    body={'card_code':c['code'],'merchant_id':mid,'amount_etb':'10',
          'idempotency_key':'v06-three-invalid-pins','redeem_pin':bad}
    for _ in range(3):
        assert post('/redemptions',body,admin).status_code==403
    alerts=get('/admin/fraud-alerts',admin).json()
    assert any(a['control_id']=='GBF003' and str(c['id']) in a['detail'] for a in alerts)
    assert get('/admin/reconciliation',admin).json()['result']=='PASS'
    response=get('/admin/reconciliation',admin)
    assert response.headers['cache-control']=='no-store'
    assert response.headers['x-frame-options']=='DENY'
