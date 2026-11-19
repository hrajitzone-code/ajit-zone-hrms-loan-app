import sys
import os
import io

sys.path.insert(0, os.path.abspath('c:/Users/Sakshi/OneDrive/Documents/My Projects/ajit_zone_loan_app'))

from app import create_app
from models import db, User, Employee, Loan, AuditLog, ImportLog
from datetime import datetime, date

app = create_app()
app.config['TESTING'] = True
app.config['WTF_CSRF_ENABLED'] = False

def run_tests():
    print("==================================================")
    print("STARTING TEST SUITE: HRMS LOAN MANAGEMENT ENHANCEMENTS")
    print("==================================================")

    with app.test_client() as client:
        # 1. Login
        login_res = client.post('/login', data={'username': 'sakshi', 'password': 'sakshi123'}, follow_redirects=True)
        assert login_res.status_code == 200
        print("[PASS] Super_Admin login verified.")

        # 2. Test Employee Auto-Fetch API
        res = client.get('/api/employee/lookup/EMP0001')
        assert res.status_code == 200
        data = res.get_json()
        assert data['success'] is True
        emp = data['employee']
        assert 'emp_id' in emp
        assert 'name' in emp
        assert 'department' in emp
        assert 'designation' in emp
        assert 'current_salary' in emp
        assert 'joining_date' in emp
        assert 'active_loans_count' in emp
        assert 'total_outstanding' in emp
        print(f"[PASS] Auto-Fetch API verified: {emp['emp_id']} - {emp['name']}, Salary: {emp['current_salary']}, Active Loans: {emp['active_loans_count']}")

        # 3. Test Blank Template Downloads
        res_xlsx = client.get('/employees/template/download?format=xlsx')
        assert res_xlsx.status_code == 200
        assert 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' in res_xlsx.content_type
        assert len(res_xlsx.data) > 1000
        print(f"[PASS] Blank Excel template download verified ({len(res_xlsx.data)} bytes).")

        res_csv = client.get('/employees/template/download?format=csv')
        assert res_csv.status_code == 200
        assert 'text/csv' in res_csv.content_type
        csv_text = res_csv.data.decode('utf-8')
        assert 'Employee ID' in csv_text
        assert 'Full Name' in csv_text
        print("[PASS] Blank CSV template download verified.")

        # 4. Test Employee Directory Export
        res_exp_xlsx = client.get('/employees/export?format=xlsx')
        assert res_exp_xlsx.status_code == 200
        assert len(res_exp_xlsx.data) > 1000
        print(f"[PASS] Employee directory export (Excel) verified ({len(res_exp_xlsx.data)} bytes).")

        res_exp_csv = client.get('/employees/export?format=csv')
        assert res_exp_csv.status_code == 200
        assert 'Employee ID' in res_exp_csv.data.decode('utf-8')
        print("[PASS] Employee directory export (CSV) verified.")

        # 5. Test Selective Single Delete: Employee WITH NO LOANS
        with app.app_context():
            # Create a test employee with no loans
            test_emp = Employee(
                emp_id='TEST_NOLOAN_001',
                name='Test User No Loan',
                department='Testing',
                designation='QA',
                current_salary=30000.0,
                status='Active'
            )
            db.session.add(test_emp)
            db.session.commit()
            test_emp_id = test_emp.id

        del_res = client.post(f'/employees/{test_emp_id}/delete', data={'delete_reason': 'Testing delete with no loans'}, follow_redirects=True)
        assert del_res.status_code == 200

        with app.app_context():
            deleted = Employee.query.get(test_emp_id)
            assert deleted is None, "Employee should have been permanently deleted!"
            audit_entry = AuditLog.query.filter_by(action='DELETE', record_id='TEST_NOLOAN_001').first()
            assert audit_entry is not None, "Audit log must record deletion!"
            print("[PASS] Employee with NO loans was permanently deleted and logged in AuditLog.")

        # 6. Test Selective Single Delete: Employee WITH LOAN HISTORY (Financial Safety Guard)
        with app.app_context():
            # Create an employee WITH an active/past loan
            test_loan_emp = Employee(
                emp_id='TEST_WITHLOAN_002',
                name='Test User With Loan',
                department='Finance',
                designation='Senior Analyst',
                current_salary=60000.0,
                status='Active'
            )
            db.session.add(test_loan_emp)
            db.session.flush()

            test_loan = Loan(
                loan_id='LN-TEST-9999',
                employee_id=test_loan_emp.id,
                loan_type='Personal Loan',
                loan_amount=50000.0,
                monthly_emi=5000.0,
                emi_start_date=date.today(),
                tenure_months=10,
                loan_status='Active',
                outstanding_balance=50000.0
            )
            db.session.add(test_loan)
            db.session.commit()
            loan_emp_id = test_loan_emp.id
            loan_id_pk = test_loan.id

        # Attempt to delete employee with loan
        loan_del_res = client.post(f'/employees/{loan_emp_id}/delete', data={'delete_reason': 'Trying to delete loan emp'}, follow_redirects=True)
        assert loan_del_res.status_code == 200

        with app.app_context():
            not_deleted = Employee.query.get(loan_emp_id)
            assert not_deleted is not None, "Employee with loans must NOT be permanently deleted!"
            assert not_deleted.status == 'Inactive', f"Employee should be Inactive (Archived), found {not_deleted.status}"
            audit_archive = AuditLog.query.filter_by(action='ARCHIVE', record_id='TEST_WITHLOAN_002').first()
            assert audit_archive is not None, "Audit log must record ARCHIVE action!"
            print(f"[PASS] Employee with LOAN HISTORY was blocked from permanent deletion and safely Archived as Inactive (Logged in AuditLog).")

            # Clean up test loan and employee
            Loan.query.filter_by(id=loan_id_pk).delete()
            Employee.query.filter_by(id=loan_emp_id).delete()
            db.session.commit()

        # 7. Test Bulk Delete with mixed employee types
        with app.app_context():
            b1 = Employee(emp_id='BULK_TEST_1', name='Bulk 1 (No Loan)', department='IT', designation='Dev', current_salary=40000.0, status='Active')
            b2 = Employee(emp_id='BULK_TEST_2', name='Bulk 2 (With Loan)', department='IT', designation='Lead', current_salary=80000.0, status='Active')
            db.session.add_all([b1, b2])
            db.session.flush()

            l2 = Loan(
                loan_id='LN-BULK-9998',
                employee_id=b2.id,
                loan_type='Medical Loan',
                loan_amount=20000.0,
                monthly_emi=2000.0,
                emi_start_date=date.today(),
                tenure_months=10,
                loan_status='Active',
                outstanding_balance=20000.0
            )
            db.session.add(l2)
            db.session.commit()
            b1_id, b2_id, l2_id = b1.id, b2.id, l2.id

        bulk_res = client.post('/employees/bulk-delete', data={
            'selected_emp_ids': [str(b1_id), str(b2_id)],
            'bulk_delete_reason': 'Automated bulk test'
        }, follow_redirects=True)
        assert bulk_res.status_code == 200

        with app.app_context():
            b1_check = Employee.query.get(b1_id)
            b2_check = Employee.query.get(b2_id)
            assert b1_check is None, "Bulk 1 (no loans) should be deleted!"
            assert b2_check is not None, "Bulk 2 (with loans) must NOT be deleted!"
            assert b2_check.status == 'Inactive', "Bulk 2 must be archived to Inactive!"
            print("[PASS] Bulk Delete verified: correctly deleted employee without loans, preserved and archived employee with loans.")

            # Clean up test records
            Loan.query.filter_by(id=l2_id).delete()
            Employee.query.filter_by(id=b2_id).delete()
            db.session.commit()

        # 8. Test Excel Import Preview & Commit with CSV
        csv_data = """Employee ID,Full Name,Department,Designation,Current Monthly Salary,Joining Date
IMP_TEST_01,Imported Test Employee One,Operations,Supervisor,38000,2024-05-10
IMP_TEST_02,Imported Test Employee Two,Marketing,Executive,42000,2024-06-15
"""
        import_res = client.post('/employees/import', data={
            'action': 'preview',
            'file': (io.BytesIO(csv_data.encode('utf-8')), 'test_import.csv'),
            'update_existing': '1'
        }, content_type='multipart/form-data')
        assert import_res.status_code == 200
        html = import_res.data.decode('utf-8')
        assert 'Validation Preview: test_import.csv' in html
        assert 'IMP_TEST_01' in html
        assert 'IMP_TEST_02' in html
        print("[PASS] Import Preview verified for CSV file.")

    print("\n==================================================")
    print("ALL TESTS PASSED WITH 100% SUCCESS!")
    print("==================================================")

if __name__ == '__main__':
    run_tests()
