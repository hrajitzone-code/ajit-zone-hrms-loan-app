import sys
import os

# Ensure app path in pythonpath
sys.path.insert(0, os.path.abspath('c:/Users/Sakshi/OneDrive/Documents/My Projects/ajit_zone_loan_app'))

from app import create_app
from models import db, Employee, Loan, EMISchedule, EMIDeduction, EMIAdjustment, LoanClosure, NOCRecord, AuditLog, User
from utils.excel_handler import parse_excel_employee_file
from utils.emi_calculator import calculate_emi_schedule
from utils.pdf_builder import generate_emi_schedule_pdf, generate_noc_pdf
from utils.automation import run_daily_loan_automation
from datetime import datetime, date

app = create_app()

def test_full_application_workflow():
    with app.app_context():
        print("=== 1. TESTING EXCEL IMPORT ===")
        excel_file = os.path.abspath('c:/Users/Sakshi/OneDrive/Documents/My Projects/HR_Dataset_5000.xlsx')
        res = parse_excel_employee_file(excel_file)
        assert 'error' not in res, f"Excel parse error: {res.get('error')}"
        print(f"[SUCCESS] Parsed {res['total_rows']} employee records from HR_Dataset_5000.xlsx")

        # Insert sample top 50 employees into DB for testing
        imported_count = 0
        for r in res['parsed_rows'][:50]:
            if not Employee.query.filter_by(emp_id=r['emp_id']).first():
                emp = Employee(
                    emp_id=r['emp_id'],
                    name=r['name'],
                    department=r['department'],
                    designation=r['designation'],
                    current_salary=r['current_salary'],
                    email=r['email'],
                    phone=r['phone'],
                    pan_number=r['pan_number'],
                    bank_name=r['bank_name'],
                    bank_account_no=r['bank_account_no'],
                    ifsc_code=r['ifsc_code']
                )
                db.session.add(emp)
                imported_count += 1
        db.session.commit()
        print(f"[SUCCESS] Committed {imported_count} employees to database")

        target_emp = Employee.query.first()
        print(f"Target Employee: {target_emp.name} ({target_emp.emp_id}), Dept: {target_emp.department}, Salary: INR {target_emp.current_salary}")

        print("\n=== 2. TESTING LOAN APPLICATION CREATION & APPROVAL ===")
        loan_amount = 60000.0
        monthly_emi = 5000.0
        start_date = date(2026, 10, 5)

        test_wf_loan_id = f"LN-WF-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        loan = Loan(
            loan_id=test_wf_loan_id,
            employee_id=target_emp.id,
            loan_type="Personal Loan",
            loan_amount=loan_amount,
            monthly_emi=monthly_emi,
            emi_start_date=start_date,
            emi_deduction_day=5,
            tenure_months=12,
            reason="Emergency personal advance",
            approval_status="Approved",
            loan_status="Active",
            approval_date=datetime.now(),
            total_recovered=0.0,
            outstanding_balance=loan_amount
        )
        db.session.add(loan)
        db.session.flush()

        # Calculate EMI Schedule
        sched_res = calculate_emi_schedule(loan_amount, monthly_emi, start_date, deduction_day=5, tenure_months=12)
        loan.tenure_from = sched_res['tenure_from']
        loan.tenure_to = sched_res['tenure_to']

        for item in sched_res['schedule']:
            sch = EMISchedule(
                loan_id=loan.id,
                emi_no=item['emi_no'],
                due_date=item['due_date'],
                scheduled_emi=item['scheduled_emi'],
                actual_deduction=0.0,
                outstanding_after=item['outstanding_after'],
                status='Upcoming'
            )
            db.session.add(sch)
        db.session.commit()

        schedules = EMISchedule.query.filter_by(loan_id=loan.id).order_by(EMISchedule.emi_no.asc()).all()
        assert len(schedules) == 12, f"Expected 12 schedules, got {len(schedules)}"
        print(f"[SUCCESS] EMI Schedule generated: 12 installments from {loan.tenure_from} to {loan.tenure_to}")
        print(f"First EMI due: {schedules[0].due_date}, Final EMI amount: INR {schedules[-1].scheduled_emi}")

        print("\n=== 3. TESTING BRANDED REPORTLAB PDF GENERATION ===")
        pdf_out = os.path.join(app.config['UPLOAD_FOLDER'], 'pdf', f"Schedule_{loan.loan_id}.pdf")
        generate_emi_schedule_pdf(loan, target_emp, schedules, pdf_out)
        assert os.path.exists(pdf_out), "PDF file was not created!"
        print(f"[SUCCESS] EMI Schedule PDF created at: {pdf_out}")

        print("\n=== 4. TESTING PARTIAL DEDUCTION & MISSED EMI ADJUSTMENT ===")
        # Deduct installment 1 in full (5,000)
        sch1 = schedules[0]
        sch1.actual_deduction = 5000.0
        sch1.actual_deduction_date = sch1.due_date
        sch1.status = 'Deducted'

        # Deduct installment 2 partially (Scheduled 5,000, Actual 3,000 -> Partial status & 2,000 pending)
        sch2 = schedules[1]
        sch2.actual_deduction = 3000.0
        sch2.actual_deduction_date = sch2.due_date
        sch2.status = 'Partial'

        db.session.commit()

        # Recalculate loan recovered and outstanding
        run_daily_loan_automation(system_user_id=1)
        loan = Loan.query.get(loan.id)

        print(f"Total Recovered: INR {loan.total_recovered} (Expected: 8000)")
        print(f"Outstanding Balance: INR {loan.outstanding_balance} (Expected: 52000)")
        assert loan.total_recovered == 8000.0, f"Expected total recovered 8000, got {loan.total_recovered}"
        assert loan.outstanding_balance == 52000.0, f"Expected outstanding 52000, got {loan.outstanding_balance}"
        print("[SUCCESS] Partial deduction & dynamic outstanding balance verified cleanly!")

        print("\n=== 5. TESTING FULL LOAN PAYOFF, AUTO-CLOSURE & NOC GENERATION ===")
        # Pay off remaining schedules to trigger auto-closure
        for s in schedules[2:]:
            s.actual_deduction = s.scheduled_emi
            s.actual_deduction_date = s.due_date
            s.status = 'Deducted'
        sch2.actual_deduction = 5000.0 # Pay remaining 2000 for sch2 as well
        sch2.status = 'Deducted'

        db.session.commit()

        run_daily_loan_automation(system_user_id=1)
        loan = Loan.query.get(loan.id)

        print(f"Post-payoff Loan Status: {loan.loan_status}")
        print(f"Post-payoff Total Recovered: INR {loan.total_recovered}")
        print(f"Post-payoff Outstanding: INR {loan.outstanding_balance}")

        assert loan.loan_status == 'Closed', f"Expected loan_status Closed, got {loan.loan_status}"
        assert loan.outstanding_balance == 0.0, f"Expected outstanding 0, got {loan.outstanding_balance}"

        noc_rec = NOCRecord.query.filter_by(loan_id=loan.id).first()
        assert noc_rec is not None, "NOC Record was not created!"
        assert os.path.exists(noc_rec.pdf_path), "NOC PDF file was not generated!"

        print(f"[SUCCESS] Loan automatically CLOSED! NOC Ref: {noc_rec.noc_number}, PDF Path: {noc_rec.pdf_path}")
        print("\n=== ALL WORKFLOW TESTS PASSED PERFECTLY! ===")

if __name__ == '__main__':
    test_full_application_workflow()
