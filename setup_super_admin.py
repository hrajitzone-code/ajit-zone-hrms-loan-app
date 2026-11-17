import sys
import os

sys.path.insert(0, os.path.abspath('c:/Users/Sakshi/OneDrive/Documents/My Projects/ajit_zone_loan_app'))

from app import create_app
from models import db, User

app = create_app()

def setup_sakshi_superadmin():
    with app.app_context():
        # Check if sakshi user exists
        sakshi_user = User.query.filter_by(username='sakshi').first()
        if not sakshi_user:
            sakshi_user = User(
                username='sakshi',
                full_name='Sakshi Shukla',
                role='Super_Admin',
                email='sakshi.shukla@ajitzone.com',
                is_active=True,
                is_primary_superadmin=True
            )
            sakshi_user.set_password('sakshi123')
            db.session.add(sakshi_user)
            print("[CREATED] Primary Super Admin user 'sakshi' (Sakshi Shukla) created successfully.")
        else:
            sakshi_user.full_name = 'Sakshi Shukla'
            sakshi_user.role = 'Super_Admin'
            sakshi_user.is_primary_superadmin = True
            sakshi_user.is_active = True
            print("[UPDATED] Primary Super Admin user 'sakshi' verified and updated.")

        # Also update existing 'superadmin' account if it exists
        legacy_sa = User.query.filter_by(username='superadmin').first()
        if legacy_sa:
            legacy_sa.full_name = 'Super Admin (Sakshi Shukla)'
            legacy_sa.role = 'Super_Admin'
            legacy_sa.is_primary_superadmin = True

        db.session.commit()
        print("[SUCCESS] Sakshi Shukla is confirmed as the Primary Super Admin.")

if __name__ == '__main__':
    setup_sakshi_superadmin()
