"""Full end-to-end API tests in a disposable SQLite sandbox."""
import os
import tempfile
from pathlib import Path

# Set database before importing the application.
_tmp=tempfile.TemporaryDirectory(prefix='giftbridge_test_')
os.environ['DATABASE_URL']='sqlite:///'+str(Path(_tmp.name)/'test.db')
os.environ['JWT_SECRET']='LOCAL_TEST_TOKEN_SECRET'
os.environ['APP_ENV']='test'

from fastapi.testclient import TestClient
from sqlalchemy import select
from backend.main import app,SessionLocal,User,hash_pw,GiftOrder,Card,Entry

client=TestClient(app)

def post(path,body,headers=None):return client.post('/api'+path,json=body,headers=headers or {})
def get(path,headers=None):return client.get('/api'+path,headers=headers or {})
def signup(phone,name):
    r=post('/auth/register',{'name':name,'phone':phone,'password':'DemoPass123!'})
    assert r.status_code==200,r.text

def login(phone):
    r=post('/auth/login',{'phone':phone,'password':'DemoPass123!'})
    assert r.status_code==200,r.text
    return {'Authorization':'Bearer '+r.json()['access_token']}

def test_end_to_end_gifts():
    signup('251911111111','Demo Buyer')
    signup('251922222222','Demo Recipient')
    signup('251933333333','Demo Cashier')
    with SessionLocal() as s:
        s.add(User(name='Demo Admin',phone='251944444444',password_hash=hash_pw('DemoPass123!'),role='admin'));s.commit()
    buyer=login('251911111111');receiver=login('251922222222');cashier=login('251933333333');admin=login('251944444444')

    assert post('/admin/merchants',{'name':'Restricted'},buyer).status_code==403
    a=post('/admin/merchants',{'name':'Queens Sample'},admin);assert a.status_code==200,a.text
    b=post('/admin/merchants',{'name':'Bookstore Sample'},admin);assert b.status_code==200,b.text
    m1,m2=a.json()['id'],b.json()['id']
    q=post('/admin/programs',{'name':'Queens Only','kind':'MERCHANT_SPECIFIC','merchant_id':m1,'accepted_merchant_ids':[m1]},admin)
    u=post('/admin/programs',{'name':'GiftBridge Universal','kind':'UNIVERSAL','merchant_id':None,'accepted_merchant_ids':[m1,m2]},admin)
    assert q.status_code==u.status_code==200
    assert post('/admin/programs',{'name':'Invalid Universal','kind':'UNIVERSAL','accepted_merchant_ids':[m1]},admin).status_code==422
    assert post('/admin/programs',{'name':'Invalid','kind':'MERCHANT_SPECIFIC','merchant_id':m1,'accepted_merchant_ids':[m1,m2]},admin).status_code==422
    assert post('/admin/staff',{'user_phone':'251933333333','merchant_id':m1},admin).status_code==200
    assert get('/staff/merchants',cashier).json()==[{'id':m1,'name':'Queens Sample'}]

    order=post('/orders',{'program_id':q.json()['id'],'amount_etb':'1200.00','recipient_phone':'251922222222','message':'Happy birthday','occasion':'BIRTHDAY','design':'coral','sender_name':'Your biggest fan'},buyer)
    assert order.status_code==200,order.text
    oid=order.json()['id']
    assert order.json()['status']=='PENDING'
    assert get('/wallet',receiver).json()==[]
    assert post(f'/orders/{oid}/simulate-payment',{'outcome':'SUCCESS'},receiver).status_code==404
    failed=post(f'/orders/{oid}/simulate-payment',{'outcome':'FAILED','channel':'SIM Test'},buyer)
    assert failed.status_code==200 and failed.json()['status']=='FAILED'
    assert get('/wallet',receiver).json()==[]
    assert post(f'/orders/{oid}/simulate-payment',{'outcome':'SUCCESS'},buyer).status_code==409
    assert post(f'/orders/{oid}/retry',{},buyer).status_code==200
    paid=post(f'/orders/{oid}/simulate-payment',{'outcome':'SUCCESS','channel':'M-PESA (simulated)'},buyer)
    assert paid.status_code==200,paid.text
    assert paid.json()['status']=='PAID' and paid.json()['card_code']
    repeat=post(f'/orders/{oid}/simulate-payment',{'outcome':'SUCCESS','channel':'M-PESA (simulated)'},buyer)
    assert repeat.status_code==200 and repeat.json()['card_code']==paid.json()['card_code']
    cards=get('/wallet',receiver).json();assert len(cards)==1
    assert cards[0]['balance_etb']==1200.0
    assert cards[0]['design']=='coral' and cards[0]['occasion']=='BIRTHDAY'
    assert cards[0]['sender']=='Your biggest fan' and cards[0]['message']=='Happy birthday'
    assert get('/notifications',receiver).json()[0]['event_type']=='GIFT_RECEIVED'
    nid=get('/notifications',receiver).json()[0]['id']
    assert post(f'/notifications/{nid}/read',{},receiver).status_code==200
    assert get('/notifications',receiver).json()[0]['read'] is True
    assert get('/orders',buyer).json()[0]['attempts'][0]['status']=='FAILED'
    assert len(get('/orders',buyer).json()[0]['attempts'])==2
    assert get('/orders',receiver).json()==[]

    pin=post(f"/cards/{cards[0]['id']}/redemption-pass",{},receiver).json()['redeem_pin']
    assert len(pin)==8
    body={'card_code':cards[0]['code'],'merchant_id':m1,'amount_etb':'500.00','idempotency_key':'redeem-unique-123','redeem_pin':pin}
    assert post('/redemptions',body,buyer).status_code==403
    assert post('/redemptions',{**body,'merchant_id':m2},cashier).status_code==403
    assert post('/redemptions',{**body,'redeem_pin':'00000000'},cashier).status_code==403
    success=post('/redemptions',body,cashier);assert success.status_code==200,success.text
    assert success.json()['receipt'].startswith('GBR-')
    assert post('/redemptions',{**body,'idempotency_key':'redeem-different-123'},cashier).status_code==403
    assert success.json()['balance_etb']==700
    idem=post('/redemptions',body,cashier);assert idem.status_code==200 and idem.json()['status']=='ALREADY_PROCESSED'
    assert post('/redemptions',{**body,'amount_etb':'600'},cashier).status_code==409
    assert post('/redemptions',{**body,'amount_etb':'2000','idempotency_key':'redeem-unique-124'},cashier).status_code==409
    assert post('/redemptions',{**body,'merchant_id':m2,'idempotency_key':'redeem-unique-125'},admin).status_code==403
    assert get(f"/cards/{cards[0]['id']}/history",receiver).json()[0]['action']=='REDEEMED'
    assert get(f"/cards/{cards[0]['id']}/history",buyer).status_code==404
    assert post(f"/cards/{cards[0]['id']}/send",{'recipient_phone':'251911111111'},receiver).status_code==200
    assert len(get('/wallet',receiver).json())==0
    assert len(get('/wallet',buyer).json())==1
    assert len(get(f"/cards/{cards[0]['id']}/history",buyer).json())==2

    # Universal can be redeemed at either participating merchant.
    universal_order=post('/orders',{'program_id':u.json()['id'],'amount_etb':'100.00'},buyer).json()
    assert post(f"/orders/{universal_order['id']}/simulate-payment",{'outcome':'SUCCESS'},buyer).status_code==200
    universal=[x for x in get('/wallet',buyer).json() if x['kind']=='UNIVERSAL'][0]
    pin_u=post(f"/cards/{universal['id']}/redemption-pass",{},buyer).json()['redeem_pin']
    redeemed=post('/redemptions',{'card_code':universal['code'],'merchant_id':m2,'amount_etb':'40','redeem_pin':pin_u,'idempotency_key':'universal-txn-1'},admin)
    assert redeemed.status_code==200 and redeemed.json()['balance_etb']==60
    pin_u2=post(f"/cards/{universal['id']}/redemption-pass",{},buyer).json()['redeem_pin']
    remaining=post('/redemptions',{'card_code':universal['code'],'merchant_id':m1,'amount_etb':'60','redeem_pin':pin_u2,'idempotency_key':'universal-txn-2'},cashier)
    assert remaining.status_code==200 and remaining.json()['balance_etb']==0
    assert post('/redemptions',{'card_code':universal['code'],'merchant_id':m1,'amount_etb':'1','redeem_pin':pin_u2,'idempotency_key':'universal-txn-3'},cashier).status_code==409
    overview=get('/admin/overview',admin);assert overview.status_code==200
    assert overview.json()['ledger_unbalanced_events']==0
    assert overview.json()['paid_orders']==2
    settlements=get('/admin/settlements',admin).json()
    assert len(settlements)==2
    assert get('/admin/settlements',buyer).status_code==403
    assert post('/admin/branches',{'merchant_id':m1,'name':'Bole branch','city':'Addis Ababa'},admin).status_code==200
    assert len(get('/branches?merchant_id='+str(m1)).json())==1
    assert get('/merchant/overview?merchant_id='+str(m1),buyer).status_code==403
    overview_merchant=get('/merchant/overview?merchant_id='+str(m1),cashier)
    assert overview_merchant.status_code==200 and overview_merchant.json()['redemptions']==2
    assert get('/merchant/redemptions?merchant_id='+str(m2),cashier).status_code==403
    assert len(get('/merchant/redemptions?merchant_id='+str(m1),cashier).json())==2
    with SessionLocal() as s:
        assert s.scalar(select(GiftOrder).where(GiftOrder.id==oid)).status=='PAID'
        assert len(s.scalars(select(Card)).all())==2
        events=s.execute(select(Entry.event_id)).all()
        assert len(events)>0


def test_health_and_login_validation():
    h=get('/health');assert h.status_code==200 and h.json()['mode']=='SIMULATION'
    assert post('/auth/login',{'phone':'nonexistent','password':'badpass'}).status_code==401
    assert get('/me').status_code==401
    assert get('/me',{'Authorization':'Bearer invalid'}).status_code==401
