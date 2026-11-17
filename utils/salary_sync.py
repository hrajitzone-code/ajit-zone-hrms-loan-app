import openpyxl
import pandas as pd
from datetime import datetime, date
from models import db, Employee, Loan, EMISchedule, EMIDeduction, SalarySheetSync, AuditLog
import io
import uuid

def process_salary_sheet_upload(file_path, user_id, salary_month=None):
    """
    Imports monthly salary sheet, matches by Employee ID, and updates/creates SalarySheetSync records.
    """
    if not salary_month:
        salary_month = date.today().strftime('%Y-%m')

    wb = openpyxl.load_workbook(file_path, data_only=True)
    ws = wb.active

    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return {'error': 'Uploaded salary file is empty'}

    headers = [str(c).strip().lower() if c else '' for c in rows[0]]
    
    emp_col = -1
    for idx, h in enumerate(headers):
        if 'emp' in h or 'employee id' in h or 'id' == h:
            emp_col = idx
            break

    if emp_col == -1:
        emp_col = 0 # Default first column

    batch_id = f"SYNC-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:4].upper()}"
    processed = 0
    success = 0
    failed = 0
    errors = []

    for row_idx, r in enumerate(rows[1:], start=2):
        if not any(r):
            continue
        processed += 1
        emp_code = str(r[emp_col]).strip() if r[emp_col] else ''

        emp = Employee.query.filter_by(emp_id=emp_code).first()
        if not emp:
            failed += 1
            errors.append(f"Row {row_idx}: Employee ID '{emp_code}' not found in Master")
            continue

        # Find active loan for employee
        active_loan = Loan.query.filter_by(employee_id=emp.id, loan_status='Active').first()
        
        emi_amt = active_loan.monthly_emi if active_loan else 0.0
        out_bal = active_loan.outstanding_balance if active_loan else 0.0
        loan_id_pk = active_loan.id if active_loan else None

        sync_rec = SalarySheetSync(
            sync_batch_id=batch_id,
            salary_month=salary_month,
            employee_id=emp.id,
            loan_id=loan_id_pk,
            emi_amount=emi_amt,
            deduction_amount=emi_amt if active_loan else 0.0,
            outstanding_balance=out_bal,
            deduction_status='Pending' if active_loan else 'Processed',
            sync_source='Excel_Import',
            synced_by_id=user_id
        )
        db.session.add(sync_rec)
        success += 1

    db.session.commit()

    return {
        'batch_id': batch_id,
        'processed': processed,
        'success': success,
        'failed': failed,
        'errors': errors
    }

def push_deductions_to_payroll(salary_month, user_id):
    """
    Executes deduction push for the given month: updates EMISchedule and EMIDeduction records,
    recalculates outstanding balances, and triggers auto-closure if balance is zero.
    """
    sync_items = SalarySheetSync.query.filter_by(salary_month=salary_month, deduction_status='Pending').all()
    updated_count = 0

    for item in sync_items:
        if not item.loan_id:
            item.deduction_status = 'Processed'
            continue

        loan = Loan.query.get(item.loan_id)
        if not loan or loan.loan_status != 'Active':
            item.deduction_status = 'Processed'
            continue

        # Find current month EMI schedule
        schedule_item = EMISchedule.query.filter(
            EMISchedule.loan_id == loan.id,
            db.func.strftime('%Y-%m', EMISchedule.due_date) == salary_month
        ).first()

        if not schedule_item:
            # Fallback to earliest upcoming schedule
            schedule_item = EMISchedule.query.filter(
                EMISchedule.loan_id == loan.id,
                EMISchedule.status.in_(['Upcoming', 'Due', 'Pending'])
            ).order_by(EMISchedule.due_date.asc()).first()

        if schedule_item:
            schedule_item.actual_deduction = round(item.deduction_amount, 2)
            schedule_item.actual_deduction_date = date.today()

            if item.deduction_amount >= schedule_item.scheduled_emi:
                schedule_item.status = 'Deducted'
                item.deduction_status = 'Processed'
            elif item.deduction_amount > 0:
                schedule_item.status = 'Partial'
                item.deduction_status = 'Partially Deducted'
            else:
                schedule_item.status = 'Pending'
                item.deduction_status = 'Failed'

            deduction_record = EMIDeduction(
                loan_id=loan.id,
                emi_schedule_id=schedule_item.id,
                deduction_date=date.today(),
                amount_deducted=item.deduction_amount,
                payment_mode='Payroll Deduction',
                transaction_ref=f"PAYROLL-{salary_month}",
                deduction_status=item.deduction_status,
                recorded_by_id=user_id,
                remarks=f"Auto-synced from Salary Sheet Batch {item.sync_batch_id}"
            )
            db.session.add(deduction_record)

            total_recovered = sum(s.actual_deduction for s in loan.schedules)
            loan.total_recovered = round(total_recovered, 2)
            loan.outstanding_balance = max(0.0, round(loan.loan_amount - total_recovered, 2))
            
            if loan.outstanding_balance == 0.0:
                loan.loan_status = 'Closed'
                loan.workflow_status = 'Closed'

            updated_count += 1

    db.session.commit()
    return updated_count
