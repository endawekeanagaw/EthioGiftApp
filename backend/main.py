"""GiftBridge demonstration MVP. NOT suitable for live customer funds."""
import os
import secrets
import hashlib
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional
from fastapi import FastAPI, Depends, HTTPException, Header
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, String, Integer, DateTime, ForeignKey, Numeric, UniqueConstraint, select, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker, Session
from jose import jwt, JWTError

DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///./giftbridge.db')
JWT_SECRET = os.getenv('JWT_SECRET', 'CHANGE_ME_LOCAL_DEMO_ONLY')
if os.getenv('APP_ENV') == 'production' and JWT_SECRET == 'CHANGE_ME_LOCAL_DEMO_ONLY':
    raise RuntimeError('Set JWT_SECRET before production')
engine = create_engine(DATABASE_URL, connect_args={'check_same_thread': False} if DATABASE_URL.startswith('sqlite') else {}, pool_pre_ping=True)
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
class Program(Base):
    __tablename__='programs'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(30))
    merchant_id: Mapped[Optional[int]] = mapped_column(ForeignKey('merchants.id'), nullable=True)
    active: Mapped[int] = mapped_column(Integer, default=1)
class Acceptance(Base):
    __tablename__='acceptances'
    __table_args__=(UniqueConstraint('program_id','merchant_id'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    program_id: Mapped[int] = mapped_column(ForeignKey('programs.id'))
    merchant_id: Mapped[int] = mapped_column(ForeignKey('merchants.id'))
class Card(Base):
    __tablename__='cards'
    id: Mapped[int] = mapped_column(primary_key=True)
    public_id: Mapped[str] = mapped_column(String(40), unique=True)
    program_id: Mapped[int] = mapped_column(ForeignKey('programs.id'))
    owner_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    original_minor: Mapped[int] = mapped_column(Integer)
    balance_minor: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(30), default='ACTIVE')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
class Entry(Base):
    __tablename__='ledger_entries'
    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[str] = mapped_column(String(64))
    account: Mapped[str] = mapped_column(String(100))
    delta_minor: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
class Redemption(Base):
    __tablename__='redemptions'
    id: Mapped[int] = mapped_column(primary_key=True)
    card_id: Mapped[int] = mapped_column(ForeignKey('cards.id'))
    merchant_id: Mapped[int] = mapped_column(ForeignKey('merchants.id'))
    amount_minor: Mapped[int] = mapped_column(Integer)
    fee_minor: Mapped[int] = mapped_column(Integer)
    idempotency_key: Mapped[str] = mapped_column(String(100), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
class Audit(Base):
    __tablename__='audit_logs'
    id: Mapped[int] = mapped_column(primary_key=True)
    actor_id: Mapped[int] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(String(60))
    detail: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

Base.metadata.create_all(engine)
app = FastAPI(title='GiftBridge Ethiopia MVP', version='0.1.0', description='DEMO ONLY: simulated funding, no live payments')
app.add_middleware(CORSMiddleware, allow_origins=['http://localhost:8000','http://127.0.0.1:8000'], allow_credentials=True, allow_methods=['*'], allow_headers=['*'])

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

def current(authorization: Optional[str]=Header(None), s:Session=Depends(db)):
    if not authorization or not authorization.startswith('Bearer '): raise HTTPException(401,'Login required')
    try: uid=int(jwt.decode(authorization[7:],JWT_SECRET,algorithms=['HS256'])['sub'])
    except (JWTError,ValueError,KeyError): raise HTTPException(401,'Invalid token')
    user=s.get(User,uid)
    if not user: raise HTTPException(401,'Invalid user')
    return user

def admin(user=Depends(current)):
    if user.role!='admin': raise HTTPException(403,'Admin only')
    return user

def money(v:Decimal):
    if v<=0 or v>Decimal('1000000') or v.as_tuple().exponent < -2: raise HTTPException(422,'Amount must be positive, max 1,000,000 ETB, 2 decimal places')
    return int(v*100)

def entry(s,event,account,delta): s.add(Entry(event_id=event,account=account,delta_minor=delta))
def audit(s,user,action,detail): s.add(Audit(actor_id=user.id,action=action,detail=detail))
def card_out(c,s):
    p=s.get(Program,c.program_id)
    return {'id':c.id,'code':c.public_id,'program':p.name,'kind':p.kind,'owner_id':c.owner_id,'original_etb':c.original_minor/100,'balance_etb':c.balance_minor/100,'status':c.status}

class Register(BaseModel):
    name:str=Field(min_length=2,max_length=120)
    phone:str=Field(min_length=7,max_length=30)
    password:str=Field(min_length=8,max_length=100)
class Login(BaseModel):
    phone:str
    password:str
class Issue(BaseModel):
    program_id:int
    amount_etb:Decimal
    recipient_phone:Optional[str]=None
class Redeem(BaseModel):
    card_code:str
    merchant_id:int
    amount_etb:Decimal
    idempotency_key:str=Field(min_length=8,max_length=100)
class Send(BaseModel):
    recipient_phone:str
class NewMerchant(BaseModel):
    name:str=Field(min_length=2,max_length=120)
class NewProgram(BaseModel):
    name:str
    kind:str
    merchant_id:Optional[int]=None
    accepted_merchant_ids:list[int]=[]

@app.post('/api/auth/register')
def register(body:Register,s:Session=Depends(db)):
    if s.scalar(select(User).where(User.phone==body.phone)): raise HTTPException(409,'Phone already registered')
    u=User(name=body.name,phone=body.phone,password_hash=hash_pw(body.password))
    s.add(u);s.commit()
    return {'id':u.id,'message':'Registered'}
@app.post('/api/auth/login')
def login(body:Login,s:Session=Depends(db)):
    u=s.scalar(select(User).where(User.phone==body.phone))
    if not u or not verify_pw(body.password,u.password_hash): raise HTTPException(401,'Invalid credentials')
    token=jwt.encode({'sub':str(u.id),'exp':datetime.now(timezone.utc)+timedelta(hours=8)},JWT_SECRET,algorithm='HS256')
    return {'access_token':token,'user':{'id':u.id,'name':u.name,'role':u.role}}
@app.get('/api/me')
def me(u=Depends(current)): return {'id':u.id,'name':u.name,'phone':u.phone,'role':u.role}
@app.get('/api/merchants')
def merchants(s:Session=Depends(db)):
    return [{'id':m.id,'name':m.name} for m in s.scalars(select(Merchant).where(Merchant.status=='ACTIVE')).all()]
@app.get('/api/programs')
def programs(s:Session=Depends(db)):
    return [{'id':p.id,'name':p.name,'kind':p.kind,'merchant_id':p.merchant_id,'accepted_merchant_ids':list(s.scalars(select(Acceptance.merchant_id).where(Acceptance.program_id==p.id)))} for p in s.scalars(select(Program).where(Program.active==1)).all()]
@app.post('/api/admin/merchants')
def new_merchant(body:NewMerchant,u=Depends(admin),s:Session=Depends(db)):
    if s.scalar(select(Merchant).where(Merchant.name==body.name)): raise HTTPException(409,'Already exists')
    m=Merchant(name=body.name);s.add(m);s.flush();audit(s,u,'CREATE_MERCHANT',str(m.id));s.commit();return {'id':m.id}
@app.post('/api/admin/programs')
def new_program(body:NewProgram,u=Depends(admin),s:Session=Depends(db)):
    if body.kind not in ('MERCHANT_SPECIFIC','UNIVERSAL'): raise HTTPException(422,'Invalid kind')
    if body.kind=='MERCHANT_SPECIFIC' and (not body.merchant_id or body.accepted_merchant_ids!=[body.merchant_id]): raise HTTPException(422,'Merchant program must accept exactly its merchant')
    if not body.accepted_merchant_ids: raise HTTPException(422,'At least one accepting merchant required')
    for mid in body.accepted_merchant_ids:
        if not s.get(Merchant,mid): raise HTTPException(404,f'Merchant {mid} not found')
    p=Program(name=body.name,kind=body.kind,merchant_id=body.merchant_id if body.kind=='MERCHANT_SPECIFIC' else None)
    s.add(p);s.flush()
    for mid in set(body.accepted_merchant_ids):s.add(Acceptance(program_id=p.id,merchant_id=mid))
    audit(s,u,'CREATE_PROGRAM',str(p.id));s.commit();return {'id':p.id}
@app.post('/api/demo/issue')
def demo_issue(body:Issue,u=Depends(current),s:Session=Depends(db)):
    """Simulates a confirmed payment. Never expose this endpoint in production."""
    if os.getenv('ENABLE_DEMO_FUNDING','true').lower()!='true': raise HTTPException(403,'Demo funding disabled')
    p=s.get(Program,body.program_id)
    if not p or not p.active: raise HTTPException(404,'Program not found')
    amt=money(body.amount_etb)
    recipient=u
    if body.recipient_phone:
        recipient=s.scalar(select(User).where(User.phone==body.recipient_phone))
        if not recipient: raise HTTPException(404,'Recipient must register first')
    c=Card(public_id='GB-'+secrets.token_hex(6).upper(),program_id=p.id,owner_id=recipient.id,original_minor=amt,balance_minor=amt)
    s.add(c);s.flush();event='ISSUE-'+str(c.id)
    entry(s,event,'DEMO_FUNDS_RECEIVED',amt)
    entry(s,event,'GIFT_LIABILITY',-amt)
    audit(s,u,'DEMO_ISSUE',c.public_id)
    s.commit();return card_out(c,s)
@app.get('/api/wallet')
def wallet(u=Depends(current),s:Session=Depends(db)):
    return [card_out(c,s) for c in s.scalars(select(Card).where(Card.owner_id==u.id).order_by(Card.id.desc())).all()]
@app.post('/api/cards/{card_id}/send')
def send(card_id:int,body:Send,u=Depends(current),s:Session=Depends(db)):
    c=s.get(Card,card_id)
    if not c or c.owner_id!=u.id: raise HTTPException(404,'Card not found')
    if c.status not in ('ACTIVE','PARTIALLY_REDEEMED'): raise HTTPException(409,'Card not transferable')
    target=s.scalar(select(User).where(User.phone==body.recipient_phone))
    if not target: raise HTTPException(404,'Recipient must register first')
    if target.id==u.id: raise HTTPException(422,'Cannot send to yourself')
    c.owner_id=target.id;audit(s,u,'SEND_GIFT',f'{c.public_id} -> {target.id}');s.commit();return {'message':'Gift transferred','recipient':target.name}
@app.post('/api/redemptions')
def redeem(body:Redeem,u=Depends(current),s:Session=Depends(db)):
    """Demo cashier operation. Production requires authenticated merchant-scoped cashier role and PostgreSQL locking."""
    existing=s.scalar(select(Redemption).where(Redemption.idempotency_key==body.idempotency_key))
    if existing: return {'id':existing.id,'status':'ALREADY_PROCESSED','balance_etb':s.get(Card,existing.card_id).balance_minor/100}
    amount=money(body.amount_etb)
    c=s.scalar(select(Card).where(Card.public_id==body.card_code).with_for_update())
    if not c: raise HTTPException(404,'Card not found')
    if not s.get(Merchant,body.merchant_id): raise HTTPException(404,'Merchant not found')
    allowed=s.scalar(select(Acceptance).where(Acceptance.program_id==c.program_id,Acceptance.merchant_id==body.merchant_id))
    if not allowed: raise HTTPException(403,'Merchant not authorized for this gift')
    if c.status not in ('ACTIVE','PARTIALLY_REDEEMED') or c.balance_minor<amount: raise HTTPException(409,'Insufficient balance or inactive card')
    c.balance_minor-=amount;c.status='FULLY_REDEEMED' if c.balance_minor==0 else 'PARTIALLY_REDEEMED'
    fee=amount*3//100
    r=Redemption(card_id=c.id,merchant_id=body.merchant_id,amount_minor=amount,fee_minor=fee,idempotency_key=body.idempotency_key)
    s.add(r);s.flush();event='REDEEM-'+str(r.id)
    entry(s,event,'GIFT_LIABILITY',amount)
    entry(s,event,'MERCHANT_PAYABLE:'+str(body.merchant_id),-(amount-fee))
    entry(s,event,'PLATFORM_FEE_PAYABLE',-fee)
    audit(s,u,'DEMO_REDEEM',f'{c.public_id} {amount}')
    s.commit();return {'id':r.id,'status':'CAPTURED','balance_etb':c.balance_minor/100,'merchant_payable_etb':(amount-fee)/100}
@app.get('/api/admin/overview')
def overview(u=Depends(admin),s:Session=Depends(db)):
    cards=s.scalars(select(Card)).all();redemptions=s.scalars(select(Redemption)).all()
    return {'cards_issued':len(cards),'outstanding_etb':sum(c.balance_minor for c in cards)/100,'redeemed_etb':sum(r.amount_minor for r in redemptions)/100,'redemption_count':len(redemptions),'ledger_unbalanced_events':len([event for event,total in s.execute(select(Entry.event_id,func.sum(Entry.delta_minor)).group_by(Entry.event_id)).all() if total!=0])}
@app.get('/api/admin/settlements')
def settlements(u=Depends(admin),s:Session=Depends(db)):
    result=[]
    for m in s.scalars(select(Merchant)).all():
        rs=s.scalars(select(Redemption).where(Redemption.merchant_id==m.id)).all()
        result.append({'merchant':m.name,'gross_etb':sum(r.amount_minor for r in rs)/100,'fee_etb':sum(r.fee_minor for r in rs)/100,'payable_etb':sum(r.amount_minor-r.fee_minor for r in rs)/100,'status':'DEMO_NOT_PAID'})
    return result
@app.get('/api/health')
def health():return {'status':'ok','mode':'DEMO'}
app.mount('/assets',StaticFiles(directory='frontend'),name='assets')
@app.get('/')
def home():return FileResponse('frontend/index.html')
