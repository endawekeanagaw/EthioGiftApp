"""GiftBridge Ethiopia v0.6 — sandbox payment adapter, reconciliation and fraud triage."""
import base64
import hashlib
import hmac
import json
import io
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

class GiftPresentation(Base):
    __tablename__='gift_presentations'
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey('gift_orders.id'), unique=True)
    occasion: Mapped[str] = mapped_column(String(35), default='JUST_BECAUSE')
    design: Mapped[str] = mapped_column(String(35), default='emerald')
    sender_name: Mapped[str] = mapped_column(String(120), default='')

class GiftNotification(Base):
    __tablename__='gift_notifications'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    title: Mapped[str] = mapped_column(String(150))
    body: Mapped[str] = mapped_column(String(350))
    card_id: Mapped[Optional[int]] = mapped_column(ForeignKey('cards.id'),nullable=True)
    event_type: Mapped[str] = mapped_column(String(30))
    read_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True),nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),default=lambda: datetime.now(timezone.utc))

class CardRedeemPass(Base):
    __tablename__='card_redeem_passes'
    id: Mapped[int] = mapped_column(primary_key=True)
    card_id: Mapped[int] = mapped_column(ForeignKey('cards.id'))
    owner_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    secret_digest: Mapped[str] = mapped_column(String(128))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer,default=0)
    consumed: Mapped[int] = mapped_column(Integer,default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),default=lambda: datetime.now(timezone.utc))

class ProgramAppearance(Base):
    """Optional storefront metadata. Separate table preserves the older v0.2/v0.3 programs schema."""
    __tablename__ = 'program_appearances'
    program_id: Mapped[int] = mapped_column(ForeignKey('programs.id'), primary_key=True)
    category: Mapped[str] = mapped_column(String(30), default='SHOPPING')
    description: Mapped[str] = mapped_column(String(240), default='')
    emoji: Mapped[str] = mapped_column(String(12), default='🎁')

class ProgramFavorite(Base):
    __tablename__ = 'program_favorites'
    __table_args__ = (UniqueConstraint('user_id', 'program_id'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    program_id: Mapped[int] = mapped_column(ForeignKey('programs.id'))

class MerchantBranch(Base):
    __tablename__='merchant_branches'
    id: Mapped[int] = mapped_column(primary_key=True)
    merchant_id: Mapped[int] = mapped_column(ForeignKey('merchants.id'))
    name: Mapped[str] = mapped_column(String(100))
    city: Mapped[str] = mapped_column(String(100),default='Addis Ababa')
    active: Mapped[int] = mapped_column(Integer,default=1)

class MerchantApplication(Base):
    __tablename__ = 'merchant_applications'
    id: Mapped[int] = mapped_column(primary_key=True)
    applicant_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    business_name: Mapped[str] = mapped_column(String(120))
    category: Mapped[str] = mapped_column(String(40))
    city: Mapped[str] = mapped_column(String(100))
    contact_phone: Mapped[str] = mapped_column(String(30))
    description: Mapped[str] = mapped_column(String(350), default='')
    status: Mapped[str] = mapped_column(String(20), default='PENDING')
    review_note: Mapped[str] = mapped_column(String(350), default='')
    merchant_id: Mapped[Optional[int]] = mapped_column(ForeignKey('merchants.id'), nullable=True)
    reviewed_by: Mapped[Optional[int]] = mapped_column(ForeignKey('users.id'), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

class MerchantMembership(Base):
    __tablename__ = 'merchant_memberships'
    __table_args__ = (UniqueConstraint('merchant_id', 'user_id'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    merchant_id: Mapped[int] = mapped_column(ForeignKey('merchants.id'))
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    role: Mapped[str] = mapped_column(String(20))  # OWNER, MANAGER or CASHIER
    branch_id: Mapped[Optional[int]] = mapped_column(ForeignKey('merchant_branches.id'), nullable=True)
    active: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class RedemptionLocation(Base):
    __tablename__ = 'redemption_locations'
    redemption_id: Mapped[int] = mapped_column(ForeignKey('redemptions.id'), primary_key=True)
    branch_id: Mapped[Optional[int]] = mapped_column(ForeignKey('merchant_branches.id'), nullable=True)
    cashier_id: Mapped[int] = mapped_column(ForeignKey('users.id'))


# v0.6 additive schema: safe for existing v0.5 SQLite/PostgreSQL databases.
class PaymentIntent(Base):
    __tablename__ = 'payment_intents'
    __table_args__ = (UniqueConstraint('buyer_id','idempotency_key'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey('gift_orders.id'))
    buyer_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    idempotency_key: Mapped[str] = mapped_column(String(100))
    provider: Mapped[str] = mapped_column(String(40))
    provider_reference: Mapped[str] = mapped_column(String(70), unique=True)
    amount_minor: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default='PENDING')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda:datetime.now(timezone.utc))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

class PaymentEvent(Base):
    __tablename__ = 'payment_events'
    id: Mapped[int] = mapped_column(primary_key=True)
    event_reference: Mapped[str] = mapped_column(String(85), unique=True)
    intent_id: Mapped[int] = mapped_column(ForeignKey('payment_intents.id'))
    outcome: Mapped[str] = mapped_column(String(16))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))

class FraudAlert(Base):
    __tablename__ = 'fraud_alerts'
    id: Mapped[int] = mapped_column(primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(150), unique=True)
    control_id: Mapped[str] = mapped_column(String(20))
    severity: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(20), default='OPEN')
    title: Mapped[str] = mapped_column(String(170))
    detail: Mapped[str] = mapped_column(String(500))
    note: Mapped[str] = mapped_column(String(350), default='')
    reviewed_by: Mapped[Optional[int]] = mapped_column(ForeignKey('users.id'),nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True),nullable=True)

class LoginGuard(Base):
    __tablename__ = 'login_guards'
    phone: Mapped[str] = mapped_column(String(30),primary_key=True)
    failure_count: Mapped[int] = mapped_column(Integer,default=0)
    first_failure_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True),nullable=True)
    locked_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True),nullable=True)

Base.metadata.create_all(engine)
app = FastAPI(title='GiftBridge Ethiopia · Sandbox MVP',version='0.6.0',description='Only SIMULATED payments, card value, and settlement. Do not use with real money.')
app.add_middleware(CORSMiddleware,allow_origins=['http://localhost:8000','http://127.0.0.1:8000'],allow_credentials=True,allow_methods=['*'],allow_headers=['*'])

@app.middleware('http')
async def safety_headers(request, call_next):
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['Permissions-Policy'] = 'camera=(self), microphone=(), geolocation=()'
    if request.url.path.startswith('/api/'):
        response.headers['Cache-Control'] = 'no-store'
    return response


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
def presentation(s,order_id):
    item=s.scalar(select(GiftPresentation).where(GiftPresentation.order_id==order_id))
    return {'occasion':item.occasion,'design':item.design,'sender_name':item.sender_name} if item else {'occasion':'JUST_BECAUSE','design':'emerald','sender_name':''}

def card_out(c,s):
    p=s.get(Program,c.program_id)
    link=s.scalar(select(OrderCard).where(OrderCard.card_id==c.id))
    o=s.get(GiftOrder,link.order_id) if link else None
    details=presentation(s,o.id) if o else {'occasion':'JUST_BECAUSE','design':'emerald','sender_name':''}
    sender=s.get(User,o.buyer_id) if o else None
    return {'id':c.id,'sender':details['sender_name'] or (sender.name if sender else 'Someone special'),
        'message':o.message if o else '',**details,'code':c.public_id,'program_id':p.id,'program':p.name,'kind':p.kind,'owner_id':c.owner_id,'original_etb':etb(c.original_minor),'balance_etb':etb(c.balance_minor),'status':c.status,'created_at':c.created_at.isoformat()}
def order_out(o,s):
    p=s.get(Program,o.program_id)
    oc=s.scalar(select(OrderCard).where(OrderCard.order_id==o.id))
    attempts=s.scalars(select(PaymentAttempt).where(PaymentAttempt.order_id==o.id).order_by(PaymentAttempt.id)).all()
    return {'id':o.id,'code':o.order_code,'status':o.status,'program':p.name,'kind':p.kind,
        'amount_etb':etb(o.amount_minor),'recipient':s.get(User,o.recipient_id).name,
        'recipient_phone':s.get(User,o.recipient_id).phone,'message':o.message,**presentation(s,o.id),
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
    category:str=Field(default='SHOPPING',max_length=30)
    description:str=Field(default='',max_length=240)
    emoji:str=Field(default='🎁',max_length=12)
    kind:str
    merchant_id:Optional[int]=None
    accepted_merchant_ids:list[int]=Field(min_length=1)
class NewStaff(BaseModel):user_phone:str;merchant_id:int
class OrderIn(BaseModel):
    program_id:int
    amount_etb:Decimal
    recipient_phone:Optional[str]=None
    message:str=Field(default='',max_length=300)
    occasion:str=Field(default='JUST_BECAUSE',max_length=35)
    design:str=Field(default='emerald',max_length=35)
    sender_name:str=Field(default='',max_length=120)
class PaymentIn(BaseModel):
    outcome:str=Field(pattern='^(SUCCESS|FAILED)$')
    channel:str=Field(default='M-PESA (simulated)',max_length=60)
class Send(BaseModel):recipient_phone:str
class Redeem(BaseModel):
    card_code:str
    merchant_id:int
    amount_etb:Decimal
    idempotency_key:str=Field(min_length=8,max_length=100)
    redeem_pin:str=Field(min_length=8,max_length=8,pattern=r'^\d{8}$')
    branch_id:Optional[int]=None

@app.post('/api/auth/register')
def register(body:Register,s:Session=Depends(db)):
    if s.scalar(select(User).where(User.phone==body.phone.strip())):raise HTTPException(409,'Phone already registered')
    u=User(name=body.name.strip(),phone=body.phone.strip(),password_hash=hash_pw(body.password),role='customer')
    s.add(u);s.commit()
    return {'id':u.id,'message':'Account created. You can sign in now.'}
@app.post('/api/auth/login')
def login(body:Login,s:Session=Depends(db)):
    phone=body.phone.strip()
    now=datetime.now(timezone.utc)
    guard=s.get(LoginGuard,phone)
    def aware(x):return x.replace(tzinfo=timezone.utc) if x and x.tzinfo is None else x
    if guard and guard.locked_until and aware(guard.locked_until)>now:
        raise HTTPException(429,'Too many attempts. Try again in 15 minutes.')
    u=s.scalar(select(User).where(User.phone==phone))
    if not u or not verify_pw(body.password,u.password_hash):
        if not guard:guard=LoginGuard(phone=phone);s.add(guard)
        if not guard.first_failure_at or aware(guard.first_failure_at)<now-timedelta(minutes=15):
            guard.failure_count=0;guard.first_failure_at=now
        guard.failure_count+=1
        if guard.failure_count>=5:guard.locked_until=now+timedelta(minutes=15)
        s.commit()
        raise HTTPException(401,'Invalid credentials')
    if guard:
        s.delete(guard);s.commit()
    return {'access_token':make_token(u.id),'user':{'id':u.id,'name':u.name,'phone':u.phone,'role':u.role}}
@app.get('/api/me')
def me(u=Depends(current)):return {'id':u.id,'name':u.name,'phone':u.phone,'role':u.role}
@app.get('/api/merchants')
def merchants(s:Session=Depends(db)):
    return [{'id':m.id,'name':m.name,'status':m.status} for m in s.scalars(select(Merchant).where(Merchant.status=='ACTIVE').order_by(Merchant.id))]
GIFT_CATEGORIES = ('SHOPPING', 'FOOD', 'EXPERIENCES', 'BEAUTY', 'BOOKS', 'UNIVERSAL')

@app.get('/api/programs')
def programs(s:Session=Depends(db)):
    results=[]
    for p in s.scalars(select(Program).where(Program.active==1).order_by(Program.id)):
        appearance=s.get(ProgramAppearance,p.id)
        results.append({'id':p.id,'name':p.name,'kind':p.kind,'merchant_id':p.merchant_id,
          'accepted_merchant_ids':list(s.scalars(select(Acceptance.merchant_id).where(Acceptance.program_id==p.id))),
          'category':appearance.category if appearance else ('UNIVERSAL' if p.kind=='UNIVERSAL' else 'SHOPPING'),
          'description':appearance.description if appearance else '',
          'emoji':appearance.emoji if appearance else ('✨' if p.kind=='UNIVERSAL' else '🎁')})
    return results

@app.get('/api/favorites')
def favorites(u=Depends(current),s:Session=Depends(db)):
    return {'program_ids':list(s.scalars(select(ProgramFavorite.program_id).where(ProgramFavorite.user_id==u.id)))}

@app.post('/api/favorites/{program_id}')
def add_favorite(program_id:int,u=Depends(current),s:Session=Depends(db)):
    p=s.get(Program,program_id)
    if not p or p.active!=1:raise HTTPException(404,'Gift program not available')
    existing=s.scalar(select(ProgramFavorite).where(ProgramFavorite.user_id==u.id,ProgramFavorite.program_id==program_id))
    if not existing:
        s.add(ProgramFavorite(user_id=u.id,program_id=program_id));s.commit()
    return {'favorite':True,'program_id':program_id}

@app.delete('/api/favorites/{program_id}')
def remove_favorite(program_id:int,u=Depends(current),s:Session=Depends(db)):
    favorite=s.scalar(select(ProgramFavorite).where(ProgramFavorite.user_id==u.id,ProgramFavorite.program_id==program_id))
    if favorite:
        s.delete(favorite);s.commit()
    return {'favorite':False,'program_id':program_id}
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
    if body.category not in GIFT_CATEGORIES:raise HTTPException(422,'Invalid gift category')
    if not body.name.strip():raise HTTPException(422,'Program name required')
    p=Program(name=body.name.strip(),kind=body.kind,merchant_id=body.merchant_id if body.kind=='MERCHANT_SPECIFIC' else None)
    s.add(p);s.flush()
    s.add(ProgramAppearance(program_id=p.id,category=body.category,
        description=body.description.strip(),emoji=body.emoji.strip() or '🎁'))
    for mid in mids:s.add(Acceptance(program_id=p.id,merchant_id=mid))
    audit(s,u,'CREATE_PROGRAM',f'{p.id} {p.name}');s.commit()
    return {'id':p.id,'message':'Gift program published successfully'}
def membership(s:Session, user_id:int, merchant_id:int):
    return s.scalar(select(MerchantMembership).where(MerchantMembership.user_id==user_id,
        MerchantMembership.merchant_id==merchant_id, MerchantMembership.active==1))

def has_merchant_role(u:User,s:Session,merchant_id:int,roles:tuple[str,...]=('OWNER','MANAGER','CASHIER')):
    if u.role=='admin':return True
    member=membership(s,u.id,merchant_id)
    if member:return member.role in roles
    # An explicitly disabled membership must not be bypassed through legacy cashier grants.
    disabled=s.scalar(select(MerchantMembership).where(MerchantMembership.user_id==u.id,
        MerchantMembership.merchant_id==merchant_id, MerchantMembership.active==0))
    if disabled:return False
    # Old v0.2–0.4 cashier records remain valid for POS access and legacy reports.
    return 'CASHIER' in roles and s.scalar(select(MerchantStaff.id).where(
        MerchantStaff.user_id==u.id, MerchantStaff.merchant_id==merchant_id)) is not None

def ensure_merchant_role(u:User,s:Session,merchant_id:int,roles=('OWNER','MANAGER','CASHIER')):
    m=s.get(Merchant,merchant_id)
    if not m or m.status!='ACTIVE':raise HTTPException(404,'Active merchant not found')
    if not has_merchant_role(u,s,merchant_id,roles):raise HTTPException(403,'Not authorized for this merchant')
    return m

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
    accessible={}
    for item in s.scalars(select(MerchantMembership).where(MerchantMembership.user_id==u.id,MerchantMembership.active==1)):
        m=s.get(Merchant,item.merchant_id)
        if m and m.status=='ACTIVE':accessible[m.id]={'id':m.id,'name':m.name,'role':item.role,'branch_id':item.branch_id}
    for m in s.scalars(select(Merchant).join(MerchantStaff,Merchant.id==MerchantStaff.merchant_id).where(MerchantStaff.user_id==u.id,Merchant.status=='ACTIVE')):
        if not s.scalar(select(MerchantMembership.id).where(MerchantMembership.user_id==u.id,
                MerchantMembership.merchant_id==m.id,MerchantMembership.active==0)):
            accessible.setdefault(m.id,{'id':m.id,'name':m.name,'role':'CASHIER','branch_id':None})
    return [{'id':v['id'],'name':v['name']} for v in accessible.values()]
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
    if body.occasion not in ('BIRTHDAY','WEDDING','GRADUATION','HOLIDAY','THANK_YOU','JUST_BECAUSE'):
        raise HTTPException(422,'Invalid occasion')
    if body.design not in ('emerald','midnight','coral','lavender','gold'):
        raise HTTPException(422,'Invalid card design')
    s.add(o);s.flush()
    s.add(GiftPresentation(order_id=o.id,occasion=body.occasion,design=body.design,sender_name=body.sender_name.strip()))
    audit(s,u,'CREATE_ORDER',o.order_code);s.commit()
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
    if s.scalar(select(PaymentIntent.id).where(PaymentIntent.order_id==o.id,PaymentIntent.status=='PENDING')):
        raise HTTPException(409,'An active payment intent exists; complete it through sandbox checkout')
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
        if o.recipient_id!=u.id:
            s.add(GiftNotification(user_id=o.recipient_id,title='A gift is waiting for you 🎁',
                body=f'{u.name} sent you {p.name if (p:=s.get(Program,o.program_id)) else "a digital gift"}. Open your wallet to unwrap it.',
                card_id=c.id,event_type='GIFT_RECEIVED'))
        else:
            s.add(GiftNotification(user_id=o.recipient_id,title='Your gift is ready ✨',
                body='Your digital gift card is now in your wallet.',card_id=c.id,event_type='GIFT_ISSUED'))
        audit(s,u,'PAYMENT_SUCCESS',f'{o.order_code} {c.public_id}')
    else:audit(s,u,'PAYMENT_FAILED',o.order_code)
    monitor_checkout(s,o,body.outcome)
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

@app.get('/api/orders/{order_id}/receipt')
def purchase_receipt(order_id:int,u=Depends(current),s:Session=Depends(db)):
    o=s.get(GiftOrder,order_id)
    if not o or (o.buyer_id!=u.id and u.role!='admin'):
        raise HTTPException(404,'Receipt not found')
    if o.status!='PAID':raise HTTPException(409,'Receipt is only available for paid orders')
    paid=s.scalar(select(PaymentAttempt).where(PaymentAttempt.order_id==o.id,PaymentAttempt.status=='SUCCESS').order_by(PaymentAttempt.id.desc()))
    card_link=s.scalar(select(OrderCard).where(OrderCard.order_id==o.id))
    return {'receipt_type':'PURCHASE','demo_only':True,'reference':'GB-PUR-'+str(o.id).zfill(7),
        'order_code':o.order_code,'gift_program':s.get(Program,o.program_id).name,
        'amount_etb':etb(o.amount_minor),'payer':s.get(User,o.buyer_id).name,
        'recipient':s.get(User,o.recipient_id).name,
        'payment_channel':paid.provider if paid else 'SIMULATED',
        'payment_reference':paid.reference if paid else None,
        'gift_card_code':s.get(Card,card_link.card_id).public_id if card_link else None,
        'date':(paid.created_at if paid else o.created_at).isoformat(),
        'disclaimer':'SANDBOX RECEIPT — NO REAL PAYMENT OR MONETARY VALUE'}

@app.get('/api/redemptions/{redemption_id}/receipt')
def redemption_receipt(redemption_id:int,u=Depends(current),s:Session=Depends(db)):
    r=s.get(Redemption,redemption_id)
    if not r:raise HTTPException(404,'Receipt not found')
    card=s.get(Card,r.card_id)
    authorized=(u.role=='admin' or card.owner_id==u.id or
        has_merchant_role(u,s,r.merchant_id))
    if not authorized:raise HTTPException(404,'Receipt not found')
    return {'receipt_type':'REDEMPTION','demo_only':True,'reference':'GBR-'+str(r.id).zfill(7),
        'merchant':s.get(Merchant,r.merchant_id).name,
        'gift_program':s.get(Program,card.program_id).name,
        'gift_card_code':card.public_id,'amount_etb':etb(r.amount_minor),
        'fee_etb':etb(r.fee_minor),'date':r.created_at.isoformat(),
        'disclaimer':'SANDBOX RECEIPT — NO REAL PAYMENT OR MONETARY VALUE'}

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
    s.execute(update(CardRedeemPass).where(CardRedeemPass.card_id==c.id,CardRedeemPass.consumed==0).values(consumed=1))
    s.add(GiftNotification(user_id=target.id,title='Someone sent you a gift 🎁',body=f'{u.name} sent you {s.get(Program,c.program_id).name}.',card_id=c.id,event_type='GIFT_TRANSFER'))
    s.add(Transfer(card_id=c.id,sender_id=u.id,receiver_id=target.id))
    audit(s,u,'SEND_GIFT',f'{c.public_id} -> {target.id}');s.commit()
    return {'message':'Gift sent successfully!','recipient':target.name}
@app.post('/api/redemptions')
def redeem(body:Redeem,u=Depends(current),s:Session=Depends(db)):
    ensure_merchant_role(u,s,body.merchant_id)
    branch=None
    if body.branch_id is not None:
        branch=s.get(MerchantBranch,body.branch_id)
        if not branch or branch.merchant_id!=body.merchant_id or not branch.active:
            raise HTTPException(403,'Branch is not active for this merchant')
    member=membership(s,u.id,body.merchant_id)
    if member and member.role=='CASHIER':
        if member.branch_id is None or body.branch_id!=member.branch_id:
            raise HTTPException(403,'Cashier must redeem at their assigned branch')
    amount=money(body.amount_etb)
    existing=s.scalar(select(Redemption).where(Redemption.idempotency_key==body.idempotency_key))
    if existing:
        location=s.get(RedemptionLocation,existing.id)
        if location and (location.cashier_id!=u.id or location.branch_id!=body.branch_id):
            raise HTTPException(409,'Idempotency key belongs to a different POS transaction')
        if existing.merchant_id!=body.merchant_id or existing.amount_minor!=amount or s.get(Card,existing.card_id).public_id!=body.card_code.strip():
            raise HTTPException(409,'Idempotency key already used for a different redemption')
        return {'id':existing.id,'receipt':'GBR-'+str(existing.id).zfill(7),'status':'ALREADY_PROCESSED','balance_etb':etb(s.get(Card,existing.card_id).balance_minor)}
    c=s.scalar(select(Card).where(Card.public_id==body.card_code.strip()).with_for_update())
    if not c:raise HTTPException(404,'Card not found')
    merchant=s.get(Merchant,body.merchant_id)
    if not merchant or merchant.status!='ACTIVE':raise HTTPException(404,'Merchant not active')
    allowed=s.scalar(select(Acceptance).where(Acceptance.program_id==c.program_id,Acceptance.merchant_id==body.merchant_id))
    if not allowed:raise HTTPException(403,'This gift cannot be redeemed at that merchant')
    if c.status not in ('ACTIVE','PARTIALLY_REDEEMED') or c.balance_minor<amount:
        raise HTTPException(409,'Insufficient balance or inactive gift')
    now=datetime.now(timezone.utc)
    redeem_pass=s.scalar(select(CardRedeemPass).where(CardRedeemPass.card_id==c.id,CardRedeemPass.consumed==0).order_by(CardRedeemPass.id.desc()).with_for_update())
    def ensure_utc(dt): return dt.replace(tzinfo=timezone.utc) if dt and dt.tzinfo is None else dt
    if not redeem_pass or redeem_pass.owner_id!=c.owner_id or ensure_utc(redeem_pass.expires_at)<=now:
        raise HTTPException(403,'Ask the gift owner to generate a fresh 8-digit redemption PIN')
    if redeem_pass.attempts>=5:raise HTTPException(429,'Too many attempts. Ask the owner to generate a new PIN')
    expected=hmac.new(JWT_SECRET.encode(),f'{c.id}:{redeem_pass.id}:{body.redeem_pin}'.encode(),hashlib.sha256).hexdigest()
    if not secrets.compare_digest(expected,redeem_pass.secret_digest):
        redeem_pass.attempts+=1
        if redeem_pass.attempts>=3:
            raise_fraud(s,f'PIN_GUESS:{redeem_pass.id}','GBF003','Repeated invalid redemption PIN',
                f'Card ID {c.id} received {redeem_pass.attempts} invalid PIN attempts', 'HIGH')
        s.commit()
        raise HTTPException(403,'Invalid redemption PIN')
    # Conditional atomic update avoids overdraft even under competing POS requests.
    changed=s.execute(update(Card).where(Card.id==c.id,Card.balance_minor>=amount,Card.status.in_(['ACTIVE','PARTIALLY_REDEEMED']),Card.owner_id==redeem_pass.owner_id).values(balance_minor=Card.balance_minor-amount))
    if changed.rowcount!=1:
        s.rollback();raise HTTPException(409,'Card balance changed; retry with a new PIN')
    s.refresh(c)
    c.status='FULLY_REDEEMED' if c.balance_minor==0 else 'PARTIALLY_REDEEMED'
    redeem_pass.consumed=1
    fee=amount*3//100
    r=Redemption(card_id=c.id,merchant_id=body.merchant_id,amount_minor=amount,fee_minor=fee,idempotency_key=body.idempotency_key)
    s.add(r);s.flush();s.add(RedemptionLocation(redemption_id=r.id,branch_id=branch.id if branch else None,cashier_id=u.id));event='REDEEM-'+str(r.id)
    entry(s,event,'GIFT_LIABILITY',amount)
    entry(s,event,'MERCHANT_PAYABLE:'+str(body.merchant_id),-(amount-fee))
    entry(s,event,'PLATFORM_FEE',-fee)
    s.add(GiftNotification(user_id=c.owner_id,title='Gift redeemed successfully ✓',body=f'{etb(amount):,.2f} ETB spent at {merchant.name}. Remaining: {etb(c.balance_minor):,.2f} ETB.',card_id=c.id,event_type='REDEEMED'))
    audit(s,u,'REDEEM',f'{c.public_id} {amount}')
    s.commit()
    return {'id':r.id,'receipt':'GBR-'+str(r.id).zfill(7),'merchant':merchant.name,'status':'CAPTURED','amount_etb':etb(amount),'balance_etb':etb(c.balance_minor),'merchant_payable_etb':etb(amount-fee),'branch':branch.name if branch else 'Unspecified'}
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

# === v0.3 product experience: gift presentations, secure redemption and merchant reporting ===
@app.get('/api/occasions')
def occasions():
    return [{'id':key,'name':name,'emoji':emoji} for key,name,emoji in [
        ('BIRTHDAY','Birthday','🎂'),('WEDDING','Wedding','💍'),('GRADUATION','Graduation','🎓'),
        ('HOLIDAY','Holiday','✨'),('THANK_YOU','Thank you','💐'),('JUST_BECAUSE','Just because','🎁')]]

@app.get('/api/notifications')
def get_notifications(u=Depends(current),s:Session=Depends(db)):
    items=s.scalars(select(GiftNotification).where(GiftNotification.user_id==u.id).order_by(GiftNotification.id.desc()).limit(80)).all()
    return [{'id':n.id,'title':n.title,'body':n.body,'card_id':n.card_id,'event_type':n.event_type,
             'read':n.read_at is not None,'at':n.created_at.isoformat()} for n in items]

@app.post('/api/notifications/{notification_id}/read')
def read_notification(notification_id:int,u=Depends(current),s:Session=Depends(db)):
    item=s.scalar(select(GiftNotification).where(GiftNotification.id==notification_id,GiftNotification.user_id==u.id))
    if not item:raise HTTPException(404,'Notification not found')
    item.read_at=datetime.now(timezone.utc);s.commit()
    return {'message':'Marked as read'}

@app.post('/api/cards/{card_id}/redemption-pass')
def generate_redemption_pass(card_id:int,u=Depends(current),s:Session=Depends(db)):
    c=s.scalar(select(Card).where(Card.id==card_id,Card.owner_id==u.id).with_for_update())
    if not c:raise HTTPException(404,'Gift not found in your wallet')
    if c.status not in ('ACTIVE','PARTIALLY_REDEEMED') or c.balance_minor<=0:
        raise HTTPException(409,'Gift is already spent or inactive')
    s.execute(update(CardRedeemPass).where(CardRedeemPass.card_id==card_id,CardRedeemPass.consumed==0).values(consumed=1))
    pin=f'{secrets.randbelow(100000000):08d}'
    x=CardRedeemPass(card_id=card_id,owner_id=u.id,secret_digest='',
                     expires_at=datetime.now(timezone.utc)+timedelta(minutes=5))
    s.add(x);s.flush()
    x.secret_digest=hmac.new(JWT_SECRET.encode(),f'{c.id}:{x.id}:{pin}'.encode(),hashlib.sha256).hexdigest()
    audit(s,u,'ISSUE_REDEMPTION_PIN',c.public_id)
    s.commit()
    return {'card_code':c.public_id,'redeem_pin':pin,'expires_in_seconds':300,
            'message':'Show this one-time 8-digit PIN to the cashier. Valid for 5 minutes.'}

class NewBranch(BaseModel):
    merchant_id:int
    name:str=Field(min_length=2,max_length=100)
    city:str=Field(default='Addis Ababa',max_length=100)

@app.post('/api/admin/branches')
def create_branch(body:NewBranch,u=Depends(admin),s:Session=Depends(db)):
    m=s.get(Merchant,body.merchant_id)
    if not m or m.status!='ACTIVE':raise HTTPException(404,'Merchant not found')
    b=MerchantBranch(merchant_id=m.id,name=body.name.strip(),city=body.city.strip())
    s.add(b);s.flush();audit(s,u,'CREATE_BRANCH',f'{m.id} {b.name}');s.commit()
    return {'id':b.id,'name':b.name,'message':'Branch created successfully'}

@app.get('/api/branches')
def list_branches(merchant_id:Optional[int]=None,s:Session=Depends(db)):
    q=select(MerchantBranch).where(MerchantBranch.active==1)
    if merchant_id is not None:q=q.where(MerchantBranch.merchant_id==merchant_id)
    return [{'id':b.id,'merchant_id':b.merchant_id,'name':b.name,'city':b.city} for b in s.scalars(q.order_by(MerchantBranch.id))]

def merchant_permission(u,s,merchant_id):
    return ensure_merchant_role(u,s,merchant_id,('OWNER','MANAGER','CASHIER'))

@app.get('/api/merchant/overview')
def merchant_overview(merchant_id:int,u=Depends(current),s:Session=Depends(db)):
    m=merchant_permission(u,s,merchant_id)
    rs=s.scalars(select(Redemption).where(Redemption.merchant_id==m.id)).all()
    return {'merchant':m.name,'redemptions':len(rs),'gross_etb':etb(sum(r.amount_minor for r in rs)),
            'fees_etb':etb(sum(r.fee_minor for r in rs)),
            'payable_etb':etb(sum(r.amount_minor-r.fee_minor for r in rs)),
            'branches':s.scalar(select(func.count()).select_from(MerchantBranch).where(MerchantBranch.merchant_id==m.id)),
            'settlement_status':'SIMULATED / NO PAYOUT'}

@app.get('/api/merchant/redemptions')
def merchant_redemptions(merchant_id:int,u=Depends(current),s:Session=Depends(db)):
    m=merchant_permission(u,s,merchant_id)
    rs=s.scalars(select(Redemption).where(Redemption.merchant_id==m.id).order_by(Redemption.id.desc()).limit(200)).all()
    return [{'id':r.id,'receipt':'GBR-'+str(r.id).zfill(7),'card_code':s.get(Card,r.card_id).public_id,
             'amount_etb':etb(r.amount_minor),'fee_etb':etb(r.fee_minor),
             'payable_etb':etb(r.amount_minor-r.fee_minor),'at':r.created_at.isoformat()} for r in rs]

@app.get('/api/wallet/summary')
def wallet_summary(u=Depends(current),s:Session=Depends(db)):
    cards=s.scalars(select(Card).where(Card.owner_id==u.id)).all()
    return {'cards':len(cards),'active_cards':sum(c.balance_minor>0 for c in cards),
            'balance_etb':etb(sum(c.balance_minor for c in cards))}

# === v0.5 Merchant Ecosystem: KYC-style demo intake, manual review, staff scopes, POS branches ===
MERCHANT_CATEGORIES=('SUPERMARKET','RESTAURANT','CAFE','HOTEL','RETAIL','BOOKSTORE','OTHER')

class MerchantApply(BaseModel):
    business_name:str=Field(min_length=3,max_length=120)
    category:str=Field(default='RETAIL')
    city:str=Field(min_length=2,max_length=100)
    contact_phone:str=Field(min_length=7,max_length=30)
    description:str=Field(default='',max_length=350)

class ReviewApplication(BaseModel):
    decision:str=Field(pattern='^(APPROVED|REJECTED)$')
    note:str=Field(default='',max_length=350)

class TeamInvite(BaseModel):
    merchant_id:int
    user_phone:str
    role:str=Field(pattern='^(MANAGER|CASHIER)$')
    branch_id:Optional[int]=None

class TeamStatus(BaseModel):
    active:bool

class MerchantGiftProgram(BaseModel):
    merchant_id:int
    name:str=Field(min_length=2,max_length=120)
    category:str=Field(default='SHOPPING')
    description:str=Field(default='',max_length=240)
    emoji:str=Field(default='🎁',max_length=12)


def application_out(a:MerchantApplication,s:Session):
    user=s.get(User,a.applicant_id)
    return {'id':a.id,'business_name':a.business_name,'category':a.category,'city':a.city,
        'contact_phone':a.contact_phone,'description':a.description,'status':a.status,
        'review_note':a.review_note,'merchant_id':a.merchant_id,'applicant_name':user.name,
        'applicant_phone':user.phone,'submitted_at':a.created_at.isoformat()}

@app.get('/api/merchant/access')
def my_merchant_access(u=Depends(current),s:Session=Depends(db)):
    if u.role=='admin':
        return [{'id':m.id,'name':m.name,'role':'ADMIN','branch_id':None} for m in s.scalars(
            select(Merchant).where(Merchant.status=='ACTIVE'))]
    accessible={}
    for item in s.scalars(select(MerchantMembership).where(MerchantMembership.user_id==u.id,MerchantMembership.active==1)):
        m=s.get(Merchant,item.merchant_id)
        if m and m.status=='ACTIVE':accessible[m.id]={'id':m.id,'name':m.name,'role':item.role,'branch_id':item.branch_id}
    for m in s.scalars(select(Merchant).join(MerchantStaff,Merchant.id==MerchantStaff.merchant_id).where(
            MerchantStaff.user_id==u.id,Merchant.status=='ACTIVE')):
        if not s.scalar(select(MerchantMembership.id).where(MerchantMembership.user_id==u.id,
                MerchantMembership.merchant_id==m.id,MerchantMembership.active==0)):
            accessible.setdefault(m.id,{'id':m.id,'name':m.name,'role':'CASHIER','branch_id':None})
    return list(accessible.values())

@app.post('/api/merchant/applications',status_code=201)
def merchant_apply(body:MerchantApply,u=Depends(current),s:Session=Depends(db)):
    name=body.business_name.strip();city=body.city.strip();phone=body.contact_phone.strip()
    if not name or not city or not phone:raise HTTPException(422,'Name, city and contact required')
    if body.category not in MERCHANT_CATEGORIES:raise HTTPException(422,'Unknown category')
    if s.scalar(select(Merchant).where(func.lower(Merchant.name)==name.lower())):
        raise HTTPException(409,'Merchant name is already registered')
    pending=s.scalar(select(MerchantApplication).where(func.lower(MerchantApplication.business_name)==name.lower(),
        MerchantApplication.status=='PENDING'))
    if pending:raise HTTPException(409,'An application for this business is already awaiting review')
    a=MerchantApplication(applicant_id=u.id,business_name=name,category=body.category,city=city,
        contact_phone=phone,description=body.description.strip())
    s.add(a);s.flush();audit(s,u,'MERCHANT_APPLICATION',f'Application #{a.id} {name}');s.commit()
    return application_out(a,s)

@app.get('/api/merchant/applications/my')
def my_applications(u=Depends(current),s:Session=Depends(db)):
    return [application_out(a,s) for a in s.scalars(select(MerchantApplication).where(
        MerchantApplication.applicant_id==u.id).order_by(MerchantApplication.id.desc()))]

@app.get('/api/admin/applications')
def review_queue(status:Optional[str]=None,u=Depends(admin),s:Session=Depends(db)):
    query=select(MerchantApplication)
    if status:
        if status not in ('PENDING','APPROVED','REJECTED'):raise HTTPException(422,'Invalid status')
        query=query.where(MerchantApplication.status==status)
    return [application_out(a,s) for a in s.scalars(query.order_by(MerchantApplication.id.desc()))]

@app.post('/api/admin/applications/{application_id}/review')
def decide_application(application_id:int,body:ReviewApplication,u=Depends(admin),s:Session=Depends(db)):
    a=s.scalar(select(MerchantApplication).where(MerchantApplication.id==application_id).with_for_update())
    if not a:raise HTTPException(404,'Application not found')
    if a.status!='PENDING':raise HTTPException(409,'Application already reviewed')
    if body.decision=='REJECTED' and not body.note.strip():raise HTTPException(422,'Provide a reason for rejection')
    if body.decision=='APPROVED':
        if s.scalar(select(Merchant).where(func.lower(Merchant.name)==a.business_name.lower())):
            raise HTTPException(409,'A merchant with that name already exists')
        merchant=Merchant(name=a.business_name,status='ACTIVE');s.add(merchant);s.flush()
        s.add(MerchantMembership(user_id=a.applicant_id,merchant_id=merchant.id,role='OWNER'))
        s.add(MerchantBranch(merchant_id=merchant.id,name='Main branch',city=a.city))
        a.merchant_id=merchant.id
        s.add(GiftNotification(user_id=a.applicant_id,title='Merchant application approved ✓',
            body=f'{a.business_name} is approved in the GiftBridge demo. Open Merchant studio to set up your shop.',event_type='MERCHANT_APPROVED'))
    else:
        s.add(GiftNotification(user_id=a.applicant_id,title='Merchant application update',
            body=f'{a.business_name}: application declined. {body.note.strip()}',event_type='MERCHANT_REJECTED'))
    a.status=body.decision;a.review_note=body.note.strip();a.reviewed_at=datetime.now(timezone.utc);a.reviewed_by=u.id
    audit(s,u,'REVIEW_MERCHANT_APPLICATION',f'{a.id} {body.decision}');s.commit()
    return application_out(a,s)

@app.get('/api/merchant/team')
def merchant_team(merchant_id:int,u=Depends(current),s:Session=Depends(db)):
    ensure_merchant_role(u,s,merchant_id,('OWNER','MANAGER'))
    rows=s.scalars(select(MerchantMembership).where(MerchantMembership.merchant_id==merchant_id).order_by(MerchantMembership.id)).all()
    result=[]
    for t in rows:
        member_user=s.get(User,t.user_id)
        branch=s.get(MerchantBranch,t.branch_id) if t.branch_id else None
        result.append({'id':t.id,'name':member_user.name,'phone':member_user.phone,'role':t.role,
            'active':bool(t.active),'branch_id':t.branch_id,'branch':branch.name if branch else None})
    # Legacy cashiers remain authorized; managers can migrate them to scoped memberships if desired.
    return result

@app.post('/api/merchant/team')
def invite_team(body:TeamInvite,u=Depends(current),s:Session=Depends(db)):
    ensure_merchant_role(u,s,body.merchant_id,('OWNER','MANAGER'))
    manager=membership(s,u.id,body.merchant_id)
    if u.role!='admin' and manager and manager.role=='MANAGER' and body.role!='CASHIER':
        raise HTTPException(403,'Managers may assign only cashiers')
    target=s.scalar(select(User).where(User.phone==body.user_phone.strip()))
    if not target:raise HTTPException(404,'Staff member must register a GiftBridge demo account first')
    if target.role=='admin':raise HTTPException(409,'Do not assign platform administrators')
    branch=None
    if body.role=='CASHIER':
        branch=s.get(MerchantBranch,body.branch_id) if body.branch_id else None
        if not branch or branch.merchant_id!=body.merchant_id or not branch.active:
            raise HTTPException(422,'Cashier requires an active branch of this merchant')
    elif body.branch_id is not None:raise HTTPException(422,'Manager assignment is merchant-wide')
    existing=s.scalar(select(MerchantMembership).where(MerchantMembership.merchant_id==body.merchant_id,
        MerchantMembership.user_id==target.id))
    if existing:
        if existing.role=='OWNER':raise HTTPException(403,'Owner access cannot be changed')
        existing.role=body.role;existing.branch_id=body.branch_id;existing.active=1
    else:
        s.add(MerchantMembership(merchant_id=body.merchant_id,user_id=target.id,role=body.role,branch_id=body.branch_id))
    audit(s,u,'ASSIGN_MERCHANT_TEAM',f'{body.merchant_id} user {target.id} {body.role}');s.commit()
    return {'message':'Team member saved','phone':target.phone,'role':body.role}

@app.patch('/api/merchant/team/{membership_id}')
def update_team(membership_id:int,body:TeamStatus,u=Depends(current),s:Session=Depends(db)):
    item=s.get(MerchantMembership,membership_id)
    if not item:raise HTTPException(404,'Team member not found')
    ensure_merchant_role(u,s,item.merchant_id,('OWNER','MANAGER'))
    if item.role=='OWNER':raise HTTPException(403,'Cannot deactivate merchant owner')
    actor=membership(s,u.id,item.merchant_id)
    if actor and actor.role=='MANAGER' and item.role!='CASHIER' and u.role!='admin':
        raise HTTPException(403,'Managers cannot edit other managers')
    item.active=int(body.active)
    audit(s,u,'UPDATE_MERCHANT_TEAM',f'{item.id} active={item.active}');s.commit()
    return {'id':item.id,'active':bool(item.active)}

@app.post('/api/merchant/branches')
def merchant_create_branch(body:NewBranch,u=Depends(current),s:Session=Depends(db)):
    ensure_merchant_role(u,s,body.merchant_id,('OWNER','MANAGER'))
    if not body.name.strip() or not body.city.strip():raise HTTPException(422,'Valid branch and city required')
    branch=MerchantBranch(merchant_id=body.merchant_id,name=body.name.strip(),city=body.city.strip())
    s.add(branch);s.flush();audit(s,u,'CREATE_MERCHANT_BRANCH',f'{branch.merchant_id} {branch.id}');s.commit()
    return {'id':branch.id,'name':branch.name,'city':branch.city}

@app.post('/api/merchant/programs')
def merchant_create_program(body:MerchantGiftProgram,u=Depends(current),s:Session=Depends(db)):
    ensure_merchant_role(u,s,body.merchant_id,('OWNER','MANAGER'))
    if body.category not in GIFT_CATEGORIES or body.category=='UNIVERSAL':raise HTTPException(422,'Invalid merchant gift category')
    p=Program(name=body.name.strip(),kind='MERCHANT_SPECIFIC',merchant_id=body.merchant_id,active=1)
    s.add(p);s.flush()
    s.add(Acceptance(program_id=p.id,merchant_id=body.merchant_id))
    s.add(ProgramAppearance(program_id=p.id,category=body.category,description=body.description.strip(),emoji=body.emoji.strip() or '🎁'))
    audit(s,u,'MERCHANT_PUBLISH_PROGRAM',f'{p.id} merchant {body.merchant_id}');s.commit()
    return {'id':p.id,'name':p.name,'message':'Merchant gift published (simulation only)'}

@app.get('/api/merchant/report')
def merchant_report(merchant_id:int,days:int=30,u=Depends(current),s:Session=Depends(db)):
    m=ensure_merchant_role(u,s,merchant_id,('OWNER','MANAGER'))
    if days not in (7,30,90,365):raise HTTPException(422,'Use 7, 30, 90 or 365 days')
    start=datetime.now(timezone.utc)-timedelta(days=days)
    rs=s.scalars(select(Redemption).where(Redemption.merchant_id==m.id,Redemption.created_at>=start)).all()
    # Count only paid merchant-specific programs owned by this merchant; universal funds belong to external program issuer.
    sold=s.execute(select(GiftOrder.amount_minor).join(Program,GiftOrder.program_id==Program.id).where(
        Program.merchant_id==m.id,Program.kind=='MERCHANT_SPECIFIC',GiftOrder.status=='PAID',
        GiftOrder.created_at>=start)).all()
    buckets={}
    branch_stats={}
    for r in rs:
        day=r.created_at.date().isoformat()
        buckets[day]=buckets.get(day,0)+r.amount_minor
        location=s.get(RedemptionLocation,r.id)
        label=s.get(MerchantBranch,location.branch_id).name if location and location.branch_id else 'Unspecified'
        item=branch_stats.setdefault(label,{'branch':label,'transactions':0,'gross_minor':0})
        item['transactions']+=1;item['gross_minor']+=r.amount_minor
    gross=sum(r.amount_minor for r in rs);fees=sum(r.fee_minor for r in rs)
    return {'merchant_id':m.id,'merchant':m.name,'days':days,'transactions':len(rs),
        'merchant_specific_sales_etb':etb(sum(row[0] for row in sold)),
        'redeemed_etb':etb(gross),'fee_etb':etb(fees),'estimated_payable_etb':etb(gross-fees),
        'daily':[{'date':date,'redeemed_etb':etb(v)} for date,v in sorted(buckets.items())],
        'branches':[{'branch':v['branch'],'transactions':v['transactions'],'redeemed_etb':etb(v['gross_minor'])}
            for v in sorted(branch_stats.values(),key=lambda x:-x['gross_minor'])],
        'disclaimer':'SIMULATED ONLY — NO REAL SETTLEMENT OR PAYMENT'}

@app.get('/api/cards/{card_id}/qr')
def gift_code_qr(card_id:int,u=Depends(current),s:Session=Depends(db)):
    """QR stores only a card identifier; cashier separately verifies owner-issued one-time PIN."""
    c=s.scalar(select(Card).where(Card.id==card_id,Card.owner_id==u.id))
    if not c:raise HTTPException(404,'Card not found in your wallet')
    if c.balance_minor<=0:raise HTTPException(409,'Gift has no balance')
    import qrcode
    qr=qrcode.QRCode(version=None,box_size=6,border=3, error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data('GB-CARD:'+c.public_id);qr.make(fit=True)
    stream=io.BytesIO();qr.make_image(fill_color='#184c36',back_color='#ffffff').save(stream,format='PNG')
    return {'card_code':c.public_id,'png_base64':base64.b64encode(stream.getvalue()).decode(),
        'note':'QR identifies the card only; the owner must separately provide a fresh one-time PIN.'}


# === v0.6 payment intents, simulated provider events, reconciliation and fraud review ===
# REAL PROVIDER CREDENTIALS / SETTLEMENT / WEBHOOKS ARE NOT SUPPORTED IN THIS SANDBOX.
PAYMENT_CHANNELS=('M-PESA (simulated)','telebirr (simulated)','Dashen Bank (simulated)','Bank card (simulated)')

def utc(dt):
    return dt.replace(tzinfo=timezone.utc) if dt and dt.tzinfo is None else dt

def raise_fraud(s, fingerprint, control_id, title, detail, severity='MEDIUM'):
    # A stable fingerprint ensures replays don't create duplicate alerts.
    exists=s.scalar(select(FraudAlert.id).where(FraudAlert.fingerprint==fingerprint))
    if not exists:
        s.add(FraudAlert(fingerprint=fingerprint,control_id=control_id,
                         title=title,detail=detail,severity=severity))

def monitor_checkout(s, order, outcome):
    if outcome=='SUCCESS' and order.amount_minor>=1000000:
        raise_fraud(s, 'HIGH_VALUE:'+str(order.id),'GBF001','High-value simulated gift',
                    f'Order {order.order_code}: {etb(order.amount_minor):,.2f} ETB', 'HIGH')
    if outcome=='FAILED':
        cutoff=datetime.now(timezone.utc)-timedelta(hours=1)
        failures=s.scalar(select(func.count()).select_from(PaymentAttempt).join(
            GiftOrder,PaymentAttempt.order_id==GiftOrder.id).where(
            GiftOrder.buyer_id==order.buyer_id,PaymentAttempt.status=='FAILED',
            PaymentAttempt.created_at>=cutoff)) or 0
        if failures>=3:
            raise_fraud(s,'FAILED_PAYMENTS:'+str(order.buyer_id)+':'+datetime.now(timezone.utc).strftime('%Y%m%d%H'),
                        'GBF002','Payment failures in one hour',
                        f'Buyer ID {order.buyer_id}: {failures} failed sandbox payment attempts in one hour','MEDIUM')

class NewPaymentIntent(BaseModel):
    order_id:int
    channel:str=Field(max_length=60)
    idempotency_key:str=Field(min_length=12,max_length=100)

class SimulateGateway(BaseModel):
    outcome:str=Field(pattern='^(SUCCESS|FAILED)$')

class ReviewFraud(BaseModel):
    status:str=Field(pattern='^(OPEN|INVESTIGATING|RESOLVED|FALSE_POSITIVE)$')
    note:str=Field(default='',max_length=350)

def intent_out(x, s):
    order=s.get(GiftOrder,x.order_id)
    return {'id':x.id,'order_id':x.order_id,'order_code':order.order_code,
            'provider':x.provider,'provider_reference':x.provider_reference,
            'amount_etb':etb(x.amount_minor),'status':x.status,
            'created_at':x.created_at.isoformat(),
            'completed_at':x.completed_at.isoformat() if x.completed_at else None,
            'sandbox_only':True}

@app.post('/api/payments/intents',status_code=201)
def create_intent(body:NewPaymentIntent,u=Depends(current),s:Session=Depends(db)):
    if os.getenv('ENABLE_DEMO_FUNDING','true').lower()!='true':raise HTTPException(403,'Sandbox payment simulation disabled')
    if body.channel not in PAYMENT_CHANNELS:raise HTTPException(422,'Unknown sandbox channel')
    o=s.get(GiftOrder,body.order_id)
    if not o or o.buyer_id!=u.id:raise HTTPException(404,'Order not found')
    existing=s.scalar(select(PaymentIntent).where(PaymentIntent.buyer_id==u.id,
                  PaymentIntent.idempotency_key==body.idempotency_key))
    if existing:
        if existing.order_id!=o.id or existing.provider!=body.channel:
            raise HTTPException(409,'Idempotency key already belongs to another payment')
        return intent_out(existing,s)
    if o.status!='PENDING':raise HTTPException(409,'Order must be pending')
    pending=s.scalar(select(PaymentIntent).where(PaymentIntent.order_id==o.id,PaymentIntent.status=='PENDING'))
    if pending:
        if pending.provider==body.channel:return intent_out(pending,s)
        raise HTTPException(409,'Complete the existing payment intent first')
    x=PaymentIntent(order_id=o.id,buyer_id=u.id,idempotency_key=body.idempotency_key,
        provider=body.channel,provider_reference='GBSIM-'+secrets.token_hex(8).upper(),
        amount_minor=o.amount_minor,status='PENDING')
    s.add(x);s.flush();audit(s,u,'CREATE_PAYMENT_INTENT',f'{o.order_code} {x.provider_reference}')
    s.commit();return intent_out(x,s)

def capture_intent(s, x, outcome, event_reference):
    """Single transaction: one verified demo event -> one order transition -> at most one card."""
    prior=s.scalar(select(PaymentEvent).where(PaymentEvent.event_reference==event_reference))
    if prior:
        if prior.intent_id!=x.id or prior.outcome!=outcome:
            raise HTTPException(409,'Event reference already belongs to another payment')
        return {'status':'ALREADY_PROCESSED','intent_id':x.id,'order_status':s.get(GiftOrder,x.order_id).status}
    if x.status!='PENDING':
        raise HTTPException(409,'Payment already finalized with a different event')
    o=s.get(GiftOrder,x.order_id)
    if o.status!='PENDING' or x.amount_minor!=o.amount_minor:
        raise HTTPException(409,'Payment order is not pending or amount changed')
    # Compare-and-swap: two concurrent simulated payment events cannot both issue value.
    changed=s.execute(update(GiftOrder).where(GiftOrder.id==o.id,GiftOrder.status=='PENDING')
        .values(status='PAID' if outcome=='SUCCESS' else 'FAILED'))
    if changed.rowcount!=1:
        s.rollback();raise HTTPException(409,'Payment has already been finalized')
    sequence=(s.scalar(select(func.count()).select_from(PaymentAttempt).where(
        PaymentAttempt.order_id==o.id)) or 0)+1
    s.add(PaymentAttempt(order_id=o.id,attempt_number=sequence,provider=x.provider,
        status=outcome,reference=x.provider_reference))
    s.add(PaymentEvent(intent_id=x.id,event_reference=event_reference,outcome=outcome))
    x.status='SUCCEEDED' if outcome=='SUCCESS' else 'FAILED'
    x.completed_at=datetime.now(timezone.utc)
    if outcome=='SUCCESS':
        c=Card(public_id='GB-'+secrets.token_hex(6).upper(),program_id=o.program_id,
            owner_id=o.recipient_id,original_minor=o.amount_minor,balance_minor=o.amount_minor,status='ACTIVE')
        s.add(c);s.flush();s.add(OrderCard(order_id=o.id,card_id=c.id))
        entry(s,'ISSUE-'+str(c.id),'SIMULATED_FUNDS',o.amount_minor)
        entry(s,'ISSUE-'+str(c.id),'GIFT_LIABILITY',-o.amount_minor)
        buyer=s.get(User,o.buyer_id)
        s.add(GiftNotification(user_id=o.recipient_id,
            title='A gift is waiting for you 🎁' if o.recipient_id!=o.buyer_id else 'Your gift is ready ✨',
            body=f'{buyer.name} sent you {s.get(Program,o.program_id).name}.' if o.recipient_id!=o.buyer_id else 'Your digital gift is in your wallet.',
            card_id=c.id,event_type='GIFT_RECEIVED' if o.recipient_id!=o.buyer_id else 'GIFT_ISSUED'))
    monitor_checkout(s,o,outcome)
    s.add(Audit(actor_id=o.buyer_id,action='GATEWAY_'+outcome,detail=f'{o.order_code} {event_reference}'))
    s.commit()
    return {'status':'PROCESSED','intent_id':x.id,'order_status':o.status,
            'order':order_out(o,s),'sandbox_only':True}

@app.get('/api/payments/intents/{intent_id}')
def get_intent(intent_id:int,u=Depends(current),s:Session=Depends(db)):
    x=s.get(PaymentIntent,intent_id)
    if not x or (x.buyer_id!=u.id and u.role!='admin'):raise HTTPException(404,'Payment intent not found')
    return intent_out(x,s)

@app.post('/api/payments/intents/{intent_id}/simulate')
def simulate_gateway(intent_id:int,body:SimulateGateway,u=Depends(current),s:Session=Depends(db)):
    if os.getenv('ENABLE_DEMO_FUNDING','true').lower()!='true':raise HTTPException(403,'Sandbox payment simulation disabled')
    x=s.get(PaymentIntent,intent_id)
    if not x or x.buyer_id!=u.id:raise HTTPException(404,'Payment intent not found')
    if x.status!='PENDING':
        return {'status':'ALREADY_PROCESSED','intent_id':x.id,'order_status':s.get(GiftOrder,x.order_id).status,
                'order':order_out(s.get(GiftOrder,x.order_id),s),'sandbox_only':True}
    event_reference='EVT-'+secrets.token_hex(12).upper()
    return capture_intent(s,x,body.outcome,event_reference)

# Only for API integration exercises; deliberately disabled in ordinary local operation.
# A real provider webhook would require provider-specific authentication and event verification.
@app.post('/api/payments/webhook/sandbox')
def sandbox_webhook(event:dict, x_giftbridge_signature:Optional[str]=Header(None),
                    x_giftbridge_timestamp:Optional[str]=Header(None),s:Session=Depends(db)):
    if os.getenv('ENABLE_SANDBOX_WEBHOOK','false').lower()!='true':raise HTTPException(404,'Not enabled')
    secret=os.getenv('SANDBOX_WEBHOOK_SECRET','')
    if len(secret)<24:raise HTTPException(503,'Webhook signing secret missing')
    try:
        stamp=int(x_giftbridge_timestamp or '0')
        if abs(datetime.now(timezone.utc).timestamp()-stamp)>300:raise ValueError('stale')
    except (ValueError,TypeError):raise HTTPException(401,'Invalid webhook timestamp')
    blob=json.dumps(event,sort_keys=True,separators=(',',':'))
    expected=hmac.new(secret.encode(),f'{stamp}.{blob}'.encode(),hashlib.sha256).hexdigest()
    if not x_giftbridge_signature or not hmac.compare_digest(x_giftbridge_signature,expected):
        raise HTTPException(401,'Invalid webhook signature')
    if sorted(event.keys())!=['amount_minor','event_reference','intent_id','outcome','provider_reference']:
        raise HTTPException(422,'Invalid webhook fields')
    if event['outcome'] not in ('SUCCESS','FAILED'):raise HTTPException(422,'Invalid outcome')
    x=s.get(PaymentIntent,event['intent_id']) if type(event['intent_id']) is int else None
    if not x or x.provider_reference!=event['provider_reference'] or x.amount_minor!=event['amount_minor']:
        raise HTTPException(409,'Intent/provider reference/amount mismatch')
    if not isinstance(event['event_reference'],str) or len(event['event_reference'])>85:
        raise HTTPException(422,'Invalid event reference')
    return capture_intent(s,x,event['outcome'],event['event_reference'])

@app.get('/api/admin/payment-activity')
def payment_activity(u=Depends(admin),s:Session=Depends(db)):
    latest=s.scalars(select(PaymentIntent).order_by(PaymentIntent.id.desc()).limit(40)).all()
    return [{'id':x.id,'order_code':s.get(GiftOrder,x.order_id).order_code,
             'provider':x.provider,'reference':x.provider_reference,'status':x.status,
             'amount_etb':etb(x.amount_minor),'created_at':x.created_at.isoformat()}
            for x in latest]

@app.get('/api/admin/reconciliation')
def reconcile(u=Depends(admin),s:Session=Depends(db)):
    # All amounts are integer minor units, never floating-point comparisons.
    issued=s.scalar(select(func.coalesce(func.sum(Card.original_minor),0))) or 0
    remaining=s.scalar(select(func.coalesce(func.sum(Card.balance_minor),0))) or 0
    redeemed=s.scalar(select(func.coalesce(func.sum(Redemption.amount_minor),0))) or 0
    liability=-(s.scalar(select(func.coalesce(func.sum(Entry.delta_minor),0)).where(
        Entry.account=='GIFT_LIABILITY')) or 0)
    paid_orders=s.scalars(select(GiftOrder).where(GiftOrder.status=='PAID')).all()
    missing=[];unpaid=[];unfunded=[]
    for o in paid_orders:
        links=s.scalars(select(OrderCard).where(OrderCard.order_id==o.id)).all()
        if len(links)!=1:missing.append(o.order_code)
        if not s.scalar(select(PaymentAttempt.id).where(PaymentAttempt.order_id==o.id,
                      PaymentAttempt.status=='SUCCESS')):
            unfunded.append(o.order_code)
    for link in s.scalars(select(OrderCard)):
        o=s.get(GiftOrder,link.order_id)
        if not o or o.status!='PAID':unpaid.append(str(link.order_id))
    unbalanced=[{'event':key,'delta_minor':total} for key,total in
        s.execute(select(Entry.event_id,func.sum(Entry.delta_minor)).group_by(Entry.event_id)) if total!=0]
    paid_total=sum(o.amount_minor for o in paid_orders)
    all_redemptions=s.scalars(select(Redemption)).all()
    expected_payable=sum(r.amount_minor-r.fee_minor for r in all_redemptions)
    expected_fees=sum(r.fee_minor for r in all_redemptions)
    ledger_payable=-(s.scalar(select(func.coalesce(func.sum(Entry.delta_minor),0)).where(
        Entry.account.like('MERCHANT_PAYABLE:%'))) or 0)
    ledger_fees=-(s.scalar(select(func.coalesce(func.sum(Entry.delta_minor),0)).where(
        Entry.account=='PLATFORM_FEE')) or 0)
    findings=[]
    if issued != remaining+redeemed:findings.append('Card issuance / redemption totals do not reconcile')
    if liability!=remaining:findings.append('Gift liability ledger differs from card balances')
    if paid_total!=issued:findings.append('Paid order total differs from issued gift value')
    if expected_payable!=ledger_payable:findings.append('Merchant payable ledger differs from redemptions')
    if expected_fees!=ledger_fees:findings.append('Platform fee ledger differs from redemptions')
    if missing:findings.append('Paid orders without exactly one card')
    if unpaid:findings.append('Cards linked to orders not marked PAID')
    if unfunded:findings.append('Paid orders without successful payment attempt')
    if unbalanced:findings.append('Unbalanced ledger events')
    report={'result':'PASS' if not findings else 'FAIL','as_of':datetime.now(timezone.utc).isoformat(),
      'cards_issued_etb':etb(issued),'outstanding_etb':etb(remaining),'redeemed_etb':etb(redeemed),
      'ledger_liability_etb':etb(liability),'paid_orders_etb':etb(paid_total),
      'merchant_payable_etb':etb(expected_payable),'ledger_merchant_payable_etb':etb(ledger_payable),
      'platform_fee_etb':etb(expected_fees),'ledger_platform_fee_etb':etb(ledger_fees),
      'paid_orders_missing_card':missing[:20],'unpaid_card_orders':unpaid[:20],
      'paid_orders_missing_payment':unfunded[:20],'unbalanced_events':unbalanced[:20],
      'findings':findings,'disclaimer':'DEMO RECONCILIATION — DOES NOT VERIFY REAL BANK OR PROCESSOR STATEMENTS'}
    return report

@app.get('/api/admin/fraud-alerts')
def fraud_alerts(u=Depends(admin),s:Session=Depends(db)):
    return [{'id':a.id,'control_id':a.control_id,'severity':a.severity,'status':a.status,
        'title':a.title,'detail':a.detail,'note':a.note,'at':a.created_at.isoformat()}
        for a in s.scalars(select(FraudAlert).order_by(FraudAlert.id.desc()).limit(150))]

@app.post('/api/admin/fraud-alerts/{alert_id}/review')
def review_fraud(alert_id:int,body:ReviewFraud,u=Depends(admin),s:Session=Depends(db)):
    a=s.get(FraudAlert,alert_id)
    if not a:raise HTTPException(404,'Fraud alert not found')
    if body.status in ('RESOLVED','FALSE_POSITIVE') and not body.note.strip():
        raise HTTPException(422,'Review note required before closing alert')
    a.status=body.status;a.note=body.note.strip();a.reviewed_by=u.id;a.reviewed_at=datetime.now(timezone.utc)
    audit(s,u,'REVIEW_FRAUD',f'{a.id} {a.status}')
    s.commit();return {'id':a.id,'status':a.status,'message':'Alert updated'}

@app.get('/api/health')
def health():return {'status':'ok','mode':'SIMULATION','version':'0.6.0'}
app.mount('/assets',StaticFiles(directory=str(ROOT/'frontend')),name='assets')
@app.get('/')
def home():return FileResponse(ROOT/'frontend'/'index.html')
