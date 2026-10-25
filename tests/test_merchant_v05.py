"""v0.5 tests for merchant lifecycle, scoped merchant teams, POS and reporting.
Uses the existing shared disposable test DB created by test_flows.py.
"""
import base64
from sqlalchemy import select, func
from tests import test_flows as base
from backend.main import SessionLocal, User, Merchant, MerchantMembership, RedemptionLocation, Entry, hash_pw

post, get, login, signup = base.post, base.get, base.login, base.signup


def test_v05_merchant_approval_team_and_qr_pos():
    signup('251955501001','New Store Owner')
    signup('251955501002','Branch Cashier')
    signup('251955501003','Shop Manager')
    signup('251955501004','Shop Buyer')
    signup('251955501005','Unrelated Customer')
    signup('251955501006','Backup Cashier')
    with SessionLocal() as s:
        s.add(User(name='V05 Platform Admin', phone='251955501007',
                   password_hash=hash_pw('DemoPass123!'),role='admin'))
        s.commit()
    owner=login('251955501001');cashier=login('251955501002');manager=login('251955501003')
    buyer=login('251955501004');unrelated=login('251955501005')
    backup=login('251955501006');admin=login('251955501007')
    request={'business_name':'Sunrise Coffee v05','category':'CAFE','city':'Addis Ababa',
        'contact_phone':'251955501001','description':'Coffee gifts for everyone'}
    assert post('/merchant/applications',request).status_code==401
    response=post('/merchant/applications',request,owner)
    assert response.status_code==201,response.text
    aid=response.json()['id']
    assert response.json()['status']=='PENDING'
    assert post('/merchant/applications',request,owner).status_code==409
    assert len(get('/merchant/applications/my',owner).json())==1
    assert get('/merchant/applications/my',unrelated).json()==[]
    assert get('/admin/applications',owner).status_code==403
    assert post(f'/admin/applications/{aid}/review',{'decision':'APPROVED'},owner).status_code==403
    pending=get('/admin/applications?status=PENDING',admin).json()
    assert any(x['id']==aid for x in pending)
    approved=post(f'/admin/applications/{aid}/review',{'decision':'APPROVED','note':'Demo verified'},admin)
    assert approved.status_code==200,approved.text
    mid=approved.json()['merchant_id']
    assert approved.json()['status']=='APPROVED'
    assert post(f'/admin/applications/{aid}/review',{'decision':'APPROVED'},admin).status_code==409
    assert any(x['id']==mid and x['role']=='OWNER' for x in get('/merchant/access',owner).json())
    assert get('/merchant/team?merchant_id='+str(mid),unrelated).status_code==403
    assert get('/merchant/team?merchant_id='+str(mid),cashier).status_code==403
    assert get('/notifications',owner).json()[0]['event_type']=='MERCHANT_APPROVED'
    main_branch=get('/branches?merchant_id='+str(mid)).json()[0]['id']
    extra=post('/merchant/branches',{'merchant_id':mid,'name':'Bole','city':'Addis Ababa'},owner)
    assert extra.status_code==200,extra.text
    branch=extra.json()['id']
    assert post('/merchant/branches',{'merchant_id':mid,'name':'Blocked','city':'Somewhere'},unrelated).status_code==403
    assert post('/merchant/team',{'merchant_id':mid,'user_phone':'251955501002','role':'CASHIER'},owner).status_code==422
    inv=post('/merchant/team',{'merchant_id':mid,'user_phone':'251955501003','role':'MANAGER'},owner)
    assert inv.status_code==200,inv.text
    assert post('/merchant/team',{'merchant_id':mid,'user_phone':'251955501006','role':'MANAGER'},manager).status_code==403
    inv=post('/merchant/team',{'merchant_id':mid,'user_phone':'251955501002','role':'CASHIER','branch_id':branch},manager)
    assert inv.status_code==200,inv.text
    inv2=post('/merchant/team',{'merchant_id':mid,'user_phone':'251955501006','role':'CASHIER','branch_id':branch},owner)
    assert inv2.status_code==200,inv2.text
    team=get('/merchant/team?merchant_id='+str(mid),owner).json()
    cashier_member=next(t for t in team if t['phone']=='251955501002')
    assert cashier_member['branch_id']==branch and cashier_member['role']=='CASHIER'
    assert get('/merchant/access',cashier).json()[0]['branch_id']==branch
    assert post('/merchant/programs',{'merchant_id':mid,'name':'Forbidden','category':'FOOD'},cashier).status_code==403
    gift=post('/merchant/programs',{'merchant_id':mid,'name':'Sunrise Coffee Thank You','category':'FOOD','emoji':'☕',
        'description':'A morning surprise'},owner)
    assert gift.status_code==200,gift.text
    pid=gift.json()['id']
    assert any(p['id']==pid for p in get('/programs',buyer).json())
    order=post('/orders',{'program_id':pid,'amount_etb':'500','recipient_phone':'251955501004'},buyer)
    assert order.status_code==200,order.text
    paid=post(f"/orders/{order.json()['id']}/simulate-payment",{'outcome':'SUCCESS'},buyer)
    assert paid.status_code==200,paid.text
    card=get('/wallet',buyer).json()[0]
    qr=get(f"/cards/{card['id']}/qr",buyer)
    assert qr.status_code==200,qr.text
    assert base64.b64decode(qr.json()['png_base64']).startswith(b'\x89PNG\r\n\x1a\n')
    assert get(f"/cards/{card['id']}/qr",unrelated).status_code==404
    pin=post(f"/cards/{card['id']}/redemption-pass",{},buyer).json()['redeem_pin']
    body={'card_code':card['code'],'merchant_id':mid,'branch_id':main_branch,'amount_etb':'125',
          'redeem_pin':pin,'idempotency_key':'v05-redemption-sunrise-1'}
    assert post('/redemptions',body,cashier).status_code==403  # cashier only assigned Bole
    assert post('/redemptions',{**body,'branch_id':None},cashier).status_code==403
    redeemed=post('/redemptions',{**body,'branch_id':branch},cashier)
    assert redeemed.status_code==200,redeemed.text
    assert redeemed.json()['branch']=='Bole'
    assert redeemed.json()['balance_etb']==375
    assert post('/redemptions',{**body,'branch_id':branch},backup).status_code==409 # idem cannot be stolen
    report=get(f'/merchant/report?merchant_id={mid}&days=30',owner)
    assert report.status_code==200,report.text
    assert report.json()['transactions']==1 and report.json()['redeemed_etb']==125
    assert report.json()['merchant_specific_sales_etb']==500
    assert report.json()['branches'][0]['branch']=='Bole'
    assert get(f'/merchant/report?merchant_id={mid}&days=30',cashier).status_code==403
    assert get(f'/merchant/report?merchant_id={mid}&days=30',unrelated).status_code==403
    assert get(f'/merchant/report?merchant_id={mid}&days=2',owner).status_code==422
    member=next(t for t in get('/merchant/team?merchant_id='+str(mid),owner).json() if t['phone']=='251955501002')
    assert base.client.patch(f"/api/merchant/team/{member['id']}",json={'active':False},headers=owner).status_code==200
    assert get('/merchant/access',cashier).json()==[]
    pin2=post(f"/cards/{card['id']}/redemption-pass",{},buyer).json()['redeem_pin']
    assert post('/redemptions',{**body,'redeem_pin':pin2,'idempotency_key':'v05-redemption-sunrise-2','branch_id':branch},cashier).status_code==403
    with SessionLocal() as s:
        assert s.scalar(select(func.count()).select_from(RedemptionLocation).where(RedemptionLocation.branch_id==branch))==1
        balances=s.execute(select(Entry.event_id,func.sum(Entry.delta_minor)).group_by(Entry.event_id))
        assert all(amount==0 for _,amount in balances)


def test_v05_rejected_application_is_private_and_reason_required():
    signup('251955502001','Unlucky Applicant')
    with SessionLocal() as s:
        s.add(User(name='V05 Reviewer',phone='251955502002',password_hash=hash_pw('DemoPass123!'),role='admin'))
        s.commit()
    applicant=login('251955502001');reviewer=login('251955502002')
    req={'business_name':'Rejected Cafe v05','category':'CAFE','city':'Adama','contact_phone':'251955502001'}
    a=post('/merchant/applications',req,applicant)
    assert a.status_code==201,a.text
    aid=a.json()['id']
    assert post(f'/admin/applications/{aid}/review',{'decision':'REJECTED'},reviewer).status_code==422
    rejected=post(f'/admin/applications/{aid}/review',{'decision':'REJECTED','note':'Demo documents incomplete'},reviewer)
    assert rejected.status_code==200,rejected.text
    assert rejected.json()['status']=='REJECTED'
    assert not any(x['name']=='Rejected Cafe v05' for x in get('/merchants').json())
    assert get('/merchant/applications/my',applicant).json()[0]['review_note']=='Demo documents incomplete'
