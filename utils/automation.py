from datetime import datetime, date
from models import db, Loan, EMISchedule, LoanClosure, NOCRecord, AuditLog, User
from utils.pdf_builder import generate_noc_pdf
import os

def run_daily_loan_automation(system_user_id=1):
    """
    Automates:
    1. Updating EMI schedule statuses (Due, Overdue).
    2. Recalculating dynamic outstanding balances.
    3. Auto-closing loans when outstanding hits 0 and generating NOC certificates.
    """
    today = date.today()
    logs = []

    # 1. Update EMI Schedule Statuses
    overdue_items = EMISchedule.query.filter(
        EMISchedule.due_date <= today,
        EMISchedule.status.in_(['Upcoming', 'Due'])
    ).all()

    for item in overdue_items:
        if item.due_date == today:
            item.status = 'Due'
        elif item.due_date < today:
            item.status = 'Overdue'
        logs.append(f"EMI #{item.id} status updated to {item.status}")

    # 2. Recalculate Active Loans Outstanding & Check Closures
    active_loans = Loan.query.filter(Loan.loan_status.in_(['Active', 'Approved'])).all()

    for loan in active_loans:
        # Sum actual deductions
        total_recovered = sum(s.actual_deduction for s in loan.schedules)
        loan.total_recovered = round(total_recovered, 2)
        
        # Calculate dynamic outstanding
        outstanding = max(0.0, round(loan.loan_amount - total_recovered, 2))
        loan.outstanding_balance = outstanding

        # 3. Check for Loan Closure
        if outstanding == 0.0 and loan.total_recovered >= loan.loan_amount and loan.schedules:
            loan.loan_status = 'Closed'
            
            # Check if closure record exists
            existing_closure = LoanClosure.query.filter_by(loan_id=loan.id).first()
            if not existing_closure:
                closure = LoanClosure(
                    loan_id=loan.id,
                    closure_date=today,
                    total_loan_amount=loan.loan_amount,
                    total_recovered=loan.total_recovered,
                    final_outstanding=0.0,
                    closed_by_id=system_user_id,
                    remarks="Automatic closure triggered by zero outstanding balance."
                )
                db.session.add(closure)
                db.session.flush()

                # Generate NOC Record & PDF
                noc_num = f"NOC-AZ-{today.year}-{loan.id:04d}"
                noc_pdf_filename = f"NOC_{loan.loan_id}.pdf"
                noc_pdf_path = os.path.join('uploads', 'noc', noc_pdf_filename)
                
                generate_noc_pdf(
                    noc_record=type('NocObj', (), {'noc_number': noc_num, 'generated_date': datetime.now()}),
                    loan=loan,
                    employee=loan.employee,
                    output_path=noc_pdf_path
                )

                noc = NOCRecord(
                    noc_number=noc_num,
                    loan_id=loan.id,
                    employee_id=loan.employee_id,
                    pdf_path=noc_pdf_path,
                    generated_by_id=system_user_id
                )
                db.session.add(noc)
                logs.append(f"Loan {loan.loan_id} automatically CLOSED. NOC {noc_num} generated.")

    db.session.commit()
    return logs
