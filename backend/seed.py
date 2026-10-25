from backend.main import SessionLocal,User,Merchant,Program,Acceptance,hash_pw
from sqlalchemy import select
with SessionLocal() as s:
    users=[('251900000001','Demo Administrator','admin'),('251900000002','Demo Customer','customer'),('251900000003','Demo Recipient','customer')]
    for phone,name,role in users:
        if not s.scalar(select(User).where(User.phone==phone)):s.add(User(phone=phone,name=name,role=role,password_hash=hash_pw('DemoPass123!')))
    s.flush()
    for name in ('Queens Supermarket (Demo)','Addis Home Depot (Demo)','GiftBridge Bookstore (Demo)'):
        if not s.scalar(select(Merchant).where(Merchant.name==name)):s.add(Merchant(name=name))
    s.flush()
    merchants=s.scalars(select(Merchant).order_by(Merchant.id)).all()
    if not s.scalar(select(Program).where(Program.name=='Queens Gift (Demo)')):
        p=Program(name='Queens Gift (Demo)',kind='MERCHANT_SPECIFIC',merchant_id=merchants[0].id);s.add(p);s.flush();s.add(Acceptance(program_id=p.id,merchant_id=merchants[0].id))
    if not s.scalar(select(Program).where(Program.name=='GiftBridge Universal (Demo)')):
        p=Program(name='GiftBridge Universal (Demo)',kind='UNIVERSAL');s.add(p);s.flush()
        for m in merchants:s.add(Acceptance(program_id=p.id,merchant_id=m.id))
    s.commit()
print('Demo seed complete')
