import unittest
from datetime import datetime, date
from app import create_app
from models import db, User, Employee, Loan, EMISchedule, AuditLog

class TestLoanDeletion(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config['TESTING'] = True
        self.app.config['WTF_CSRF_ENABLED'] = False
        self.client = self.app.test_client()

    def test_loan_deletion_workflow(self):
        with self.app.app_context():
            # 1. Login as Super Admin Sakshi Shukla
            res = self.client.post('/login', data={'username': 'sakshi', 'password': 'sakshi123'}, follow_redirects=True)
            self.assertEqual(res.status_code, 200)

            # 2. Get an employee to create a test loan for
            emp = Employee.query.first()
            self.assertIsNotNone(emp)

            # Record initial counts
            initial_loans_count = Loan.query.count()
            initial_audit_count = AuditLog.query.count()

            # 3. Create a test loan
            test_loan_code = f"LN-TEST-{datetime.now().strftime('%H%M%S')}"
            test_loan = Loan(
                loan_id=test_loan_code,
                employee_id=emp.id,
                loan_type='Personal Loan',
                loan_amount=25000.0,
                monthly_emi=2500.0,
                interest_rate=0.0,
                emi_start_date=date.today(),
                emi_deduction_day=5,
                tenure_months=10,
                approval_status='Approved',
                loan_status='Active',
                workflow_status='Approved',
                total_recovered=5000.0,
                outstanding_balance=20000.0
            )
            db.session.add(test_loan)
            db.session.flush()

            # Add test schedules
            for i in range(1, 11):
                sch = EMISchedule(
                    loan_id=test_loan.id,
                    emi_no=i,
                    due_date=date.today(),
                    scheduled_emi=2500.0,
                    actual_deduction=2500.0 if i <= 2 else 0.0,
                    outstanding_after=25000.0 - (i * 2500.0),
                    status='Deducted' if i <= 2 else 'Upcoming'
                )
                db.session.add(sch)
            db.session.commit()

            test_loan_pk = test_loan.id
            self.assertEqual(EMISchedule.query.filter_by(loan_id=test_loan_pk).count(), 10)

            # 4. Verify loan appears in list and UI contains delete option
            list_res = self.client.get('/loans')
            self.assertEqual(list_res.status_code, 200)
            list_html = list_res.data.decode('utf-8')
            self.assertIn(test_loan_code, list_html)
            self.assertIn('confirmDeleteLoan', list_html)
            self.assertIn('bulkDeleteLoanModal', list_html)

            # 5. Verify loan detail page contains delete option
            view_res = self.client.get(f'/loans/{test_loan_pk}')
            self.assertEqual(view_res.status_code, 200)
            view_html = view_res.data.decode('utf-8')
            self.assertIn('Delete Loan', view_html)
            self.assertIn('id="deleteLoanModal"', view_html)

            # 6. Test Single Delete via POST /loans/<id>/delete
            del_res = self.client.post(f'/loans/{test_loan_pk}/delete', data={
                'delete_reason': 'Test single deletion verification'
            }, follow_redirects=True)
            self.assertEqual(del_res.status_code, 200)

            # Verify loan and schedules are gone
            self.assertIsNone(Loan.query.get(test_loan_pk))
            self.assertEqual(EMISchedule.query.filter_by(loan_id=test_loan_pk).count(), 0)
            self.assertEqual(Loan.query.count(), initial_loans_count)

            # Verify AuditLog created
            audit = AuditLog.query.filter_by(record_id=test_loan_code, action='DELETE').first()
            self.assertIsNotNone(audit)
            self.assertEqual(audit.module, 'Loans')
            self.assertIn('Test single deletion verification', audit.reason)
            self.assertIn('Sakshi Shukla', audit.reason)

            # 7. Test Bulk Delete: Create 2 test loans
            bulk_code_1 = f"LN-BULK1-{datetime.now().strftime('%H%M%S')}"
            bulk_code_2 = f"LN-BULK2-{datetime.now().strftime('%H%M%S')}"

            l1 = Loan(loan_id=bulk_code_1, employee_id=emp.id, loan_type='Emergency Advance', loan_amount=10000.0, monthly_emi=1000.0, emi_start_date=date.today(), emi_deduction_day=5, tenure_months=10, approval_status='Pending', loan_status='Pending', workflow_status='Submitted')
            l2 = Loan(loan_id=bulk_code_2, employee_id=emp.id, loan_type='Salary Advance', loan_amount=15000.0, monthly_emi=1500.0, emi_start_date=date.today(), emi_deduction_day=5, tenure_months=10, approval_status='Pending', loan_status='Pending', workflow_status='Submitted')
            db.session.add_all([l1, l2])
            db.session.commit()

            l1_id, l2_id = l1.id, l2.id

            # Execute Bulk Delete
            bulk_res = self.client.post('/loans/bulk-delete', data={
                'selected_loan_ids': f"{l1_id},{l2_id}",
                'bulk_delete_reason': 'Batch cleanup test'
            }, follow_redirects=True)
            self.assertEqual(bulk_res.status_code, 200)

            # Verify both are deleted
            self.assertIsNone(Loan.query.get(l1_id))
            self.assertIsNone(Loan.query.get(l2_id))
            self.assertEqual(Loan.query.count(), initial_loans_count)

            # Verify AuditLog created for both
            audit1 = AuditLog.query.filter_by(record_id=bulk_code_1, action='DELETE').first()
            audit2 = AuditLog.query.filter_by(record_id=bulk_code_2, action='DELETE').first()
            self.assertIsNotNone(audit1)
            self.assertIsNotNone(audit2)

            # 8. Test Unauthorized user cannot delete
            # Create a regular employee user without delete permission
            test_user = User.query.filter_by(username='test_loan_user').first()
            if not test_user:
                test_user = User(
                    username='test_loan_user',
                    full_name='Test Regular User',
                    role='Employee',
                    employee_id=emp.id,
                    is_active=True
                )
                test_user.set_password('pass123')
                db.session.add(test_user)
                db.session.commit()

            self.client.get('/logout')
            self.client.post('/login', data={'username': 'test_loan_user', 'password': 'pass123'}, follow_redirects=True)

            # Create another loan to test unauthorized delete attempt
            unauth_code = f"LN-UNAUTH-{datetime.now().strftime('%H%M%S')}"
            unauth_loan = Loan(loan_id=unauth_code, employee_id=emp.id, loan_type='Personal', loan_amount=5000.0, monthly_emi=500.0, emi_start_date=date.today(), emi_deduction_day=5, tenure_months=10, approval_status='Pending', loan_status='Pending', workflow_status='Submitted')
            db.session.add(unauth_loan)
            db.session.commit()
            unauth_id = unauth_loan.id

            # Regular employee attempts delete -> should be blocked
            blocked_res = self.client.post(f'/loans/{unauth_id}/delete', data={'delete_reason': 'Hacker delete'}, follow_redirects=True)
            self.assertIn('Permission Denied', blocked_res.data.decode('utf-8'))
            # Loan must still exist
            self.assertIsNotNone(Loan.query.get(unauth_id))

            # Cleanup
            db.session.delete(unauth_loan)
            db.session.delete(test_user)
            db.session.commit()

            # Final verify: count matches initial count
            self.assertEqual(Loan.query.count(), initial_loans_count)
            print("\n[PASS] All Loan Deletion unit & integration checks succeeded!")

if __name__ == '__main__':
    unittest.main()
