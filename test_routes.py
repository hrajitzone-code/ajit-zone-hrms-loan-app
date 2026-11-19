import sys
import os

sys.path.insert(0, os.path.abspath('c:/Users/Sakshi/OneDrive/Documents/My Projects/ajit_zone_loan_app'))

from app import create_app
from models import db, User

app = create_app()
app.config['TESTING'] = True
app.config['WTF_CSRF_ENABLED'] = False

def test_routes_rendering():
    with app.test_client() as client:
        # Test Login page
        res = client.get('/login')
        assert res.status_code == 200, f"Login route status {res.status_code}"
        print("[SUCCESS] /login rendered 200 OK")

        # Login as Super_Admin Sakshi Shukla
        login_res = client.post('/login', data={'username': 'sakshi', 'password': 'sakshi123'}, follow_redirects=True)
        assert login_res.status_code == 200, f"Dashboard status {login_res.status_code}"
        print("[SUCCESS] Login POST & redirect to /dashboard rendered 200 OK")

        routes_to_test = [
            '/dashboard',
            '/employees',
            '/employees/import',
            '/loans',
            '/loans/create',
            '/emi/management',
            '/emi/adjustments',
            '/salary-sync',
            '/users',
            '/reports',
            '/audit-logs',
            '/settings',
            '/api/dashboard/chart-data',
            '/api/employee/lookup/EMP0001'
        ]

        for r in routes_to_test:
            r_res = client.get(r)
            assert r_res.status_code == 200, f"Route {r} failed with status {r_res.status_code}"
            print(f"[SUCCESS] Route {r} rendered 200 OK")

    print("\n=== ALL 14 ROUTES TESTED & RENDERING 200 OK! ===")

if __name__ == '__main__':
    test_routes_rendering()
