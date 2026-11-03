import asyncio
import sys
import os
from uuid import uuid4

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from datetime import date
from passlib.context import CryptContext

from app.core.config import get_settings
from app.models import User, UserRole, UserStatus, Distributor

settings = get_settings()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

async def create_superuser():
    engine = create_async_engine(settings.DATABASE_URL, echo=True)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as db:
        # Check if super admin already exists
        from sqlalchemy import select
        result = await db.execute(select(User).where(User.role == UserRole.SUPER_ADMIN))
        existing = result.scalar_one_or_none()
        
        if existing:
            print(f"Super admin already exists: {existing.email}")
            return
        
        # Create default distributor first
        distributor = Distributor(
            id=uuid4(),
            name="Default Distributor",
            legal_name="Default Distributor Pvt Ltd",
            gstin="27AAAAA0000A1Z5",
            pan="AAAAA0000A",
            address="123 Default Street",
            city="Mumbai",
            state="Maharashtra",
            pincode="400001",
            phone="+919876543210",
            email="distributor@chemistcrm.com",
            drug_license_number="DL-001",
            drug_license_form="Form 20",
            drug_license_expiry=date(2025, 12, 31),
            is_active=True,
            credit_limit=1000000,
            payment_terms_days=30,
        )
        db.add(distributor)
        await db.flush()
        
        # Create super admin user
        superuser = User(
            id=uuid4(),
            email="admin@chemistcrm.com",
            hashed_password=pwd_context.hash("admin123456"),
            full_name="Super Admin",
            phone="+919876543210",
            role=UserRole.SUPER_ADMIN,
            status=UserStatus.ACTIVE,
            is_active=True,
            distributor_id=distributor.id,
        )
        db.add(superuser)
        
        # Create demo distributor user
        distributor_user = User(
            id=uuid4(),
            email="distributor@demo.com",
            hashed_password=pwd_context.hash("password123"),
            full_name="Demo Distributor",
            phone="+919876543211",
            role=UserRole.DISTRIBUTOR_ADMIN,
            status=UserStatus.ACTIVE,
            is_active=True,
            distributor_id=distributor.id,
        )
        db.add(distributor_user)
        
        # Create demo retailer user (will be linked after retailer creation)
        print("Creating demo users...")
        await db.commit()
        print("Super admin created: admin@chemistcrm.com / admin123456")
        print("Distributor user created: distributor@demo.com / password123")
        print(f"Distributor ID: {distributor.id}")

if __name__ == "__main__":
    asyncio.run(create_superuser())