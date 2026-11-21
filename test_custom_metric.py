import os
import json
import unittest
from app import create_app
from models import db, User, AuditLog
from utils.permissions import MODULES_DEF

class CustomMetricSaveTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config['WTF_CSRF_ENABLED'] = True
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()

    def login_as_sakshi(self):
        sakshi = User.query.filter_by(username='sakshi').first()
        with self.client.session_transaction() as sess:
            sess['user_id'] = sakshi.id
            sess['username'] = sakshi.username
            sess['role'] = sakshi.role
            sess['is_primary_superadmin'] = sakshi.is_primary_superadmin

    def get_csrf_token(self):
        res = self.client.get('/users')
        import re
        html = res.get_data(as_text=True)
        m = re.search(r'<meta\s+name=["\']csrf-token["\']\s+content=["\']([^"\']+)["\']', html)
        if m:
            return m.group(1)
        m2 = re.search(r'name=["\']csrf_token["\']\s+value=["\']([^"\']+)["\']', html)
        if m2:
            return m2.group(1)
        return ''

    def test_save_custom_metric_flow(self):
        with self.app.app_context():
            self.login_as_sakshi()
            csrf = self.get_csrf_token()
            self.assertTrue(bool(csrf), "CSRF token must be present")

            # Target user: Pradeep Gothwal (ID: 7, Manager)
            pradeep = User.query.filter_by(username='Pradeep Gothwal').first()
            if not pradeep:
                pradeep = User.query.filter(User.username != 'sakshi').first()
            self.assertIsNotNone(pradeep, "Secondary user must exist for custom metric test")
            user_id = pradeep.id

            # 1. TEST FORM SUBMISSION (Simulating clicking 'Save Custom Metric' in Modal)
            form_payload = {
                'csrf_token': csrf,
                'active_tab': 'users',
                'perm_loans': ['view_all', 'approve'],
                'perm_employees': ['view_all']
            }
            res_form = self.client.post(f'/users/{user_id}/permissions', data=form_payload, follow_redirects=True)
            self.assertEqual(res_form.status_code, 200)
            page_text = res_form.get_data(as_text=True)
            self.assertTrue("Custom metric" in page_text)
            self.assertTrue("Custom Matrix" in page_text)

            # Verify in DB
            db.session.expire_all()
            user_saved = User.query.get(user_id)
            self.assertIsNotNone(user_saved.permissions, "User permissions in DB must not be None after save")
            perms_dict = json.loads(user_saved.permissions)
            self.assertIn('loans', perms_dict)
            self.assertEqual(perms_dict['loans'], ['view_all', 'approve'])
            self.assertIn('employees', perms_dict)
            self.assertEqual(perms_dict['employees'], ['view_all'])
            print("\n[PASS] 1. Form POST 'Save Custom Metric' saved to DB and persisted successfully.")

            # 2. TEST AJAX JSON SUBMISSION (Simulating Tab 2 'Save Custom Metric' interactive matrix)
            json_payload = {
                'permissions': {
                    'loans': ['view_all', 'approve', 'add'],
                    'salary': ['view_all', 'export'],
                    'reports': ['view_all']
                }
            }
            res_json = self.client.post(
                f'/users/{user_id}/permissions',
                json=json_payload,
                headers={'X-CSRFToken': csrf, 'X-Requested-With': 'XMLHttpRequest'}
            )
            self.assertEqual(res_json.status_code, 200)
            json_data = res_json.get_json()
            self.assertTrue(json_data.get('success'), "AJAX response must indicate success")
            self.assertIn("Custom metric", json_data.get('message'))

            # Verify in DB after Edit
            db.session.expire_all()
            user_edited = User.query.get(user_id)
            perms_edited = json.loads(user_edited.permissions)
            self.assertIn('salary', perms_edited)
            self.assertEqual(perms_edited['salary'], ['view_all', 'export'])
            self.assertIn('add', perms_edited['loans'])
            print("[PASS] 2. AJAX JSON 'Save Custom Metric' edited and updated DB successfully.")

            # 3. TEST PAGE REFRESH & PERSISTENCE
            res_refresh = self.client.get('/users?tab=users')
            self.assertEqual(res_refresh.status_code, 200)
            refresh_text = res_refresh.get_data(as_text=True)
            self.assertIn("Custom Matrix &amp; Metric Configured", refresh_text.replace('&', '&amp;'))
            print("[PASS] 3. Page refresh verified: Custom metric persists across requests.")

            # 4. TEST RESET / DELETE OF CUSTOM METRIC
            reset_payload = {
                'csrf_token': csrf,
                'active_tab': 'users'
            }
            res_reset = self.client.post(f'/users/{user_id}/reset-permissions', data=reset_payload, follow_redirects=True)
            self.assertEqual(res_reset.status_code, 200)

            db.session.expire_all()
            user_reset = User.query.get(user_id)
            self.assertIsNone(user_reset.permissions, "User permissions must be reset to None")
            print("[PASS] 4. Reset / Delete custom metric verified: Reverted to role defaults.")

if __name__ == '__main__':
    unittest.main()
