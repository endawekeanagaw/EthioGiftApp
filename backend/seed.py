"""Idempotent local sandbox demo setup. Never use these accounts in production."""
from sqlalchemy import select
from backend.main import SessionLocal, User, Merchant, Program, Acceptance, MerchantStaff, hash_pw

with SessionLocal() as s:
    users = [
        ('251900000001','Demo Administrator','admin'),
        ('251900000002','Demo Customer','customer'),
        ('251900000003','Demo Recipient','customer'),
        ('251900000004','Queens Demo Cashier','merchant'),
    ]
    for phone,name,role in users:
        u=s.scalar(select(User).where(User.phone==phone))
        if not u:s.add(User(phone=phone,name=name,role=role,password_hash=hash_pw('DemoPass123!')))
    s.flush()
    for name in ['Queens Supermarket (Demo)','Addis Home Depot (Demo)','GiftBridge Bookstore (Demo)']:
        if not s.scalar(select(Merchant).where(Merchant.name==name)):
            s.add(Merchant(name=name))
    s.flush()
    merch={m.name:m for m in s.scalars(select(Merchant))}
    cashier=s.scalar(select(User).where(User.phone=='251900000004'))
    queens=merch['Queens Supermarket (Demo)']
    if not s.scalar(select(MerchantStaff).where(MerchantStaff.user_id==cashier.id,MerchantStaff.merchant_id==queens.id)):
        s.add(MerchantStaff(user_id=cashier.id,merchant_id=queens.id))
    definitions=[
        ('Queens Gift (Demo)','MERCHANT_SPECIFIC',queens.id,[queens.id]),
        ('Addis Home Depot Gift (Demo)','MERCHANT_SPECIFIC',merch['Addis Home Depot (Demo)'].id,[merch['Addis Home Depot (Demo)'].id]),
        ('GiftBridge Universal (Demo)','UNIVERSAL',None,[m.id for m in merch.values()]),
    ]
    for name,kind,merchant_id,ids in definitions:
        p=s.scalar(select(Program).where(Program.name==name))
        if not p:
            p=Program(name=name,kind=kind,merchant_id=merchant_id)
            s.add(p);s.flush()
        for mid in ids:
            if not s.scalar(select(Acceptance).where(Acceptance.program_id==p.id,Acceptance.merchant_id==mid)):
                s.add(Acceptance(program_id=p.id,merchant_id=mid))
    s.commit()
print('GiftBridge sandbox accounts and sample merchants are ready.')
