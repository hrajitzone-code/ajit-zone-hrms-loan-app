from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, g, current_app
from models import db, Loan, Employee, EMISchedule, LoanDocument, AuditLog
from routes.auth import login_required, role_required, permission_required
from utils.emi_calculator import calculate_emi_schedule, validate_loan_eligibility
from utils.pdf_builder import generate_emi_schedule_pdf
from datetime import datetime, date
import os

loan_bp = Blueprint('loan', __name__)

def generate_next_loan_id():
    year = datetime.now().year
    count = Loan.query.count() + 1
    return f"LN-{year}-{count:04d}"

@loan_bp.route('/loans')
@login_required
@permission_required('loans', 'view')
def index():
    status_filter = request.args.get('status', '').strip()
    workflow_filter = request.args.get('workflow', '').strip()
    search_q = request.args.get('q', '').strip()

    query = Loan.query.join(Employee)

    # Scope: If user only has 'view_own' and not 'view_all', restrict to their own records
    if not g.user.can_view_all('loans'):
        if g.user.employee_id:
            query = query.filter(Loan.employee_id == g.user.employee_id)
        else:
            query = query.filter(Loan.id == -1)

    if status_filter:
        query = query.filter(Loan.loan_status == status_filter)

    if workflow_filter:
        query = query.filter(Loan.workflow_status == workflow_filter)

    if search_q:
        query = query.filter(
            (Loan.loan_id.ilike(f'%{search_q}%')) |
            (Employee.name.ilike(f'%{search_q}%')) |
            (Employee.emp_id.ilike(f'%{search_q}%'))
        )

    loans = query.order_by(Loan.created_at.desc()).all()
    return render_template('loans/index.html', loans=loans, selected_status=status_filter, selected_workflow=workflow_filter, search_q=search_q)

@loan_bp.route('/loans/create', methods=['GET', 'POST'])
@login_required
@permission_required('loan_applications', 'add')
def create():
    if request.method == 'POST':
        emp_id = request.form.get('employee_id_input', '').strip()
        loan_type = request.form.get('loan_type', '').strip()
        loan_amount = request.form.get('loan_amount', 0.0, type=float)
        monthly_emi = request.form.get('monthly_emi', 0.0, type=float)
        tenure_months = request.form.get('tenure_months', 12, type=int)
        interest_rate = request.form.get('interest_rate', 0.0, type=float)
        start_date_str = request.form.get('emi_start_date', '').strip()
        deduction_day = request.form.get('emi_deduction_day', 5, type=int)
        reason = request.form.get('reason', '').strip()
        remarks = request.form.get('remarks', '').strip()
        declaration = request.form.get('declaration_accepted') == 'on'

        employee = Employee.query.filter_by(emp_id=emp_id).first()
        if not employee:
            flash(f"Employee with ID '{emp_id}' not found.", 'danger')
            return redirect(request.url)

        # Scoping check: If user cannot view all applications, they can only apply for themselves
        if not g.user.can_view_all('loan_applications') and g.user.employee_id:
            if employee.id != g.user.employee_id:
                flash('Access Denied: You may only submit loan applications for your own employee ID.', 'danger')
                return redirect(url_for('loan.index'))

        # Dynamic Eligibility Check against Admin System Settings
        eligibility = validate_loan_eligibility(employee, loan_amount, tenure_months, monthly_emi)
        if not eligibility['is_eligible']:
            for err in eligibility['errors']:
                flash(f"Eligibility Warning: {err}", 'danger')

        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date() if start_date_str else date.today()
        loan_id_code = generate_next_loan_id()

        loan = Loan(
            loan_id=loan_id_code,
            employee_id=employee.id,
            loan_type=loan_type,
            loan_amount=loan_amount,
            monthly_emi=monthly_emi,
            interest_rate=interest_rate,
            emi_start_date=start_date,
            emi_deduction_day=deduction_day,
            tenure_months=tenure_months,
            reason=reason,
            remarks=remarks,
            declaration_accepted=declaration,
            approval_status='Pending',
            loan_status='Pending',
            workflow_status='Submitted',
            total_recovered=0.0,
            outstanding_balance=loan_amount
        )
        db.session.add(loan)
        db.session.flush()

        if 'document' in request.files:
            file = request.files['document']
            if file and file.filename != '':
                file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], f"{loan_id_code}_{file.filename}")
                os.makedirs(current_app.config['UPLOAD_FOLDER'], exist_ok=True)
                file.save(file_path)
                
                doc_record = LoanDocument(
                    loan_id=loan.id,
                    document_name=file.filename,
                    file_path=file_path
                )
                db.session.add(doc_record)

        audit = AuditLog(
            user_id=g.user.id,
            user_name=g.user.full_name,
            role=g.user.role,
            action='CREATE',
            module='Loans',
            record_id=loan_id_code,
            new_value=f"Submitted loan application {loan_id_code} of ₹{loan_amount:,.2f} for {employee.name}",
            reason="Loan Application Submission"
        )
        db.session.add(audit)
        db.session.commit()

        flash(f"Loan Application {loan_id_code} submitted successfully and under review!", 'success')
        return redirect(url_for('loan.view_loan', loan_id=loan.id))

    next_loan_id = generate_next_loan_id()
    employees = Employee.query.filter_by(status='Active').all()

    default_emp_id = ""
    if g.user and g.user.role == 'Employee' and g.user.employee:
        default_emp_id = g.user.employee.emp_id

    return render_template('loans/create.html', next_loan_id=next_loan_id, employees=employees, default_emp_id=default_emp_id, today_date=date.today().strftime('%Y-%m-%d'))

@loan_bp.route('/loans/<int:loan_id>')
@login_required
@permission_required('loans', 'view')
def view_loan(loan_id):
    loan = Loan.query.get_or_404(loan_id)
    employee = loan.employee

    # Scope check: If user only has view_own, ensure they are viewing their own loan
    if not g.user.can_view_all('loans') and not g.user.can_view_all('loan_applications'):
        if g.user.employee_id != employee.id:
            flash('Unauthorized access: You can only view your own loan account.', 'danger')
            return redirect(url_for('dashboard.index'))

    schedules = EMISchedule.query.filter_by(loan_id=loan.id).order_by(EMISchedule.emi_no.asc()).all()
    return render_template('loans/view.html', loan=loan, employee=employee, schedules=schedules)

@loan_bp.route('/loans/<int:loan_id>/approve', methods=['POST'])
@login_required
@permission_required('loan_applications', 'approve')
def approve_loan(loan_id):
    loan = Loan.query.get_or_404(loan_id)
    action = request.form.get('action', 'approve')
    approval_remarks = request.form.get('approval_remarks', '').strip()

    if action == 'approve':
        loan.approval_status = 'Approved'
        loan.loan_status = 'Active'
        loan.workflow_status = 'Approved'
        loan.approval_date = datetime.utcnow()
        loan.approved_by_id = g.user.id
        if approval_remarks:
            loan.remarks = (loan.remarks or '') + f"\n[Approval Note]: {approval_remarks}"

        schedule_res = calculate_emi_schedule(
            loan_amount=loan.loan_amount,
            monthly_emi=loan.monthly_emi,
            start_date=loan.emi_start_date,
            deduction_day=loan.emi_deduction_day,
            tenure_months=loan.tenure_months,
            interest_rate=loan.interest_rate
        )

        loan.tenure_months = schedule_res['actual_tenure']
        loan.tenure_from = schedule_res['tenure_from']
        loan.tenure_to = schedule_res['tenure_to']

        EMISchedule.query.filter_by(loan_id=loan.id).delete()

        new_schedules = []
        for item in schedule_res['schedule']:
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
            new_schedules.append(sch)

        db.session.flush()

        pdf_path = os.path.join(current_app.config['UPLOAD_FOLDER'], 'pdf', f"Schedule_{loan.loan_id}.pdf")
        generate_emi_schedule_pdf(loan, loan.employee, new_schedules, pdf_path)

        audit = AuditLog(
            user_id=g.user.id,
            user_name=g.user.full_name,
            role=g.user.role,
            action='APPROVE',
            module='Loans',
            record_id=loan.loan_id,
            new_value=f"Approved loan {loan.loan_id} for {loan.employee.name}",
            reason=approval_remarks or "Loan Approval"
        )
        db.session.add(audit)
        db.session.commit()

        flash(f"Loan {loan.loan_id} approved and EMI schedule generated successfully!", 'success')
    else:
        loan.approval_status = 'Rejected'
        loan.loan_status = 'Rejected'
        loan.workflow_status = 'Rejected'
        loan.approval_date = datetime.utcnow()
        loan.approved_by_id = g.user.id
        loan.remarks = (loan.remarks or '') + f"\n[Rejection Reason]: {approval_remarks}"

        audit = AuditLog(
            user_id=g.user.id,
            user_name=g.user.full_name,
            role=g.user.role,
            action='REJECT',
            module='Loans',
            record_id=loan.loan_id,
            new_value=f"Rejected loan application {loan.loan_id}",
            reason=approval_remarks or "Loan Rejection"
        )
        db.session.add(audit)
        db.session.commit()

        flash(f"Loan application {loan.loan_id} rejected.", 'info')

    return redirect(url_for('loan.view_loan', loan_id=loan.id))
