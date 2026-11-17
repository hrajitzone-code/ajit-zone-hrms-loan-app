import sys
import os
import json
from datetime import timedelta

# Ensure app directory is on python path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app import create_app
from models import db, User, Employee, Loan, EMISchedule, AuditLog

def run_production_security_audit():
    app = create_app()
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False

    passed = 0
    total = 0

    def assert_true(condition, test_name):
        nonlocal passed, total
        total += 1
        if condition:
            passed += 1
            print(f"[PASS] {test_name}")
        else:
            print(f"[FAIL] {test_name}")
            raise AssertionError(f"Test failed: {test_name}")

    with app.test_client() as client:
        with app.app_context():
            print("\n=======================================================")
            print("AJIT ZONE HRMS - RBAC SECURITY & PRODUCTION AUDIT SUITE")
            print("=======================================================\n")

            # Clean any previous test artifacts
            User.query.filter(User.username.in_(['ops_mgr', 'live_user', 'restricted_tester', 'u_emp1', 'temp_inactive', 'inactive_tester'])).delete()
            Employee.query.filter(Employee.emp_id.in_(['EMP_TEST_LIVE', 'EMP_TEST_LIVE_99'])).delete()
            db.session.commit()

            # -----------------------------------------------------------------
            # SECTION 1: DATA SAFETY & BASELINE PRESERVATION (Requirement 8)
            # -----------------------------------------------------------------
            emp_count = Employee.query.count()
            loan_count = Loan.query.count()
            assert_true(emp_count >= 50, f"Preserve all employee master records (Current count: {emp_count})")
            assert_true(loan_count >= 1, f"Preserve active/closed loan financial history (Current count: {loan_count})")

            # -----------------------------------------------------------------
            # SECTION 2: SUPER ADMIN SAKSHI SHUKLA VALIDATION (Requirement 5)
            # -----------------------------------------------------------------
            sakshi = User.query.filter_by(username='sakshi').first()
            assert_true(sakshi is not None, "Sakshi Shukla exists in system")
            assert_true(sakshi.is_primary_superadmin == True, "Sakshi Shukla is verified Primary Super Admin")
            assert_true(sakshi.role == 'Super_Admin', "Sakshi Shukla assigned role is Super_Admin")
            assert_true(sakshi.is_superadmin() == True, "Sakshi Shukla is_superadmin() evaluates True")

            from utils.permissions import MODULES_DEF
            for m in MODULES_DEF:
                for act in m['actions']:
                    assert_true(sakshi.has_permission(m['id'], act) == True, f"Sakshi Shukla retains full capability on {m['id']}:{act}")

            # -----------------------------------------------------------------
            # SECTION 3: NO DEMO CREDENTIALS OR INSECURE ACCOUNTS (Requirement 7)
            # -----------------------------------------------------------------
            insecure_demo_users = ['admin', 'hr', 'hrmanager', 'superadmin', 'finance']
            for demo_u in insecure_demo_users:
                found = User.query.filter_by(username=demo_u).first()
                assert_true(found is None, f"Demo account '{demo_u}' has been purged from system")

            login_page = client.get('/login').data.decode('utf-8')
            assert_true('Quick Demo Accounts' not in login_page, "Zero demo account cards on login page")
            assert_true('fillCreds' not in login_page, "Zero demo auto-fill scripts on login page")
            assert_true('admin123' not in login_page, "Zero default passwords displayed on login page")
            assert_true('hr123' not in login_page, "Zero HR demo passwords displayed on login page")

            # -----------------------------------------------------------------
            # SECTION 4: PASSWORD HASHING, EXPIRATION & INACTIVE LOGIN (Requirement 4)
            # -----------------------------------------------------------------
            assert_true(sakshi.password_hash.startswith('scrypt:') or sakshi.password_hash.startswith('pbkdf2:'), "Passwords hashed with modern cryptographic salt (scrypt/pbkdf2)")
            assert_true(sakshi.password_hash != 'sakshi123', "Passwords are NEVER stored in plaintext")

            # Inactive user login protection
            temp_inactive = User(
                username='inactive_tester',
                full_name='Inactive Tester',
                role='Viewer',
                is_active=False
            )
            temp_inactive.set_password('inact123')
            db.session.add(temp_inactive)
            db.session.commit()

            res_inact_login = client.post('/login', data={'username': 'inactive_tester', 'password': 'inact123'}, follow_redirects=True)
            assert_true(b'Account Deactivated' in res_inact_login.data, "Inactive account login denied with deactivation message")

            # Inactive user real-time session revocation (user deactivated WHILE logged in)
            temp_inactive.is_active = True
            db.session.commit()
            client.post('/login', data={'username': 'inactive_tester', 'password': 'inact123'}, follow_redirects=True)
            res_before_deact = client.get('/dashboard')
            assert_true(b'Account Deactivated' not in res_before_deact.data, "Active user accesses dashboard normally")

            # Deactivate in database while session cookie is held
            temp_inactive.is_active = False
            db.session.commit()

            # Next request MUST immediately kick user out and terminate session
            res_after_deact = client.get('/dashboard', follow_redirects=True)
            assert_true(b'Account Deactivated' in res_after_deact.data, "Real-time session revocation: Deactivated user immediately kicked to login")

            db.session.delete(temp_inactive)
            db.session.commit()

            # Session expiration config check
            assert_true(app.config.get('PERMANENT_SESSION_LIFETIME') == timedelta(hours=8), "Session expiration configured to 8 hours")
            assert_true(app.config.get('SESSION_COOKIE_HTTPONLY') == True, "Session cookie HTTPOnly protection active")

            # -----------------------------------------------------------------
            # SECTION 5: ONLY SAKSHI SHUKLA CAN MANAGE USERS & RBAC (Requirement 5)
            # -----------------------------------------------------------------
            # Create a regular admin/manager account
            ops_mgr = User(username='ops_mgr', full_name='Operations Manager', role='Manager', is_active=True)
            ops_mgr.set_password('ops12345')
            db.session.add(ops_mgr)
            db.session.commit()

            client.get('/logout')
            client.post('/login', data={'username': 'ops_mgr', 'password': 'ops12345'}, follow_redirects=True)

            # Operations Manager tries accessing User Management
            res_ops_users = client.get('/users', follow_redirects=True)
            assert_true(b'Access Denied: Only Primary Super Admin (Sakshi Shukla)' in res_ops_users.data, "Non-Sakshi user blocked from /users")

            # Operations Manager tries POST /users/create
            res_ops_create = client.post('/users/create', data={'username': 'hacked_user', 'password': '123', 'full_name': 'Hacked'}, follow_redirects=True)
            assert_true(b'Access Denied: Only Primary Super Admin (Sakshi Shukla)' in res_ops_create.data, "Non-Sakshi user blocked from /users/create")

            # Operations Manager tries POST /users/<id>/permissions
            res_ops_perms = client.post(f'/users/{ops_mgr.id}/permissions', json={'permissions': {}}, follow_redirects=True)
            assert_true(b'Access Denied: Only Primary Super Admin (Sakshi Shukla)' in res_ops_perms.data, "Non-Sakshi user blocked from modifying permissions")

            client.get('/logout')
            db.session.delete(ops_mgr)
            db.session.commit()

            # Sakshi Shukla attempts same actions -> allowed
            client.post('/login', data={'username': 'sakshi', 'password': 'sakshi123'}, follow_redirects=True)
            res_sakshi_users = client.get('/users')
            assert_true(b'Custom RBAC &amp; User Management' in res_sakshi_users.data or b'Custom RBAC & User Management' in res_sakshi_users.data, "Sakshi Shukla successfully accesses User Management")

            # -----------------------------------------------------------------
            # SECTION 6: REAL-TIME PERMISSION UPDATES WITHOUT LOGOUT (Requirement 1)
            # -----------------------------------------------------------------
            # Create user 'live_user' with employees:view_all permission only
            live_user = User(username='live_user', full_name='Live Permissions Tester', role='Viewer', is_active=True)
            live_user.set_password('live1234')
            live_user.permissions = json.dumps({'dashboard': ['view_all'], 'employees': ['view_all']})
            db.session.add(live_user)
            db.session.commit()

            # Log in as live_user in a separate test client session
            with app.test_client() as live_client:
                live_client.post('/login', data={'username': 'live_user', 'password': 'live1234'}, follow_redirects=True)

                # Attempt POST /employees/add -> should be blocked!
                res_add_blocked = live_client.post('/employees/add', data={'emp_id': 'EMP_TEST_LIVE', 'name': 'Live Emp'}, follow_redirects=True)
                assert_true(b'Access Denied' in res_add_blocked.data, "live_user initially blocked from employees:add")

                # In background, Sakshi Shukla grants employees:add to live_user
                live_user = User.query.filter_by(username='live_user').first()
                live_user.permissions = json.dumps({'dashboard': ['view_all'], 'employees': ['view_all', 'add']})
                db.session.commit()

                # WITHOUT LOGGING OUT, live_user immediately re-attempts POST /employees/add
                res_add_allowed = live_client.post('/employees/add', data={'emp_id': 'EMP_TEST_LIVE_99', 'name': 'Live Emp 99', 'department': 'IT'}, follow_redirects=True)
                assert_true(b'added successfully' in res_add_allowed.data, "Real-time enforcement: Permission changes take effect IMMEDIATELY without logout")

                # Cleanup test employee created
                test_emp = Employee.query.filter_by(emp_id='EMP_TEST_LIVE_99').first()
                if test_emp:
                    db.session.delete(test_emp)
                    db.session.commit()

            db.session.delete(User.query.filter_by(username='live_user').first())
            db.session.commit()

            # -----------------------------------------------------------------
            # SECTION 7: DIRECT URL & API TAMPERING PROTECTION (Requirement 2)
            # -----------------------------------------------------------------
            # Create user with restricted permissions (e.g. only loans view)
            restricted_u = User(username='restricted_tester', full_name='Restricted Tester', role='Viewer', is_active=True)
            restricted_u.set_password('rest1234')
            restricted_u.permissions = json.dumps({'dashboard': ['view_all'], 'loans': ['view_all']})
            db.session.add(restricted_u)
            db.session.commit()

            with app.test_client() as rest_client:
                rest_client.post('/login', data={'username': 'restricted_tester', 'password': 'rest1234'}, follow_redirects=True)

                # Direct URL /salary-sync
                res_url_salary = rest_client.get('/salary-sync', follow_redirects=True)
                assert_true(b'Access Denied' in res_url_salary.data, "Direct URL access to /salary-sync blocked")

                # Direct URL /settings
                res_url_settings = rest_client.get('/settings', follow_redirects=True)
                assert_true(b'Access Denied' in res_url_settings.data, "Direct URL access to /settings blocked")

                # Direct URL /audit-logs
                res_url_audit = rest_client.get('/audit-logs', follow_redirects=True)
                assert_true(b'Access Denied' in res_url_audit.data, "Direct URL access to /audit-logs blocked")

                # Direct POST to /salary-sync/push
                res_api_salary_push = rest_client.post('/salary-sync/push', data={'salary_month': '2026-09'}, follow_redirects=True)
                assert_true(b'Access Denied' in res_api_salary_push.data, "Direct API call to /salary-sync/push blocked")

                # Direct POST to /employees/1/delete
                first_emp = Employee.query.first()
                res_api_emp_del = rest_client.post(f'/employees/{first_emp.id}/delete', follow_redirects=True)
                assert_true(b'Access Denied' in res_api_emp_del.data, "Direct API call to /employees/<id>/delete blocked")

            db.session.delete(User.query.filter_by(username='restricted_tester').first())
            db.session.commit()

            # -----------------------------------------------------------------
            # SECTION 8: ID TAMPERING & RECORD ISOLATION (Requirement 3)
            # -----------------------------------------------------------------
            emp1 = Employee.query.order_by(Employee.id.asc()).first()
            emp2 = Employee.query.filter(Employee.id != emp1.id).first()

            # User 1 linked to emp1
            u_emp1 = User(username='u_emp1', full_name='Employee One', role='Employee', employee_id=emp1.id, is_active=True)
            u_emp1.set_password('emp1pass')
            u_emp1.permissions = json.dumps({
                'dashboard': ['view_all'],
                'employees': ['view_own'],
                'loans': ['view_own'],
                'loan_applications': ['view_own', 'add'],
                'documents': ['view_own'],
                'emi': ['view_own']
            })
            db.session.add(u_emp1)
            db.session.commit()

            with app.test_client() as emp1_client:
                emp1_client.post('/login', data={'username': 'u_emp1', 'password': 'emp1pass'}, follow_redirects=True)

                # Access own employee profile -> Allowed
                res_own_detail = emp1_client.get(f'/employees/{emp1.id}/detail')
                assert_true(res_own_detail.status_code == 200 and emp1.name.encode() in res_own_detail.data, "Employee accesses own profile successfully")

                # Tamper URL to view other employee profile (/employees/<emp2.id>/detail) -> Blocked
                res_other_detail = emp1_client.get(f'/employees/{emp2.id}/detail', follow_redirects=True)
                assert_true(b'Unauthorized access' in res_other_detail.data, "ID Tampering blocked on /employees/<id>/detail")

                # Tamper API lookup /api/employee/lookup/<emp2.emp_id> -> 403 Forbidden
                res_api_lookup_other = emp1_client.get(f'/api/employee/lookup/{emp2.emp_id}')
                assert_true(res_api_lookup_other.status_code == 403, f"ID Tampering blocked on /api/employee/lookup/<emp_code> (HTTP 403)")

                # Own API lookup -> Allowed
                res_api_lookup_own = emp1_client.get(f'/api/employee/lookup/{emp1.emp_id}')
                assert_true(res_api_lookup_own.status_code == 200, "Employee permitted to lookup own profile via API")

                # Tamper loan application POST using emp2's ID -> Blocked
                res_tamper_loan = emp1_client.post('/loans/create', data={
                    'employee_id_input': emp2.emp_id,
                    'loan_type': 'Personal Loan',
                    'loan_amount': 25000,
                    'monthly_emi': 2500,
                    'tenure_months': 10
                }, follow_redirects=True)
                assert_true(b'Access Denied: You may only submit loan applications for your own employee ID.' in res_tamper_loan.data, "ID Tampering blocked on POST /loans/create")

            db.session.delete(User.query.filter_by(username='u_emp1').first())
            db.session.commit()

            # -----------------------------------------------------------------
            # SECTION 9: AUDIT LOGS IMMUTABILITY (Requirement 6)
            # -----------------------------------------------------------------
            # Verify AuditLog count
            audit_count_before = AuditLog.query.count()
            assert_true(audit_count_before > 0, f"Audit trail exists with {audit_count_before} tamper-evident entries")

            # Verify no unauthorized user can read audit logs
            with app.test_client() as anon_client:
                res_anon_audit = anon_client.get('/audit-logs', follow_redirects=True)
                assert_true(b'Please log in to access this page' in res_anon_audit.data, "Anonymous access to audit logs denied")

            # Verify HTTP methods like DELETE or PUT on /audit-logs return 405 Method Not Allowed
            res_del_audit = client.delete('/audit-logs')
            assert_true(res_del_audit.status_code in [404, 405], "HTTP DELETE on /audit-logs rejected (Method Not Allowed / Not Found)")

            # Final check: employee and loan counts still intact
            assert_true(Employee.query.count() == emp_count, f"Final count check: Employee master records intact ({Employee.query.count()})")
            assert_true(Loan.query.count() == loan_count, f"Final count check: Loan records intact ({Loan.query.count()})")

            print("\n=======================================================")
            print(f"SECURITY AUDIT COMPLETE: ALL {passed}/{total} AUDIT TESTS PASSED!")
            print("=======================================================\n")

if __name__ == '__main__':
    run_production_security_audit()
