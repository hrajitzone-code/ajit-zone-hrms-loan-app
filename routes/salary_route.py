from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file, g, current_app
from models import db, SalarySheetSync, Employee, Loan, AuditLog
from routes.auth import login_required, role_required, permission_required
from utils.salary_sync import process_salary_sheet_upload, push_deductions_to_payroll
from utils.excel_handler import export_data_to_excel
from datetime import datetime, date
import os

salary_bp = Blueprint('salary', __name__)

@salary_bp.route('/salary-sync', methods=['GET'])
@login_required
@permission_required('salary', 'view_all')
def index():
    month_filter = request.args.get('month', date.today().strftime('%Y-%m')).strip()
    status_filter = request.args.get('status', '').strip()
    search_q = request.args.get('q', '').strip()

    query = SalarySheetSync.query.join(Employee)

    if month_filter:
        query = query.filter(SalarySheetSync.salary_month == month_filter)

    if status_filter:
        query = query.filter(SalarySheetSync.deduction_status == status_filter)

    if search_q:
        query = query.filter(
            (Employee.name.ilike(f'%{search_q}%')) |
            (Employee.emp_id.ilike(f'%{search_q}%')) |
            (SalarySheetSync.sync_batch_id.ilike(f'%{search_q}%'))
        )

    sync_items = query.order_by(SalarySheetSync.synced_at.desc()).all()
    batches = db.session.query(SalarySheetSync.sync_batch_id, SalarySheetSync.synced_at, SalarySheetSync.salary_month).distinct().order_by(SalarySheetSync.synced_at.desc()).limit(10).all()

    return render_template('salary/index.html', items=sync_items, batches=batches, selected_month=month_filter, selected_status=status_filter, search_q=search_q)

@salary_bp.route('/salary-sync/upload', methods=['POST'])
@login_required
@permission_required('salary', 'import')
def upload_salary_sheet():
    if 'file' not in request.files:
        flash('No file selected.', 'danger')
        return redirect(url_for('salary.index'))

    file = request.files['file']
    salary_month = request.form.get('salary_month', date.today().strftime('%Y-%m')).strip()

    if file.filename == '':
        flash('No file selected.', 'danger')
        return redirect(url_for('salary.index'))

    file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], f"Salary_{file.filename}")
    os.makedirs(current_app.config['UPLOAD_FOLDER'], exist_ok=True)
    file.save(file_path)

    res = process_salary_sheet_upload(file_path, g.user.id, salary_month)

    if 'error' in res:
        flash(f"Sync Error: {res['error']}", 'danger')
        return redirect(url_for('salary.index'))

    audit = AuditLog(
        user_id=g.user.id,
        user_name=g.user.full_name,
        role=g.user.role,
        action='SYNC',
        module='SalarySync',
        record_id=res['batch_id'],
        new_value=f"Synced salary sheet for {salary_month}: {res['success']} matched, {res['failed']} failed",
        reason="Salary Sheet Sync Upload"
    )
    db.session.add(audit)
    db.session.commit()

    flash(f"Salary Sheet Synced for {salary_month}! Matched: {res['success']} employees. Batch ID: {res['batch_id']}", 'success')
    return redirect(url_for('salary.index', month=salary_month))

@salary_bp.route('/salary-sync/push', methods=['POST'])
@login_required
@permission_required('salary', 'manage')
def push_deductions():
    salary_month = request.form.get('salary_month', date.today().strftime('%Y-%m')).strip()
    
    pushed_count = push_deductions_to_payroll(salary_month, g.user.id)

    audit = AuditLog(
        user_id=g.user.id,
        user_name=g.user.full_name,
        role=g.user.role,
        action='UPDATE',
        module='SalarySync',
        record_id=salary_month,
        new_value=f"Pushed EMI deductions for {salary_month} to Payroll ({pushed_count} records processed)",
        reason="Push Deduction to Payroll"
    )
    db.session.add(audit)
    db.session.commit()

    flash(f"Pushed {pushed_count} EMI deductions for {salary_month} into Payroll Ledger successfully!", 'success')
    return redirect(url_for('salary.index', month=salary_month))

@salary_bp.route('/salary-sync/export')
@login_required
@permission_required('salary', 'export')
def export_salary_deductions():
    salary_month = request.args.get('month', date.today().strftime('%Y-%m')).strip()

    items = SalarySheetSync.query.filter_by(salary_month=salary_month).all()

    columns = ['Employee ID', 'Employee Name', 'Department', 'Salary Month', 'Loan ID', 'EMI Amount (₹)', 'Deduction Amount (₹)', 'Outstanding Balance (₹)', 'Deduction Status']
    rows = []

    for it in items:
        loan_code = it.loan.loan_id if it.loan else 'N/A'
        rows.append([
            it.employee.emp_id,
            it.employee.name,
            it.employee.department,
            it.salary_month,
            loan_code,
            it.emi_amount,
            it.deduction_amount,
            it.outstanding_balance,
            it.deduction_status
        ])

    excel_stream = export_data_to_excel(columns, rows, sheet_title=f"Salary_Deductions_{salary_month}"[:31])
    filename = f"Salary_EMI_Deductions_{salary_month}.xlsx"

    return send_file(
        excel_stream,
        as_attachment=True,
        download_name=filename,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
