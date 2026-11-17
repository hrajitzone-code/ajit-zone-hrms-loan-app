import sys
import os
import json

# Ensure app directory is on python path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app import create_app
from models import db, User, Employee, Loan, AuditLog

def run_tests():
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
            print("\n==========================================")
            print("AJIT ZONE HRMS - RBAC VERIFICATION SUITE")
            print("==========================================\n")

            # TEST 1: Database records preserved
            emp_count = Employee.query.count()
            loan_count = Loan.query.count()
            assert_true(emp_count >= 50, f"Preserve Employee records (count={emp_count} >= 50)")
            assert_true(loan_count >= 1, f"Preserve Loan records (count={loan_count} >= 1)")

            # TEST 2: Primary Super Admin exists & protected
            sakshi = User.query.filter_by(username='sakshi').first()
            assert_true(sakshi is not None, "Sakshi Shukla exists in database")
            assert_true(sakshi.is_primary_superadmin == True, "Sakshi Shukla has is_primary_superadmin == True")
            assert_true(sakshi.role == 'Super_Admin', "Sakshi Shukla role is Super_Admin")
            assert_true(sakshi.is_superadmin() == True, "Sakshi Shukla is_superadmin() returns True")

            # Check permissions for Sakshi (100% full access to all 12 modules)
            from utils.permissions import MODULES_DEF
            for m in MODULES_DEF:
                for act in m['actions']:
                    assert_true(sakshi.has_permission(m['id'], act) == True, f"Sakshi Shukla has {m['id']}:{act}")

            # TEST 3: Login Page has no demo credentials or buttons
            login_page = client.get('/login').data.decode('utf-8')
            assert_true('Quick Demo Accounts' not in login_page, "No 'Quick Demo Accounts' on login page")
            assert_true('fillCreds' not in login_page, "No 'fillCreds' JavaScript on login page")
            assert_true('admin123' not in login_page, "No demo password 'admin123' displayed")
            assert_true('Sign In to Workspace' in login_page, "Professional clean login form present")

            # TEST 4: Invalid logins denied
            res_bad_pw = client.post('/login', data={'username': 'sakshi', 'password': 'wrongpassword'}, follow_redirects=True)
            assert_true(b'Invalid username or password' in res_bad_pw.data, "Invalid password correctly denied")

            res_bad_user = client.post('/login', data={'username': 'nonexistent_user_xyz', 'password': 'any'}, follow_redirects=True)
            assert_true(b'Invalid username or password' in res_bad_user.data, "Non-existent user correctly denied")

            # TEST 5: Sakshi Shukla can log in
            res_login = client.post('/login', data={'username': 'sakshi', 'password': 'sakshi123'}, follow_redirects=True)
            assert_true(b'Welcome back, Sakshi Shukla!' in res_login.data, "Sakshi Shukla login successful")
            assert_true(b'Custom RBAC &amp; User Management' in client.get('/users').data or b'Custom RBAC & User Management' in client.get('/users').data, "Super Admin Sakshi Shukla can access /users")

            # TEST 6: Super Admin protection against deletion & deactivation
            # Try deactivating Sakshi
            res_deact = client.post(f'/users/{sakshi.id}/toggle-status', follow_redirects=True)
            assert_true(b'cannot be deactivated' in res_deact.data, "Sakshi Shukla is protected from deactivation")
            sakshi = User.query.filter_by(username='sakshi').first()
            assert_true(sakshi.is_active == True, "Sakshi Shukla is_active remains True")

            # Try deleting Sakshi
            res_del = client.post(f'/users/{sakshi.id}/delete', follow_redirects=True)
            assert_true(b'cannot be deleted under any circumstances' in res_del.data, "Sakshi Shukla is protected from deletion")
            sakshi = User.query.filter_by(username='sakshi').first()
            assert_true(sakshi is not None, "Sakshi Shukla account still exists after delete attempt")

            # Try demoting Sakshi's role
            res_demote = client.post(f'/users/{sakshi.id}/edit', data={'role': 'HR', 'full_name': 'Sakshi Shukla', 'email': 'sakshi@ajitzone.com'}, follow_redirects=True)
            assert_true(b'cannot have their Super Admin role changed' in res_demote.data, "Sakshi Shukla cannot be demoted")
            sakshi = User.query.filter_by(username='sakshi').first()
            assert_true(sakshi.role == 'Super_Admin', "Sakshi Shukla role remains Super_Admin")

            # TEST 7: Super Admin creates a new user with custom permissions
            test_username = 'test_clerk'
            existing_clerk = User.query.filter_by(username=test_username).first()
            if existing_clerk:
                db.session.delete(existing_clerk)
                db.session.commit()

            res_create = client.post('/users/create', data={
                'username': test_username,
                'password': 'clerkpassword123',
                'full_name': 'Test Clerk',
                'email': 'clerk@ajitzone.com',
                'role': 'Viewer'
            }, follow_redirects=True)
            assert_true(b'created successfully' in res_create.data, f"New User '{test_username}' created successfully")
            
            clerk = User.query.filter_by(username=test_username).first()
            assert_true(clerk is not None, "Clerk found in DB")

            # Set custom permission matrix: only view_all and add on employees, no edit/delete
            custom_perms = {
                'employees': ['view_all', 'add'],
                'dashboard': ['view_all']
            }
            res_perms = client.post(f'/users/{clerk.id}/permissions', json={'permissions': custom_perms})
            assert_true(res_perms.status_code == 200 and res_perms.get_json()['success'] == True, "Saved custom permissions matrix via AJAX JSON")

            # Reload user and check permissions
            db.session.expire_all()
            clerk = User.query.filter_by(username=test_username).first()
            assert_true(clerk.has_permission('employees', 'view') == True, "Clerk has 'employees:view'")
            assert_true(clerk.has_permission('employees', 'add') == True, "Clerk has 'employees:add'")
            assert_true(clerk.has_permission('employees', 'edit') == False, "Clerk DOES NOT have 'employees:edit'")
            assert_true(clerk.has_permission('employees', 'delete') == False, "Clerk DOES NOT have 'employees:delete'")
            assert_true(clerk.has_permission('settings', 'manage') == False, "Clerk DOES NOT have 'settings:manage'")

            # TEST 8: Test Clerk logs in and attempts unauthorized actions
            client.get('/logout')
            res_clerk_login = client.post('/login', data={'username': test_username, 'password': 'clerkpassword123'}, follow_redirects=True)
            assert_true(b'Welcome back, Test Clerk!' in res_clerk_login.data, "Clerk logged in successfully")

            # Clerk attempts to access User Management (Super Admin only) -> blocked!
            res_clerk_users = client.get('/users', follow_redirects=True)
            assert_true(b'Access Denied' in res_clerk_users.data, "Clerk blocked from /users (Super Admin console)")

            # Clerk attempts to access System Settings -> blocked!
            res_clerk_settings = client.get('/settings', follow_redirects=True)
            assert_true(b'Access Denied' in res_clerk_settings.data, "Clerk blocked from /settings")

            # Clerk attempts to delete an employee -> blocked by backend permission check!
            first_emp = Employee.query.first()
            res_clerk_del_emp = client.post(f'/employees/{first_emp.id}/delete', follow_redirects=True)
            assert_true(b'Access Denied' in res_clerk_del_emp.data, "Clerk blocked from deleting employee (Backend Guarded)")

            # Clerk attempts to edit an employee -> blocked by backend permission check!
            res_clerk_edit_emp = client.post(f'/employees/{first_emp.id}/edit', data={'name': 'Hacked Name'}, follow_redirects=True)
            assert_true(b'Access Denied' in res_clerk_edit_emp.data, "Clerk blocked from editing employee (Backend Guarded)")

            # TEST 9: Employee Role & View Own scoping
            # Create an employee user linked to emp 1
            emp_user_name = 'emp_user_test'
            existing_emp_user = User.query.filter_by(username=emp_user_name).first()
            if existing_emp_user:
                db.session.delete(existing_emp_user)
                db.session.commit()

            emp_user = User(
                username=emp_user_name,
                full_name='Scoped Employee',
                role='Employee',
                employee_id=first_emp.id,
                is_active=True
            )
            emp_user.set_password('pass123')
            db.session.add(emp_user)
            db.session.commit()

            client.get('/logout')
            client.post('/login', data={'username': emp_user_name, 'password': 'pass123'}, follow_redirects=True)
            
            # When scoped employee accesses /employees, only their OWN record is returned
            res_emp_list = client.get('/employees').data.decode('utf-8')
            assert_true(first_emp.emp_id in res_emp_list, "Scoped employee sees their own record")
            # Other employee (e.g. emp 2) should NOT be displayed
            other_emp = Employee.query.filter(Employee.id != first_emp.id).first()
            if other_emp:
                assert_true(other_emp.name not in res_emp_list, f"Scoped employee cannot see other employee '{other_emp.name}'")

            # Clean up test users
            client.get('/logout')
            with app.app_context():
                User.query.filter(User.username.in_([test_username, emp_user_name])).delete()
                db.session.commit()

            print("\n==========================================")
            print(f"ALL {passed}/{total} RBAC VERIFICATION TESTS PASSED SUCCESSFULLY!")
            print("==========================================\n")

if __name__ == '__main__':
    run_tests()
