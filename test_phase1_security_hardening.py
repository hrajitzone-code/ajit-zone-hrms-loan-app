import os
import sys
import unittest
from datetime import timedelta

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

# Ensure local test key exists for config loading
os.environ.setdefault('SECRET_KEY', 'az-prod-sec-hardening-test-key-2026')

from app import create_app
from config import Config
from models import db, User, Employee, Loan, AuditLog

class TestPhase1SecurityHardening(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()

    def test_01_secret_key_enforcement(self):
        """Test that missing SECRET_KEY fails safely and hardcoded fallback is removed."""
        print("\n[TEST 1] Verifying SECRET_KEY requirement and fallback removal...")
        self.assertIsNotNone(Config.SECRET_KEY)
        self.assertNotEqual(Config.SECRET_KEY, 'ajit-zone-super-secret-key-2026-loan-emi', "Old hardcoded fallback must NOT be used")
        
        # Test that config module raises ValueError when SECRET_KEY is missing from both env and .env
        import unittest.mock as mock
        import importlib
        import config

        orig_key = os.environ.get('SECRET_KEY')
        try:
            os.environ.pop('SECRET_KEY', None)
            with mock.patch('dotenv.load_dotenv', return_value=None):
                with self.assertRaises(ValueError) as ctx:
                    importlib.reload(config)
                self.assertIn("CRITICAL SECURITY CONFIGURATION ERROR", str(ctx.exception))
                print("  [PASS] Config correctly raises ValueError when SECRET_KEY is missing.")
        finally:
            if orig_key:
                os.environ['SECRET_KEY'] = orig_key
            importlib.reload(config)

    def test_02_cookie_security_flags(self):
        """Test SESSION_COOKIE_SECURE, HTTPONLY, and SAMESITE."""
        print("\n[TEST 2] Verifying Session Cookie Security flags...")
        self.assertTrue(Config.SESSION_COOKIE_SECURE, "SESSION_COOKIE_SECURE must be True")
        self.assertTrue(Config.SESSION_COOKIE_HTTPONLY, "SESSION_COOKIE_HTTPONLY must be True")
        self.assertEqual(Config.SESSION_COOKIE_SAMESITE, 'Lax', "SESSION_COOKIE_SAMESITE must be 'Lax'")
        self.assertTrue(Config.WTF_CSRF_ENABLED, "WTF_CSRF_ENABLED must be True")
        print("  [PASS] SESSION_COOKIE_SECURE = True")
        print("  [PASS] SESSION_COOKIE_HTTPONLY = True")
        print("  [PASS] SESSION_COOKIE_SAMESITE = 'Lax'")
        print("  [PASS] WTF_CSRF_ENABLED = True")

    def test_03_csrf_rejection_without_token(self):
        """Test that state-changing POST requests without CSRF token are strictly rejected (HTTP 400)."""
        print("\n[TEST 3] Verifying CSRF token rejection on unauthenticated & state-changing POST requests...")
        # Ensure CSRF is enabled in test app
        self.app.config['WTF_CSRF_ENABLED'] = True
        
        # POST to /login without CSRF token
        res = self.client.post('/login', data={'username': 'sakshi', 'password': 'sakshi123'})
        self.assertEqual(res.status_code, 400, f"Expected 400 CSRF rejection, got {res.status_code}")
        print("  [PASS] POST /login without CSRF token rejected with HTTP 400.")

        # POST to /employees/add without CSRF token
        res_emp = self.client.post('/employees/add', data={'emp_id': 'TEST999', 'name': 'Hacker'})
        self.assertEqual(res_emp.status_code, 400, f"Expected 400 CSRF rejection, got {res_emp.status_code}")
        print("  [PASS] POST /employees/add without CSRF token rejected with HTTP 400.")

    def test_04_csrf_acceptance_with_form_and_header(self):
        """Test that state-changing requests WITH CSRF token (form field or X-CSRFToken header) succeed."""
        print("\n[TEST 4] Verifying CSRF acceptance with valid token in form and headers...")
        self.app.config['WTF_CSRF_ENABLED'] = True
        
        # 1. Obtain CSRF token from GET /login
        get_res = self.client.get('/login')
        html = get_res.data.decode('utf-8')
        self.assertIn('name="csrf_token"', html, "Login page must include csrf_token input field")
        
        import re
        m = re.search(r'name="csrf_token"\s+value="([^"]+)"', html)
        self.assertIsNotNone(m, "CSRF token value must be present in HTML")
        token = m.group(1)
        self.assertTrue(len(token) > 20, "CSRF token must be a valid cryptographic string")
        print(f"  [PASS] Successfully extracted CSRF token from login HTML ({token[:12]}...).")

        # 2. Login with form CSRF token
        login_res = self.client.post('/login', data={
            'csrf_token': token,
            'username': 'sakshi',
            'password': 'sakshi123'
        }, follow_redirects=True)
        self.assertEqual(login_res.status_code, 200, f"Expected 200 after login redirect, got {login_res.status_code}")
        print("  [PASS] POST /login with form csrf_token accepted and logged into dashboard.")

        # 3. Extract fresh post-login session CSRF token from base.html meta tag
        dash_html = login_res.data.decode('utf-8')
        meta_match = re.search(r'<meta\s+name="csrf-token"\s+content="([^"]+)"', dash_html)
        self.assertIsNotNone(meta_match, "Logged in pages must contain <meta name='csrf-token'> tag")
        post_login_token = meta_match.group(1)

        # 4. Test AJAX request with X-CSRFToken header using the active session token
        ajax_res = self.client.post('/users/6/permissions', headers={
            'X-CSRFToken': post_login_token,
            'Content-Type': 'application/json'
        }, json={'permissions': {'dashboard': ['view_all']}})
        self.assertEqual(ajax_res.status_code, 200, f"Expected 200 for AJAX with X-CSRFToken, got {ajax_res.status_code}")
        print("  [PASS] AJAX POST with X-CSRFToken header accepted (HTTP 200).")

    def test_05_csrf_exempt_webhook(self):
        """Test that Google Sheets external webhook is exempt from browser CSRF and authenticated via secret token."""
        print("\n[TEST 5] Verifying external Google Sheets webhook CSRF exemption & token authentication...")
        self.app.config['WTF_CSRF_ENABLED'] = True
        
        # 1. Unauthenticated request without token should be blocked with 401
        res_unauth = self.client.post('/api/google-sheets/webhook', json={'action': 'ping'})
        self.assertEqual(res_unauth.status_code, 401, f"Expected 401 Unauthorized without token, got {res_unauth.status_code}")
        print("  [PASS] Webhook without secret token correctly rejected with HTTP 401 Unauthorized.")

        # 2. Authenticated request with token passes authentication and is CSRF exempt
        from utils.google_sheets_sync import get_google_sheets_config
        with self.app.app_context():
            token = get_google_sheets_config().get('google_sheets_webhook_token')

        res_auth = self.client.post(f'/api/google-sheets/webhook?token={token}', json={'action': 'ping'})
        self.assertNotEqual(res_auth.status_code, 400, "Webhook must be @csrf.exempt and not fail with 400 CSRF error")
        self.assertNotEqual(res_auth.status_code, 401, "Webhook with valid token must not fail with 401")
        print(f"  [PASS] /api/google-sheets/webhook authenticated with valid token & exempt from CSRF (Status: {res_auth.status_code}).")

    def test_06_login_rate_limiting(self):
        """Test that excessive login attempts trigger rate limiting (HTTP 429)."""
        print("\n[TEST 6] Verifying login brute-force rate limiting...")
        self.app.config['WTF_CSRF_ENABLED'] = True
        self.app.config['RATELIMIT_ENABLED'] = True

        # Extract token
        get_res = self.client.get('/login')
        import re
        m = re.search(r'name="csrf_token"\s+value="([^"]+)"', get_res.data.decode('utf-8'))
        token = m.group(1)

        # Send rapid requests until rate limit threshold (10 per minute) is reached
        hit_429 = False
        for attempt in range(1, 15):
            res = self.client.post('/login', data={
                'csrf_token': token,
                'username': 'attacker',
                'password': f'badpass{attempt}'
            })
            if res.status_code == 429:
                hit_429 = True
                print(f"  [PASS] Rate limit successfully triggered on attempt #{attempt} (HTTP 429 RateLimitExceeded).")
                self.assertIn(b"Too many login attempts", res.data)
                break

        self.assertTrue(hit_429, "Rate limiter must enforce threshold and return HTTP 429 on excessive attempts")

    def test_07_database_and_records_intact(self):
        """Test that all existing employees, loans, and super admin data remain completely intact."""
        print("\n[TEST 7] Verifying all production data remains intact...")
        with self.app.app_context():
            # Check employees
            emp_count = Employee.query.count()
            self.assertGreaterEqual(emp_count, 77, f"Expected at least 77 employees, got {emp_count}")
            print(f"  [PASS] Employee records intact (Count: {emp_count}).")

            # Check target loan 1: Pramod Dadhich (LN-2026-0001)
            loan1 = Loan.query.filter_by(loan_id='LN-2026-0001').first()
            self.assertIsNotNone(loan1, "LN-2026-0001 must exist")
            self.assertEqual(loan1.loan_amount, 60000.0)
            self.assertEqual(loan1.monthly_emi, 5000.0)
            self.assertEqual(loan1.loan_status, 'Pending')
            print(f"  [PASS] Target loan LN-2026-0001 intact: {loan1.employee.name}, INR {loan1.loan_amount:,.2f}, Status: {loan1.loan_status}.")

            # Check target loan 2: Avinash Mishra (LN-2026-0002)
            loan2 = Loan.query.filter_by(loan_id='LN-2026-0002').first()
            self.assertIsNotNone(loan2, "LN-2026-0002 must exist")
            self.assertEqual(loan2.loan_amount, 25000.0)
            self.assertEqual(loan2.monthly_emi, 2500.0)
            self.assertEqual(loan2.loan_status, 'Pending')
            print(f"  [PASS] Target loan LN-2026-0002 intact: {loan2.employee.name}, INR {loan2.loan_amount:,.2f}, Status: {loan2.loan_status}.")

            # Check Super Admin Sakshi Shukla
            sakshi = User.query.filter_by(username='sakshi').first()
            self.assertIsNotNone(sakshi, "Super Admin Sakshi must exist")
            self.assertTrue(sakshi.is_primary_superadmin)
            self.assertTrue(sakshi.is_active)
            print(f"  [PASS] Super Admin Sakshi Shukla intact and active.")

if __name__ == '__main__':
    unittest.main()
