"""GiftBridge Ethiopia v0.2 — local SIMULATION only. No actual payments or gift value."""
import base64
import hashlib
import hmac
import json
import os
import secrets
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import (DateTime, ForeignKey, Integer, String, UniqueConstraint,
                        create_engine, func, select, update)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

ROOT = Path(__file__).resolve().parent.parent
DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///' + str(ROOT / 'giftbridge.db'))
JWT_SECRET = os.getenv('JWT_SECRET', 'CHANGE_ME_LOCAL_DEMO_ONLY')
if os.getenv('APP_ENV') == 'production':
    raise RuntimeError('GiftBridge SIMULATION build must never be used in production')
engine = create_engine(DATABASE_URL,
    connect_args={'check_same_thread': False, 'timeout': 30} if DATABASE_URL.startswith('sqlite') else {},
    pool_pre_ping=True)
if DATABASE_URL.startswith('sqlite'):
    from sqlalchemy import event
    @event.listens_for(engine, 'connect')
    def sqlite_setup(conn, _):
        cur = conn.cursor()
        cur.execute('PRAGMA foreign_keys=ON')
        cur.execute('PRAGMA busy_timeout=30000')
        cur.close()
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

class Base(DeclarativeBase): pass
class User(Base):
    __tablename__='users'
    id: Mapped[int] = mapped_column(primary_key=True)
    phone: Mapped[str] = mapped_column(String(30), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(150))
    role: Mapped[str] = mapped_column(String(30), default='customer')
class Merchant(Base):
    __tablename__='merchants'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    status: Mapped[str] = mapped_column(String(20), default='ACTIVE')
class MerchantStaff(Base):
    __tablename__='merchant_staff'
    __table_args__ = (UniqueConstraint('user_id','merchant_id'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    merchant_id: Mapped[int] = mapped_column(ForeignKey('merchants.id'))
class Program(Base):
    __tablename__='programs'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(30))
    merchant_id: Mapped[Optional[int]] = mapped_column(ForeignKey('merchants.id'),nullable=True)
    active: Mapped[int] = mapped_column(Integer,default=1)
class Acceptance(Base):
    __tablename__='acceptances'
    __table_args__=(UniqueConstraint('program_id','merchant_id'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    program_id: Mapped[int] = mapped_column(ForeignKey('programs.id'))
    merchant_id: Mapped[int] = mapped_column(ForeignKey('merchants.id'))
class Card(Base):
    __tablename__='cards'
    id: Mapped[int] = mapped_column(primary_key=True)
    public_id: Mapped[str] = mapped_column(String(40),unique=True)
    program_id: Mapped[int] = mapped_column(ForeignKey('programs.id'))
    owner_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    original_minor: Mapped[int] = mapped_column(Integer)
    balance_minor: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(30),default='ACTIVE')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),default=lambda: datetime.now(timezone.utc))
class GiftOrder(Base):
    __tablename__='gift_orders'
    id: Mapped[int] = mapped_column(primary_key=True)
    order_code: Mapped[str] = mapped_column(String(45),unique=True)
    buyer_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    recipient_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    program_id: Mapped[int] = mapped_column(ForeignKey('programs.id'))
    amount_minor: Mapped[int] = mapped_column(Integer)
    message: Mapped[str] = mapped_column(String(300),default='')
    status: Mapped[str] = mapped_column(String(25),default='PENDING')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),default=lambda: datetime.now(timezone.utc))
class PaymentAttempt(Base):
    __tablename__='payment_attempts'
    __table_args__=(UniqueConstraint('order_id','attempt_number'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey('gift_orders.id'))
    attempt_number: Mapped[int] = mapped_column(Integer)
    provider: Mapped[str] = mapped_column(String(50),default='SANDBOX')
    status: Mapped[str] = mapped_column(String(20))
    reference: Mapped[str] = mapped_column(String(60),unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),default=lambda: datetime.now(timezone.utc))
class OrderCard(Base):
    __tablename__='order_cards'
    __table_args__=(UniqueConstraint('order_id'),UniqueConstraint('card_id'))
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey('gift_orders.id'))
    card_id: Mapped[int] = mapped_column(ForeignKey('cards.id'))
class Entry(Base):
    __tablename__='ledger_entries'
    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[str] = mapped_column(String(64))
    account: Mapped[str] = mapped_column(String(100))
    delta_minor: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),default=lambda: datetime.now(timezone.utc))
class Redemption(Base):
    __tablename__='redemptions'
    id: Mapped[int] = mapped_column(primary_key=True)
    card_id: Mapped[int] = mapped_column(ForeignKey('cards.id'))
    merchant_id: Mapped[int] = mapped_column(ForeignKey('merchants.id'))
    amount_minor: Mapped[int] = mapped_column(Integer)
    fee_minor: Mapped[int] = mapped_column(Integer)
    idempotency_key: Mapped[str] = mapped_column(String(100),unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),default=lambda: datetime.now(timezone.utc))
class Transfer(Base):
    __tablename__='gift_transfers'
    id: Mapped[int] = mapped_column(primary_key=True)
    card_id: Mapped[int] = mapped_column(ForeignKey('cards.id'))
    sender_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    receiver_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),default=lambda: datetime.now(timezone.utc))
class Audit(Base):
    __tablename__='audit_logs'
    id: Mapped[int] = mapped_column(primary_key=True)
    actor_id: Mapped[int] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(String(60))
    detail: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),default=lambda: datetime.now(timezone.utc))

Base.metadata.create_all(engine)
app = FastAPI(title='GiftBridge Ethiopia · Sandbox MVP',version='0.2.0',description='Only SIMULATED payments, card value, and settlement. Do not use with real money.')
app.add_middleware(CORSMiddleware,allow_origins=['http://localhost:8000','http://127.0.0.1:8000'],allow_credentials=True,allow_methods=['*'],allow_headers=['*'])

def db():
    with SessionLocal() as s: yield s

def hash_pw(p):
    salt=secrets.token_hex(16)
    return salt+':'+hashlib.pbkdf2_hmac('sha256',p.encode(),bytes.fromhex(salt),240000).hex()
def verify_pw(p,h):
    try:
        salt,digest=h.split(':',1)
        return secrets.compare_digest(hashlib.pbkdf2_hmac('sha256',p.encode(),bytes.fromhex(salt),240000).hex(),digest)
    except (ValueError,TypeError): return False

def _b64(data):return base64.urlsafe_b64encode(data).rstrip(b'=').decode()
def _unb64(s):return base64.urlsafe_b64decode(s+'='*((-len(s))%4))
def make_token(user_id):
    header=_b64(b'{"alg":"HS256","typ":"JWT"}')
    payload=_b64(json.dumps({'sub':str(user_id),'exp':int((datetime.now(timezone.utc)+timedelta(hours=8)).timestamp())},separators=(',',':')).encode())
    body=header+'.'+payload
    return body+'.'+_b64(hmac.new(JWT_SECRET.encode(),body.encode(),hashlib.sha256).digest())
def decode_token(token):
    try:
        header,payload,signature=token.split('.')
        if json.loads(_unb64(header)).get('alg')!='HS256':raise ValueError()
        expected=_b64(hmac.new(JWT_SECRET.encode(),(header+'.'+payload).encode(),hashlib.sha256).digest())
        if not secrets.compare_digest(expected,signature):raise ValueError()
        data=json.loads(_unb64(payload))
        if int(data['exp'])<=datetime.now(timezone.utc).timestamp():raise ValueError()
        return int(data['sub'])
    except (KeyError,ValueError,TypeError,OverflowError):raise HTTPException(401,'Invalid or expired token')
def current(authorization:Optional[str]=Header(None),s:Session=Depends(db)):
    if not authorization or not authorization.startswith('Bearer '):raise HTTPException(401,'Login required')
    u=s.get(User,decode_token(authorization[7:]))
    if not u:raise HTTPException(401,'Invalid user')
    return u
def admin(u=Depends(current)):
    if u.role!='admin':raise HTTPException(403,'Admin only')
    return u

def money(v:Decimal):
    if not v.is_finite() or v<=0 or v>Decimal('1000000') or v.as_tuple().exponent < -2:
        raise HTTPException(422,'Amount must be 0.01–1,000,000 ETB, maximum 2 decimal places')
    return int(v*100)
def etb(minor):return float(Decimal(minor)/100)
def entry(s,event,account,delta):s.add(Entry(event_id=event,account=account,delta_minor=delta))
def audit(s,u,action,detail):s.add(Audit(actor_id=u.id,action=action,detail=detail))
def card_out(c,s):
    p=s.get(Program,c.program_id)
    return {'id':c.id,'code':c.public_id,'program_id':p.id,'program':p.name,'kind':p.kind,'owner_id':c.owner_id,'original_etb':etb(c.original_minor),'balance_etb':etb(c.balance_minor),'status':c.status,'created_at':c.created_at.isoformat()}
def order_out(o,s):
    p=s.get(Program,o.program_id)
    oc=s.scalar(select(OrderCard).where(OrderCard.order_id==o.id))
    attempts=s.scalars(select(PaymentAttempt).where(PaymentAttempt.order_id==o.id).order_by(PaymentAttempt.id)).all()
    return {'id':o.id,'code':o.order_code,'status':o.status,'program':p.name,'kind':p.kind,
        'amount_etb':etb(o.amount_minor),'recipient':s.get(User,o.recipient_id).name,
        'recipient_phone':s.get(User,o.recipient_id).phone,'message':o.message,
        'card_code':s.get(Card,oc.card_id).public_id if oc else None,
        'attempts':[{'provider':a.provider,'status':a.status,'reference':a.reference} for a in attempts],
        'created_at':o.created_at.isoformat()}
class Register(BaseModel):
    name:str=Field(min_length=2,max_length=120)
    phone:str=Field(min_length=7,max_length=30)
    password:str=Field(min_length=8,max_length=100)
class Login(BaseModel):phone:str;password:str
class NewMerchant(BaseModel):name:str=Field(min_length=2,max_length=120)
class NewProgram(BaseModel):
    name:str=Field(min_length=2,max_length=120)
    kind:str
    merchant_id:Optional[int]=None
    accepted_merchant_ids:list[int]=Field(min_length=1)
class NewStaff(BaseModel):user_phone:str;merchant_id:int
class OrderIn(BaseModel):
    program_id:int
    amount_etb:Decimal
    recipient_phone:Optional[str]=None
    message:str=Field(default='',max_length=300)
class PaymentIn(BaseModel):
    outcome:str=Field(pattern='^(SUCCESS|FAILED)$')
    channel:str=Field(default='M-PESA (simulated)',max_length=60)
class Send(BaseModel):recipient_phone:str
class Redeem(BaseModel):
    card_code:str
    merchant_id:int
    amount_etb:Decimal
    idempotency_key:str=Field(min_length=8,max_length=100)

@app.post('/api/auth/register')
def register(body:Register,s:Session=Depends(db)):
    if s.scalar(select(User).where(User.phone==body.phone.strip())):raise HTTPException(409,'Phone already registered')
    u=User(name=body.name.strip(),phone=body.phone.strip(),password_hash=hash_pw(body.password),role='customer')
    s.add(u);s.commit()
    return {'id':u.id,'message':'Account created. You can sign in now.'}
@app.post('/api/auth/login')
def login(body:Login,s:Session=Depends(db)):
    u=s.scalar(select(User).where(User.phone==body.phone.strip()))
    if not u or not verify_pw(body.password,u.password_hash):raise HTTPException(401,'Invalid credentials')
    return {'access_token':make_token(u.id),'user':{'id':u.id,'name':u.name,'phone':u.phone,'role':u.role}}
@app.get('/api/me')
def me(u=Depends(current)):return {'id':u.id,'name':u.name,'phone':u.phone,'role':u.role}
@app.get('/api/merchants')
def merchants(s:Session=Depends(db)):
    return [{'id':m.id,'name':m.name,'status':m.status} for m in s.scalars(select(Merchant).where(Merchant.status=='ACTIVE').order_by(Merchant.id))]
@app.get('/api/programs')
def programs(s:Session=Depends(db)):
    return [{'id':p.id,'name':p.name,'kind':p.kind,'merchant_id':p.merchant_id,
      'accepted_merchant_ids':list(s.scalars(select(Acceptance.merchant_id).where(Acceptance.program_id==p.id)))}
      for p in s.scalars(select(Program).where(Program.active==1).order_by(Program.id))]
@app.post('/api/admin/merchants')
def new_merchant(body:NewMerchant,u=Depends(admin),s:Session=Depends(db)):
    name=body.name.strip()
    if not name:raise HTTPException(422,'Merchant name required')
    if s.scalar(select(Merchant).where(func.lower(Merchant.name)==name.lower())):raise HTTPException(409,'Merchant already exists')
    m=Merchant(name=name);s.add(m);s.flush();audit(s,u,'CREATE_MERCHANT',f'{m.id} {m.name}');s.commit()
    return {'id':m.id,'name':m.name,'message':'Merchant created successfully'}
@app.post('/api/admin/programs')
def new_program(body:NewProgram,u=Depends(admin),s:Session=Depends(db)):
    if body.kind not in ('MERCHANT_SPECIFIC','UNIVERSAL'):raise HTTPException(422,'Invalid gift type')
    mids=set(body.accepted_merchant_ids)
    if body.kind=='UNIVERSAL' and len(mids)<2:
        raise HTTPException(422,'Universal gift must accept at least two merchants')
    if body.kind=='MERCHANT_SPECIFIC' and (body.merchant_id is None or mids!={body.merchant_id}):
        raise HTTPException(422,'Merchant-specific gift must accept only its issuing merchant')
    for mid in mids:
        m=s.get(Merchant,mid)
        if not m or m.status!='ACTIVE':raise HTTPException(404,f'Active merchant {mid} not found')
    p=Program(name=body.name.strip(),kind=body.kind,merchant_id=body.merchant_id if body.kind=='MERCHANT_SPECIFIC' else None)
    s.add(p);s.flush()
    for mid in mids:s.add(Acceptance(program_id=p.id,merchant_id=mid))
    audit(s,u,'CREATE_PROGRAM',f'{p.id} {p.name}');s.commit()
    return {'id':p.id,'message':'Gift program published successfully'}
@app.post('/api/admin/staff')
def add_staff(body:NewStaff,u=Depends(admin),s:Session=Depends(db)):
    target=s.scalar(select(User).where(User.phone==body.user_phone.strip()))
    if not target:raise HTTPException(404,'User must register before being assigned as staff')
    if target.role=='admin':raise HTTPException(409,'Admin accounts do not need staff assignment')
    if not s.get(Merchant,body.merchant_id):raise HTTPException(404,'Merchant not found')
    if s.scalar(select(MerchantStaff).where(MerchantStaff.user_id==target.id,MerchantStaff.merchant_id==body.merchant_id)):
        raise HTTPException(409,'Already assigned to this merchant')
    s.add(MerchantStaff(user_id=target.id,merchant_id=body.merchant_id))
    target.role='merchant';audit(s,u,'ASSIGN_STAFF',f'{target.id} {body.merchant_id}');s.commit()
    return {'message':'Cashier assigned successfully'}
@app.get('/api/staff/merchants')
def staff_merchants(u=Depends(current),s:Session=Depends(db)):
    if u.role=='admin':return [{'id':m.id,'name':m.name} for m in s.scalars(select(Merchant).where(Merchant.status=='ACTIVE'))]
    return [{'id':m.id,'name':m.name} for m in s.scalars(select(Merchant).join(MerchantStaff,Merchant.id==MerchantStaff.merchant_id).where(MerchantStaff.user_id==u.id,Merchant.status=='ACTIVE'))]
@app.post('/api/orders')
def create_order(body:OrderIn,u=Depends(current),s:Session=Depends(db)):
    p=s.get(Program,body.program_id)
    if not p or p.active!=1:raise HTTPException(404,'Gift program not available')
    amt=money(body.amount_etb)
    receiver=u
    if body.recipient_phone and body.recipient_phone.strip()!=u.phone:
        receiver=s.scalar(select(User).where(User.phone==body.recipient_phone.strip()))
        if not receiver:raise HTTPException(404,'Recipient must create a GiftBridge account first')
    o=GiftOrder(order_code='GBO-'+secrets.token_hex(5).upper(),buyer_id=u.id,recipient_id=receiver.id,
                program_id=p.id,amount_minor=amt,message=body.message.strip(),status='PENDING')
    s.add(o);s.flush();audit(s,u,'CREATE_ORDER',o.order_code);s.commit()
    return order_out(o,s)
@app.get('/api/orders')
def my_orders(u=Depends(current),s:Session=Depends(db)):
    return [order_out(o,s) for o in s.scalars(select(GiftOrder).where(GiftOrder.buyer_id==u.id).order_by(GiftOrder.id.desc())).all()]
@app.get('/api/orders/{order_id}')
def get_order(order_id:int,u=Depends(current),s:Session=Depends(db)):
    o=s.get(GiftOrder,order_id)
    if not o or (o.buyer_id!=u.id and u.role!='admin'):raise HTTPException(404,'Order not found')
    return order_out(o,s)
@app.post('/api/orders/{order_id}/simulate-payment')
def simulate_payment(order_id:int,body:PaymentIn,u=Depends(current),s:Session=Depends(db)):
    """Internal sandbox action. Deliberately has NO real payment provider or gateway integration."""
    if os.getenv('ENABLE_DEMO_FUNDING','true').lower()!='true':raise HTTPException(403,'Sandbox payments disabled')
    o=s.get(GiftOrder,order_id)
    if not o or o.buyer_id!=u.id:raise HTTPException(404,'Order not found')
    if o.status=='PAID':
        result=order_out(o,s);result['message']='Already paid — no duplicate gift issued'
        return result
    if o.status!='PENDING':raise HTTPException(409,'Order not pending; use Retry for a failed payment')
    # Conditional DB update avoids two successful callbacks issuing twice.
    changed=s.execute(update(GiftOrder).where(GiftOrder.id==o.id,GiftOrder.status=='PENDING')
                      .values(status='PAID' if body.outcome=='SUCCESS' else 'FAILED'))
    if changed.rowcount!=1:
        s.rollback();raise HTTPException(409,'Payment already processed, refresh order history')
    sequence=(s.scalar(select(func.count()).select_from(PaymentAttempt).where(PaymentAttempt.order_id==o.id)) or 0)+1
    attempt=PaymentAttempt(order_id=o.id,attempt_number=sequence,provider=body.channel.strip(),
            status=body.outcome,reference='SIM-'+secrets.token_hex(8).upper())
    s.add(attempt)
    if body.outcome=='SUCCESS':
        c=Card(public_id='GB-'+secrets.token_hex(6).upper(),program_id=o.program_id,
            owner_id=o.recipient_id,original_minor=o.amount_minor,balance_minor=o.amount_minor,status='ACTIVE')
        s.add(c);s.flush();s.add(OrderCard(order_id=o.id,card_id=c.id))
        event='ISSUE-'+str(c.id)
        entry(s,event,'SIMULATED_FUNDS',o.amount_minor)
        entry(s,event,'GIFT_LIABILITY',-o.amount_minor)
        audit(s,u,'PAYMENT_SUCCESS',f'{o.order_code} {c.public_id}')
    else:audit(s,u,'PAYMENT_FAILED',o.order_code)
    s.commit()
    result=order_out(s.get(GiftOrder,o.id),s)
    result['message']='Payment successful! Your digital gift is ready.' if body.outcome=='SUCCESS' else 'Payment simulation failed. No gift was issued.'
    return result
@app.post('/api/orders/{order_id}/retry')
def retry_order(order_id:int,u=Depends(current),s:Session=Depends(db)):
    o=s.get(GiftOrder,order_id)
    if not o or o.buyer_id!=u.id:raise HTTPException(404,'Order not found')
    if o.status!='FAILED':raise HTTPException(409,'Only failed orders can be retried')
    o.status='PENDING';audit(s,u,'RETRY_PAYMENT',o.order_code);s.commit()
    return order_out(o,s)
@app.get('/api/wallet')
def wallet(u=Depends(current),s:Session=Depends(db)):
    return [card_out(c,s) for c in s.scalars(select(Card).where(Card.owner_id==u.id).order_by(Card.id.desc())).all()]
@app.get('/api/cards/{card_id}/history')
def card_history(card_id:int,u=Depends(current),s:Session=Depends(db)):
    c=s.get(Card,card_id)
    if not c or (c.owner_id!=u.id and u.role!='admin'):raise HTTPException(404,'Card not found')
    result=[]
    for r in s.scalars(select(Redemption).where(Redemption.card_id==card_id)):
        result.append({'action':'REDEEMED','amount_etb':etb(r.amount_minor),'detail':s.get(Merchant,r.merchant_id).name,'at':r.created_at.isoformat()})
    for t in s.scalars(select(Transfer).where(Transfer.card_id==card_id)):
        result.append({'action':'SENT','amount_etb':0,'detail':'Gift ownership transfer','at':t.created_at.isoformat()})
    return sorted(result,key=lambda x:x['at'],reverse=True)
@app.post('/api/cards/{card_id}/send')
def send(card_id:int,body:Send,u=Depends(current),s:Session=Depends(db)):
    c=s.scalar(select(Card).where(Card.id==card_id).with_for_update())
    if not c or c.owner_id!=u.id:raise HTTPException(404,'Card not found in your wallet')
    if c.status not in ('ACTIVE','PARTIALLY_REDEEMED'):raise HTTPException(409,'Gift is no longer transferable')
    target=s.scalar(select(User).where(User.phone==body.recipient_phone.strip()))
    if not target:raise HTTPException(404,'Recipient must register first')
    if target.id==u.id:raise HTTPException(422,'Cannot send to yourself')
    c.owner_id=target.id
    s.add(Transfer(card_id=c.id,sender_id=u.id,receiver_id=target.id))
    audit(s,u,'SEND_GIFT',f'{c.public_id} -> {target.id}');s.commit()
    return {'message':'Gift sent successfully!','recipient':target.name}
@app.post('/api/redemptions')
def redeem(body:Redeem,u=Depends(current),s:Session=Depends(db)):
    if u.role not in ('admin','merchant'):raise HTTPException(403,'Only a demo cashier or admin can redeem gifts')
    if u.role=='merchant' and not s.scalar(select(MerchantStaff).where(MerchantStaff.user_id==u.id,MerchantStaff.merchant_id==body.merchant_id)):
        raise HTTPException(403,'You are not assigned to this merchant')
    amount=money(body.amount_etb)
    existing=s.scalar(select(Redemption).where(Redemption.idempotency_key==body.idempotency_key))
    if existing:
        if existing.merchant_id!=body.merchant_id or existing.amount_minor!=amount or s.get(Card,existing.card_id).public_id!=body.card_code.strip():
            raise HTTPException(409,'Idempotency key already used for a different redemption')
        return {'id':existing.id,'status':'ALREADY_PROCESSED','balance_etb':etb(s.get(Card,existing.card_id).balance_minor)}
    c=s.scalar(select(Card).where(Card.public_id==body.card_code.strip()).with_for_update())
    if not c:raise HTTPException(404,'Card not found')
    merchant=s.get(Merchant,body.merchant_id)
    if not merchant or merchant.status!='ACTIVE':raise HTTPException(404,'Merchant not active')
    allowed=s.scalar(select(Acceptance).where(Acceptance.program_id==c.program_id,Acceptance.merchant_id==body.merchant_id))
    if not allowed:raise HTTPException(403,'This gift cannot be redeemed at that merchant')
    if c.status not in ('ACTIVE','PARTIALLY_REDEEMED') or c.balance_minor<amount:
        raise HTTPException(409,'Insufficient balance or inactive gift')
    # SQLite demo does not implement full concurrent-lock semantics; production needs PostgreSQL and review.
    c.balance_minor-=amount;c.status='FULLY_REDEEMED' if c.balance_minor==0 else 'PARTIALLY_REDEEMED'
    fee=amount*3//100
    r=Redemption(card_id=c.id,merchant_id=body.merchant_id,amount_minor=amount,fee_minor=fee,idempotency_key=body.idempotency_key)
    s.add(r);s.flush();event='REDEEM-'+str(r.id)
    entry(s,event,'GIFT_LIABILITY',amount)
    entry(s,event,'MERCHANT_PAYABLE:'+str(body.merchant_id),-(amount-fee))
    entry(s,event,'PLATFORM_FEE',-fee)
    audit(s,u,'REDEEM',f'{c.public_id} {amount}')
    s.commit()
    return {'id':r.id,'status':'CAPTURED','balance_etb':etb(c.balance_minor),'merchant_payable_etb':etb(amount-fee)}
@app.get('/api/admin/overview')
def overview(u=Depends(admin),s:Session=Depends(db)):
    return {'merchants':s.scalar(select(func.count()).select_from(Merchant)),
      'programs':s.scalar(select(func.count()).select_from(Program)),
      'orders':s.scalar(select(func.count()).select_from(GiftOrder)),
      'paid_orders':s.scalar(select(func.count()).select_from(GiftOrder).where(GiftOrder.status=='PAID')),
      'cards_issued':s.scalar(select(func.count()).select_from(Card)),
      'outstanding_etb':etb(s.scalar(select(func.coalesce(func.sum(Card.balance_minor),0))) or 0),
      'redeemed_etb':etb(s.scalar(select(func.coalesce(func.sum(Redemption.amount_minor),0))) or 0),
      'ledger_unbalanced_events':len([r for r in s.execute(select(Entry.event_id,func.sum(Entry.delta_minor)).group_by(Entry.event_id)) if r[1]!=0])}
@app.get('/api/admin/settlements')
def settlements(u=Depends(admin),s:Session=Depends(db)):
    result=[]
    for m in s.scalars(select(Merchant).order_by(Merchant.id)):
        rs=s.scalars(select(Redemption).where(Redemption.merchant_id==m.id)).all()
        result.append({'merchant':m.name,'gross_etb':etb(sum(r.amount_minor for r in rs)),
         'fee_etb':etb(sum(r.fee_minor for r in rs)),
         'payable_etb':etb(sum(r.amount_minor-r.fee_minor for r in rs)),
         'status':'SIMULATED · NOT SETTLED'})
    return result
@app.get('/api/health')
def health():return {'status':'ok','mode':'SIMULATION','version':'0.2.0'}
app.mount('/assets',StaticFiles(directory=str(ROOT/'frontend')),name='assets')
@app.get('/')
def home():return FileResponse(ROOT/'frontend'/'index.html')
