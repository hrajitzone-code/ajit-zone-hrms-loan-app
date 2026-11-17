from flask import Blueprint, render_template, request, send_file, flash, redirect, url_for, g
from models import db, Loan, Employee, EMISchedule, EMIDeduction, EMIAdjustment, LoanClosure
from routes.auth import login_required, permission_required
from utils.excel_handler import export_data_to_excel
from datetime import datetime, date

reports_bp = Blueprint('reports', __name__)

REPORT_TYPES = {
    'employee_loans': 'Employee-wise Loan Report',
    'dept_loans': 'Department-wise Loan Report',
    'active_loans': 'Active Loan Report',
    'closed_loans': 'Closed Loan Report',
    'monthly_emi': 'Monthly EMI Deduction Report',
    'pending_emi': 'Pending EMI Report',
    'overdue_emi': 'Overdue EMI Report',
    'outstanding': 'Outstanding Balance Report',
    'deduction_ledger': 'Deduction Ledger Report',
    'adjustments': 'Adjustment History Report',
    'closures': 'Loan Closure & NOC Report'
}

@reports_bp.route('/reports')
@login_required
@permission_required('reports', 'view')
def index():
    report_type = request.args.get('type', 'active_loans')
    dept_filter = request.args.get('department', '').strip()
    status_filter = request.args.get('status', '').strip()
    start_date = request.args.get('start_date', '').strip()
    end_date = request.args.get('end_date', '').strip()
    export_fmt = request.args.get('export', '').strip()

    if export_fmt == 'excel':
        if not (g.user.is_superadmin() or g.user.has_permission('reports', 'export')):
            flash('Access Denied: You do not have permission to export reports to Excel.', 'danger')
            return redirect(url_for('reports.index', type=report_type))

    emp_id_filter = None
    if not g.user.can_view_all('reports'):
        emp_id_filter = g.user.employee_id or -1

    columns, rows = generate_report_data(report_type, dept_filter, status_filter, start_date, end_date, emp_id_filter=emp_id_filter)

    if export_fmt == 'excel':
        excel_stream = export_data_to_excel(columns, rows, sheet_title=REPORT_TYPES.get(report_type, 'Report')[:31])
        filename = f"{report_type}_{date.today().strftime('%Y%m%d')}.xlsx"
        return send_file(
            excel_stream,
            as_attachment=True,
            download_name=filename,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )

    departments = db.session.query(Employee.department).distinct().all()
    departments = [d[0] for d in departments if d[0]]

    return render_template(
        'reports/index.html',
        report_types=REPORT_TYPES,
        current_report=report_type,
        columns=columns,
        rows=rows,
        departments=departments,
        selected_dept=dept_filter,
        selected_status=status_filter,
        start_date=start_date,
        end_date=end_date
    )

def generate_report_data(report_type, dept, status, start_d, end_d, emp_id_filter=None):
    if report_type == 'employee_loans':
        columns = ['Employee ID', 'Employee Name', 'Department', 'Designation', 'Total Loans', 'Total Amount (₹)', 'Recovered (₹)', 'Outstanding (₹)']
        query = db.session.query(
            Employee.emp_id, Employee.name, Employee.department, Employee.designation,
            db.func.count(Loan.id), db.func.sum(Loan.loan_amount),
            db.func.sum(Loan.total_recovered), db.func.sum(Loan.outstanding_balance)
        ).join(Loan, Loan.employee_id == Employee.id)
        if dept: query = query.filter(Employee.department == dept)
        if emp_id_filter is not None: query = query.filter(Employee.id == emp_id_filter)
        data = query.group_by(Employee.id).all()
        rows = [[d[0], d[1], d[2], d[3], d[4], round(d[5] or 0, 2), round(d[6] or 0, 2), round(d[7] or 0, 2)] for d in data]

    elif report_type == 'dept_loans':
        columns = ['Department', 'Active Employees', 'Total Loans', 'Total Loan Amount (₹)', 'Total Recovered (₹)', 'Total Outstanding (₹)']
        query = db.session.query(
            Employee.department,
            db.func.count(db.distinct(Employee.id)),
            db.func.count(Loan.id),
            db.func.sum(Loan.loan_amount),
            db.func.sum(Loan.total_recovered),
            db.func.sum(Loan.outstanding_balance)
        ).outerjoin(Loan, Loan.employee_id == Employee.id)
        if dept: query = query.filter(Employee.department == dept)
        if emp_id_filter is not None: query = query.filter(Employee.id == emp_id_filter)
        data = query.group_by(Employee.department).all()
        rows = [[d[0], d[1], d[2], round(d[3] or 0, 2), round(d[4] or 0, 2), round(d[5] or 0, 2)] for d in data]

    elif report_type == 'active_loans':
        columns = ['Loan ID', 'Emp ID', 'Employee Name', 'Department', 'Loan Type', 'Loan Amount (₹)', 'Monthly EMI (₹)', 'Recovered (₹)', 'Outstanding (₹)', 'Tenure From', 'Tenure To']
        query = Loan.query.join(Employee).filter(Loan.loan_status == 'Active')
        if dept: query = query.filter(Employee.department == dept)
        if emp_id_filter is not None: query = query.filter(Loan.employee_id == emp_id_filter)
        loans = query.all()
        rows = [[
            l.loan_id, l.employee.emp_id, l.employee.name, l.employee.department,
            l.loan_type, l.loan_amount, l.monthly_emi, l.total_recovered, l.outstanding_balance,
            l.tenure_from.strftime('%d-%b-%Y') if l.tenure_from else '',
            l.tenure_to.strftime('%d-%b-%Y') if l.tenure_to else ''
        ] for l in loans]

    elif report_type == 'closed_loans':
        columns = ['Loan ID', 'Emp ID', 'Employee Name', 'Department', 'Loan Amount (₹)', 'Total Recovered (₹)', 'Closure Date', 'NOC Generated']
        query = Loan.query.join(Employee).filter(Loan.loan_status == 'Closed')
        if dept: query = query.filter(Employee.department == dept)
        loans = query.all()
        rows = [[
            l.loan_id, l.employee.emp_id, l.employee.name, l.employee.department,
            l.loan_amount, l.total_recovered,
            l.closure.closure_date.strftime('%d-%b-%Y') if l.closure else '',
            'Yes' if l.closure else 'No'
        ] for l in loans]

    elif report_type == 'monthly_emi':
        columns = ['EMI ID', 'Loan ID', 'Emp ID', 'Employee Name', 'Due Date', 'Scheduled EMI (₹)', 'Deducted (₹)', 'Deduction Date', 'Status']
        query = EMISchedule.query.join(Loan).join(Employee)
        if dept: query = query.filter(Employee.department == dept)
        if status: query = query.filter(EMISchedule.status == status)
        schedules = query.order_by(EMISchedule.due_date.asc()).all()
        rows = [[
            s.id, s.loan.loan_id, s.loan.employee.emp_id, s.loan.employee.name,
            s.due_date.strftime('%d-%b-%Y') if s.due_date else '',
            s.scheduled_emi, s.actual_deduction,
            s.actual_deduction_date.strftime('%d-%b-%Y') if s.actual_deduction_date else '',
            s.status
        ] for s in schedules]

    elif report_type == 'pending_emi':
        columns = ['Loan ID', 'Emp ID', 'Employee Name', 'Department', 'EMI No', 'Due Date', 'Scheduled EMI (₹)', 'Actual Deducted (₹)', 'Pending Balance (₹)', 'Status']
        query = EMISchedule.query.join(Loan).join(Employee).filter(EMISchedule.status.in_(['Upcoming', 'Due', 'Partial', 'Pending']))
        if dept: query = query.filter(Employee.department == dept)
        schedules = query.all()
        rows = [[
            s.loan.loan_id, s.loan.employee.emp_id, s.loan.employee.name, s.loan.employee.department,
            s.emi_no, s.due_date.strftime('%d-%b-%Y') if s.due_date else '',
            s.scheduled_emi, s.actual_deduction, round(s.scheduled_emi - s.actual_deduction, 2), s.status
        ] for s in schedules]

    elif report_type == 'overdue_emi':
        columns = ['Loan ID', 'Emp ID', 'Employee Name', 'Department', 'EMI No', 'Due Date', 'Scheduled EMI (₹)', 'Overdue Balance (₹)']
        query = EMISchedule.query.join(Loan).join(Employee).filter(EMISchedule.status == 'Overdue')
        if dept: query = query.filter(Employee.department == dept)
        schedules = query.all()
        rows = [[
            s.loan.loan_id, s.loan.employee.emp_id, s.loan.employee.name, s.loan.employee.department,
            s.emi_no, s.due_date.strftime('%d-%b-%Y') if s.due_date else '',
            s.scheduled_emi, round(s.scheduled_emi - s.actual_deduction, 2)
        ] for s in schedules]

    elif report_type == 'outstanding':
        columns = ['Emp ID', 'Employee Name', 'Department', 'Loan ID', 'Loan Type', 'Loan Amount (₹)', 'Total Recovered (₹)', 'Outstanding Balance (₹)']
        query = Loan.query.join(Employee).filter(Loan.loan_status == 'Active')
        if dept: query = query.filter(Employee.department == dept)
        loans = query.all()
        rows = [[
            l.employee.emp_id, l.employee.name, l.employee.department, l.loan_id, l.loan_type,
            l.loan_amount, l.total_recovered, l.outstanding_balance
        ] for l in loans]

    elif report_type == 'deduction_ledger':
        columns = ['Deduction ID', 'Loan ID', 'Emp ID', 'Employee Name', 'Deduction Date', 'Amount Deducted (₹)', 'Payment Mode', 'Transaction Ref']
        query = EMIDeduction.query.join(Loan).join(Employee)
        if dept: query = query.filter(Employee.department == dept)
        deductions = query.order_by(EMIDeduction.deduction_date.desc()).all()
        rows = [[
            d.id, d.loan.loan_id, d.loan.employee.emp_id, d.loan.employee.name,
            d.deduction_date.strftime('%d-%b-%Y') if d.deduction_date else '',
            d.amount_deducted, d.payment_mode, d.transaction_ref or ''
        ] for d in deductions]

    elif report_type == 'adjustments':
        columns = ['Adjustment ID', 'Loan ID', 'Emp ID', 'Employee Name', 'Adjustment Type', 'Amount (₹)', 'Reason', 'Approval Status']
        query = EMIAdjustment.query.join(Loan).join(Employee)
        if dept: query = query.filter(Employee.department == dept)
        adjs = query.order_by(EMIAdjustment.created_at.desc()).all()
        rows = [[
            a.id, a.loan.loan_id, a.loan.employee.emp_id, a.loan.employee.name,
            a.adjustment_type, a.amount, a.reason, a.approval_status
        ] for a in adjs]

    else: # closures
        columns = ['Closure ID', 'Loan ID', 'Emp ID', 'Employee Name', 'Loan Amount (₹)', 'Recovered (₹)', 'Closure Date', 'NOC Number']
        closures = LoanClosure.query.join(Loan).join(Employee).all()
        rows = [[
            c.id, c.loan.loan_id, c.loan.employee.emp_id, c.loan.employee.name,
            c.total_loan_amount, c.total_recovered,
            c.closure_date.strftime('%d-%b-%Y') if c.closure_date else '',
            c.loan.employee.loans[0].loan_id if c.loan.employee.loans else ''
        ] for c in closures]

    return columns, rows
