from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, g, current_app, send_file
from models import db, Employee, Loan, ImportLog, AuditLog, User
from routes.auth import login_required, role_required, permission_required
from utils.excel_handler import parse_excel_employee_file, generate_blank_employee_template, export_employees_to_file
from utils.google_sheets_sync import trigger_auto_sync_if_enabled
from datetime import datetime, date
import os
import json

employee_bp = Blueprint('employee', __name__)

@employee_bp.route('/employees')
@login_required
@permission_required('employees', 'view')
def index():
    search_q = request.args.get('q', '').strip()
    dept_filter = request.args.get('department', '').strip()
    status_filter = request.args.get('status', '').strip()
    page = request.args.get('page', 1, type=int)

    query = Employee.query

    # Restrict to own record if user only has 'view_own' and not 'view_all'
    if not g.user.can_view_all('employees'):
        if g.user.employee_id:
            query = query.filter(Employee.id == g.user.employee_id)
        else:
            query = query.filter(Employee.id == -1)

    if search_q:
        query = query.filter(
            (Employee.name.ilike(f'%{search_q}%')) |
            (Employee.emp_id.ilike(f'%{search_q}%')) |
            (Employee.email.ilike(f'%{search_q}%'))
        )

    if dept_filter:
        query = query.filter(Employee.department == dept_filter)

    if status_filter:
        query = query.filter(Employee.status == status_filter)

    pagination = query.order_by(Employee.created_at.desc()).paginate(page=page, per_page=15, error_out=False)
    employees = pagination.items

    departments = db.session.query(Employee.department).distinct().all()
    departments = [d[0] for d in departments if d[0]]

    # Compute loan count for each employee to display loan protection indicator in UI
    emp_ids_on_page = [e.id for e in employees]
    emp_loans_count = {}
    if emp_ids_on_page:
        loan_records = db.session.query(Loan.employee_id, db.func.count(Loan.id)).filter(
            Loan.employee_id.in_(emp_ids_on_page)
        ).group_by(Loan.employee_id).all()
        for emp_pk, count in loan_records:
            emp_loans_count[emp_pk] = count

    return render_template(
        'employees/index.html',
        employees=employees,
        pagination=pagination,
        departments=departments,
        search_q=search_q,
        selected_dept=dept_filter,
        selected_status=status_filter,
        emp_loans_count=emp_loans_count
    )

@employee_bp.route('/employees/add', methods=['POST'])
@login_required
@permission_required('employees', 'add')
def add_employee():
    emp_id = request.form.get('emp_id', '').strip()
    name = request.form.get('name', '').strip()
    department = request.form.get('department', '').strip()
    designation = request.form.get('designation', '').strip()
    salary = request.form.get('current_salary', 0.0, type=float)
    joining_date_str = request.form.get('joining_date', '').strip()

    if not emp_id or not name:
        flash('Employee ID and Name are required fields.', 'danger')
        return redirect(url_for('employee.index'))

    existing = Employee.query.filter_by(emp_id=emp_id).first()
    if existing:
        flash(f'Employee ID {emp_id} already exists!', 'danger')
        return redirect(url_for('employee.index'))

    j_date = datetime.strptime(joining_date_str, '%Y-%m-%d').date() if joining_date_str else date.today()

    emp = Employee(
        emp_id=emp_id,
        name=name,
        department=department or 'General',
        designation=designation or 'Staff',
        current_salary=salary,
        joining_date=j_date,
        hiring_date=j_date,
        email=request.form.get('email', '').strip(),
        phone=request.form.get('phone', '').strip(),
        pan_number=request.form.get('pan_number', '').strip(),
        aadhar_number=request.form.get('aadhar_number', '').strip(),
        bank_name=request.form.get('bank_name', '').strip(),
        bank_account_no=request.form.get('bank_account_no', '').strip(),
        ifsc_code=request.form.get('ifsc_code', '').strip()
    )
    db.session.add(emp)

    audit = AuditLog(
        user_id=g.user.id,
        user_name=g.user.full_name,
        role=g.user.role,
        action='CREATE',
        module='Employees',
        record_id=emp_id,
        new_value=f"Created employee {name} ({emp_id})",
        reason="Manual Employee Creation",
        ip_address=request.remote_addr
    )
    db.session.add(audit)
    db.session.commit()
    trigger_auto_sync_if_enabled()

    flash(f'Employee {name} ({emp_id}) added successfully!', 'success')
    return redirect(url_for('employee.index'))

@employee_bp.route('/employees/<int:emp_id_pk>/edit', methods=['POST'])
@login_required
@permission_required('employees', 'edit')
def edit_employee(emp_id_pk):
    emp = Employee.query.get_or_404(emp_id_pk)
    
    old_val = f"Name: {emp.name}, Salary: ₹{emp.current_salary}, Dept: {emp.department}, Status: {emp.status}"

    emp.name = request.form.get('name', '').strip() or emp.name
    emp.department = request.form.get('department', '').strip() or emp.department
    emp.designation = request.form.get('designation', '').strip() or emp.designation
    emp.current_salary = request.form.get('current_salary', emp.current_salary, type=float)
    emp.email = request.form.get('email', '').strip()
    emp.phone = request.form.get('phone', '').strip()
    emp.pan_number = request.form.get('pan_number', '').strip()
    emp.aadhar_number = request.form.get('aadhar_number', '').strip()
    emp.bank_name = request.form.get('bank_name', '').strip()
    emp.bank_account_no = request.form.get('bank_account_no', '').strip()
    emp.ifsc_code = request.form.get('ifsc_code', '').strip()

    joining_date_str = request.form.get('joining_date', '').strip()
    if joining_date_str:
        emp.joining_date = datetime.strptime(joining_date_str, '%Y-%m-%d').date()

    emp.updated_at = datetime.utcnow()

    new_val = f"Name: {emp.name}, Salary: ₹{emp.current_salary}, Dept: {emp.department}, Status: {emp.status}"

    audit = AuditLog(
        user_id=g.user.id,
        user_name=g.user.full_name,
        role=g.user.role,
        action='UPDATE',
        module='Employees',
        record_id=emp.emp_id,
        old_value=old_val,
        new_value=new_val,
        reason="Admin/HR Employee Details Edit",
        ip_address=request.remote_addr
    )
    db.session.add(audit)
    db.session.commit()

    flash(f"Employee details for {emp.name} ({emp.emp_id}) updated successfully!", 'success')
    return redirect(request.referrer or url_for('employee.index'))

@employee_bp.route('/employees/<int:emp_id_pk>/toggle-status', methods=['POST'])
@login_required
@permission_required('employees', 'edit')
def toggle_status(emp_id_pk):
    emp = Employee.query.get_or_404(emp_id_pk)
    old_status = emp.status
    emp.status = 'Inactive' if emp.status == 'Active' else 'Active'
    emp.updated_at = datetime.utcnow()

    audit = AuditLog(
        user_id=g.user.id,
        user_name=g.user.full_name,
        role=g.user.role,
        action='UPDATE',
        module='Employees',
        record_id=emp.emp_id,
        old_value=f"Status: {old_status}",
        new_value=f"Status: {emp.status}",
        reason=f"Employee Status Toggled to {emp.status}",
        ip_address=request.remote_addr
    )
    db.session.add(audit)
    db.session.commit()

    flash(f"Status for {emp.name} ({emp.emp_id}) changed to {emp.status}!", 'info')
    return redirect(request.referrer or url_for('employee.index'))

@employee_bp.route('/employees/<int:emp_id_pk>/delete', methods=['POST'])
@login_required
@permission_required('employees', 'delete')
def delete_employee(emp_id_pk):
    """
    Selective Single Employee Delete with Loan History Protection.
    If the employee has any loan/EMI history, permanent deletion is BLOCKED,
    and the employee is safely Archived/Deactivated instead.
    """
    emp = Employee.query.get_or_404(emp_id_pk)
    delete_reason = request.form.get('delete_reason', '').strip() or 'Selective employee deletion'

    # Check for active or past loan records
    loans = Loan.query.filter_by(employee_id=emp.id).all()
    if loans:
        # CRITICAL SAFETY: Prevent permanent deletion to preserve financial audit trail
        emp.status = 'Inactive'
        emp.updated_at = datetime.utcnow()

        audit = AuditLog(
            user_id=g.user.id,
            user_name=g.user.full_name,
            role=g.user.role,
            action='ARCHIVE',
            module='Employees',
            record_id=emp.emp_id,
            old_value=f"Status: {emp.status}, Existing Loans: {len(loans)}",
            new_value="Status: Inactive (Archived)",
            reason=f"Permanent deletion blocked because employee has {len(loans)} loan/EMI records. Employee has been Archived/Deactivated instead. User reason: {delete_reason}",
            ip_address=request.remote_addr
        )
        db.session.add(audit)
        db.session.commit()

        flash(
            f"Cannot permanently delete employee {emp.name} ({emp.emp_id}) because they have {len(loans)} active/past loan records. To protect financial audit integrity, the employee has been safely Archived / Deactivated instead.",
            'warning'
        )
        return redirect(request.referrer or url_for('employee.index'))

    # If NO loan history exists, safe to delete permanently
    emp_id_code = emp.emp_id
    emp_name = emp.name
    old_details = f"Name: {emp.name}, Dept: {emp.department}, Desig: {emp.designation}, Salary: ₹{emp.current_salary:,.2f}"

    # Decouple linked user account if any
    linked_user = User.query.filter_by(employee_id=emp.id).first()
    if linked_user:
        linked_user.employee_id = None
        if linked_user.role == 'Employee':
            linked_user.is_active = False

    db.session.delete(emp)

    audit = AuditLog(
        user_id=g.user.id,
        user_name=g.user.full_name,
        role=g.user.role,
        action='DELETE',
        module='Employees',
        record_id=emp_id_code,
        old_value=old_details,
        new_value="PERMANENTLY DELETED",
        reason=delete_reason,
        ip_address=request.remote_addr
    )
    db.session.add(audit)
    db.session.commit()
    trigger_auto_sync_if_enabled()

    flash(f"Employee {emp_name} ({emp_id_code}) has been permanently deleted.", 'success')
    return redirect(request.referrer or url_for('employee.index'))

@employee_bp.route('/employees/bulk-delete', methods=['POST'])
@login_required
@permission_required('employees', 'delete')
def bulk_delete():
    """
    Selective Bulk Employee Delete with Loan History Protection.
    Requires selecting specific employee checkboxes. Never allows Delete All.
    """
    selected_ids = request.form.getlist('selected_emp_ids')
    delete_reason = request.form.get('bulk_delete_reason', '').strip() or 'Selective bulk employee deletion'

    if not selected_ids:
        flash("No employees were selected for deletion. Please select at least one employee.", "warning")
        return redirect(request.referrer or url_for('employee.index'))

    deleted_count = 0
    archived_count = 0

    for emp_id_str in selected_ids:
        try:
            emp_pk = int(emp_id_str)
        except ValueError:
            continue

        emp = Employee.query.get(emp_pk)
        if not emp:
            continue

        loans = Loan.query.filter_by(employee_id=emp.id).all()
        if loans:
            # Archive/Deactivate due to loan history
            emp.status = 'Inactive'
            emp.updated_at = datetime.utcnow()
            archived_count += 1

            audit = AuditLog(
                user_id=g.user.id,
                user_name=g.user.full_name,
                role=g.user.role,
                action='ARCHIVE',
                module='Employees',
                record_id=emp.emp_id,
                old_value=f"Status: {emp.status}, Existing Loans: {len(loans)}",
                new_value="Status: Inactive (Archived)",
                reason=f"Bulk delete: Permanent delete blocked due to {len(loans)} existing loans. Employee Archived instead. User reason: {delete_reason}",
                ip_address=request.remote_addr
            )
            db.session.add(audit)
        else:
            # Permanent delete
            emp_id_code = emp.emp_id
            emp_name = emp.name
            old_details = f"Name: {emp.name}, Dept: {emp.department}, Salary: ₹{emp.current_salary:,.2f}"

            linked_user = User.query.filter_by(employee_id=emp.id).first()
            if linked_user:
                linked_user.employee_id = None
                if linked_user.role == 'Employee':
                    linked_user.is_active = False

            db.session.delete(emp)
            deleted_count += 1

            audit = AuditLog(
                user_id=g.user.id,
                user_name=g.user.full_name,
                role=g.user.role,
                action='DELETE',
                module='Employees',
                record_id=emp_id_code,
                old_value=old_details,
                new_value="PERMANENTLY DELETED",
                reason=f"Bulk delete: {delete_reason}",
                ip_address=request.remote_addr
            )
            db.session.add(audit)

    db.session.commit()
    trigger_auto_sync_if_enabled()

    msg = f"Bulk Action Completed: {deleted_count} employee(s) permanently deleted."
    if archived_count > 0:
        msg += f" {archived_count} employee(s) had loan/EMI history and were safely Archived / Deactivated instead to protect financial records."
    flash(msg, "info")

    return redirect(request.referrer or url_for('employee.index'))

@employee_bp.route('/employees/<int:emp_id_pk>/detail')
@login_required
@permission_required('employees', 'view')
def detail(emp_id_pk):
    employee = Employee.query.get_or_404(emp_id_pk)
    
    # Scope check: If user only has view_own (and not view_all), verify they are viewing their OWN profile!
    if not g.user.can_view_all('employees'):
        if not g.user.has_permission('employees', 'view_own') or g.user.employee_id != employee.id:
            flash('Unauthorized access: You can only view your own employee profile.', 'danger')
            return redirect(url_for('dashboard.index'))

    loans = Loan.query.filter_by(employee_id=employee.id).order_by(Loan.created_at.desc()).all()
    return render_template('employees/detail.html', employee=employee, loans=loans)

@employee_bp.route('/api/employee/lookup/<string:emp_code>')
@login_required
def lookup_employee(emp_code):
    """
    Real-time lookup for employee auto-fetch in Loan Application and HRMS.
    Returns complete details including active loan statistics.
    """
    emp = Employee.query.filter_by(emp_id=emp_code.strip()).first()
    if not emp:
        from utils.blob_db import sync_from_blob, is_vercel
        if is_vercel():
            sync_from_blob(force=True)
            emp = Employee.query.filter_by(emp_id=emp_code.strip()).first()

    if not emp:
        return jsonify({'success': False, 'message': 'Employee not found'}), 200

    # Security check: If user cannot view all employees, verify they are authorized or querying their own record
    if not g.user.can_view_all('employees'):
        if not g.user.has_permission('loan_applications', 'add') and not g.user.has_permission('employees', 'view'):
            return jsonify({'success': False, 'message': 'Access Denied: Unauthorized to query employee records.'}), 403
        if g.user.employee_id and emp.id != g.user.employee_id:
            return jsonify({'success': False, 'message': 'Access Denied: You may only query your own employee profile.'}), 403
    
    j_date_str = emp.joining_date.strftime('%Y-%m-%d') if emp.joining_date else (emp.hiring_date.strftime('%Y-%m-%d') if emp.hiring_date else '')
    
    loans = Loan.query.filter_by(employee_id=emp.id).all()
    active_loans = [l for l in loans if l.loan_status == 'Active']
    total_outstanding = sum(l.outstanding_balance for l in active_loans)

    return jsonify({
        'success': True,
        'employee': {
            'id': emp.id,
            'emp_id': emp.emp_id,
            'name': emp.name,
            'department': emp.department,
            'designation': emp.designation,
            'current_salary': emp.current_salary,
            'joining_date': j_date_str,
            'email': emp.email or '',
            'phone': emp.phone or '',
            'status': emp.status,
            'active_loans_count': len(active_loans),
            'total_loans_count': len(loans),
            'total_outstanding': total_outstanding
        }
    })

@employee_bp.route('/employees/template/download')
@login_required
@permission_required('employees', 'import')
def download_template():
    """Downloadable blank import template in XLSX or CSV format"""
    file_format = request.args.get('format', 'xlsx').lower()
    if file_format not in ['xlsx', 'csv']:
        file_format = 'xlsx'

    template_stream = generate_blank_employee_template(file_format=file_format)
    
    if file_format == 'csv':
        filename = "AJIT_ZONE_Employee_Import_Template.csv"
        mimetype = "text/csv"
    else:
        filename = "AJIT_ZONE_Employee_Import_Template.xlsx"
        mimetype = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    return send_file(
        template_stream,
        as_attachment=True,
        download_name=filename,
        mimetype=mimetype
    )

@employee_bp.route('/employees/export')
@login_required
@permission_required('employees', 'export')
def export_employees():
    """Exports employee master records to Excel (.xlsx) or CSV format with applied filters"""
    file_format = request.args.get('format', 'xlsx').lower()
    if file_format not in ['xlsx', 'csv']:
        file_format = 'xlsx'

    search_q = request.args.get('q', '').strip()
    dept_filter = request.args.get('department', '').strip()
    status_filter = request.args.get('status', '').strip()

    query = Employee.query
    if not g.user.can_view_all('employees'):
        if g.user.employee_id:
            query = query.filter(Employee.id == g.user.employee_id)
        else:
            query = query.filter(Employee.id == -1)

    if search_q:
        query = query.filter(
            (Employee.name.ilike(f'%{search_q}%')) |
            (Employee.emp_id.ilike(f'%{search_q}%')) |
            (Employee.email.ilike(f'%{search_q}%'))
        )
    if dept_filter:
        query = query.filter(Employee.department == dept_filter)
    if status_filter:
        query = query.filter(Employee.status == status_filter)

    employees = query.order_by(Employee.emp_id.asc()).all()

    export_stream = export_employees_to_file(employees, file_format=file_format)
    timestamp_str = datetime.now().strftime('%Y%m%d_%H%M')

    if file_format == 'csv':
        filename = f"AJIT_ZONE_Employees_{timestamp_str}.csv"
        mimetype = "text/csv"
    else:
        filename = f"AJIT_ZONE_Employees_{timestamp_str}.xlsx"
        mimetype = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    return send_file(
        export_stream,
        as_attachment=True,
        download_name=filename,
        mimetype=mimetype
    )

@employee_bp.route('/employees/import', methods=['GET', 'POST'])
@login_required
@permission_required('employees', 'import')
def import_excel():
    """
    Excel/CSV Employee Import Engine:
    - Downloadable template
    - File validation & parsing
    - Duplicate detection (both in-file and database)
    - Toggle to update existing records
    - Import preview with categorization badges
    - Detailed error report
    - Import history logging
    """
    if request.method == 'POST':
        action = request.form.get('action', 'preview')

        if action == 'preview':
            if 'file' not in request.files:
                flash('Please select an Excel (.xlsx, .xls) or CSV (.csv) file.', 'danger')
                return redirect(request.url)

            file = request.files['file']
            if not file or file.filename == '':
                flash('No file was selected.', 'danger')
                return redirect(request.url)

            ext = os.path.splitext(file.filename)[1].lower()
            if ext not in ['.xlsx', '.xls', '.csv']:
                flash('Invalid file format. Please upload an Excel (.xlsx, .xls) or CSV (.csv) file.', 'danger')
                return redirect(request.url)

            os.makedirs(current_app.config['UPLOAD_FOLDER'], exist_ok=True)
            saved_filename = f"import_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{file.filename}"
            file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], saved_filename)
            file.save(file_path)

            # Get existing employee IDs to detect duplicates/updates
            existing_ids = {e.emp_id.upper() for e in Employee.query.all()}
            result = parse_excel_employee_file(file_path, existing_emp_ids=existing_ids)

            if 'error' in result:
                flash(f"Import Error: {result['error']}", 'danger')
                return redirect(request.url)

            update_existing_default = request.form.get('update_existing', '1') == '1'

            return render_template(
                'employees/import.html',
                preview=True,
                rows=result['parsed_rows'][:200], # Preview up to 200 rows
                total_rows=result['total_rows'],
                valid_count=result['valid_count'],
                new_count=result['new_count'],
                update_count=result['update_count'],
                duplicate_count=result['duplicate_count'],
                error_count=result['error_count'],
                errors_list=result['errors_list'],
                filename=file.filename,
                file_path=file_path,
                update_existing=update_existing_default
            )

        elif action == 'commit':
            file_path = request.form.get('file_path', '')
            original_filename = request.form.get('file_name', 'employee_import')
            update_existing = request.form.get('update_existing') == '1'

            if not os.path.exists(file_path):
                flash('Import session expired or file not found. Please upload again.', 'danger')
                return redirect(url_for('employee.import_excel'))

            existing_ids = {e.emp_id.upper() for e in Employee.query.all()}
            result = parse_excel_employee_file(file_path, existing_emp_ids=existing_ids)

            if 'error' in result:
                flash(f"Commit Error: {result['error']}", 'danger')
                return redirect(url_for('employee.import_excel'))

            new_success_count = 0
            update_success_count = 0
            fail_count = 0
            commit_errors = []

            for r in result['parsed_rows']:
                if not r['is_valid']:
                    fail_count += 1
                    commit_errors.append(f"Row {r['row_idx']} ({r['emp_id']}): {r['error_message']}")
                    continue

                existing = Employee.query.filter_by(emp_id=r['emp_id']).first()

                if existing:
                    if update_existing:
                        existing.name = r['name']
                        existing.department = r['department']
                        existing.designation = r['designation']
                        existing.current_salary = r['current_salary']
                        if r['joining_date']:
                            existing.joining_date = r['joining_date']
                            existing.hiring_date = r['joining_date']
                        if r['email']: existing.email = r['email']
                        if r['phone']: existing.phone = r['phone']
                        if r['pan_number']: existing.pan_number = r['pan_number']
                        if r['aadhar_number']: existing.aadhar_number = r['aadhar_number']
                        if r['bank_name']: existing.bank_name = r['bank_name']
                        if r['bank_account_no']: existing.bank_account_no = r['bank_account_no']
                        if r['ifsc_code']: existing.ifsc_code = r['ifsc_code']
                        existing.updated_at = datetime.utcnow()
                        update_success_count += 1
                    else:
                        fail_count += 1
                        commit_errors.append(f"Row {r['row_idx']} ({r['emp_id']}): Skipped existing employee (Update mode was off)")
                else:
                    new_emp = Employee(
                        emp_id=r['emp_id'],
                        name=r['name'],
                        department=r['department'],
                        designation=r['designation'],
                        current_salary=r['current_salary'],
                        joining_date=r['joining_date'] or date.today(),
                        hiring_date=r['joining_date'] or date.today(),
                        email=r['email'],
                        phone=r['phone'],
                        pan_number=r['pan_number'],
                        aadhar_number=r['aadhar_number'],
                        bank_name=r['bank_name'],
                        bank_account_no=r['bank_account_no'],
                        ifsc_code=r['ifsc_code'],
                        status='Active'
                    )
                    db.session.add(new_emp)
                    new_success_count += 1

            total_success = new_success_count + update_success_count

            imp_log = ImportLog(
                file_name=original_filename,
                records_processed=result['total_rows'],
                records_success=total_success,
                records_failed=fail_count,
                error_details=json.dumps(commit_errors[:50]) if commit_errors else None,
                imported_by_id=g.user.id
            )
            db.session.add(imp_log)

            audit = AuditLog(
                user_id=g.user.id,
                user_name=g.user.full_name,
                role=g.user.role,
                action='IMPORT',
                module='Employees',
                record_id=original_filename,
                new_value=f"Imported {original_filename}: {new_success_count} new created, {update_success_count} updated, {fail_count} skipped/failed",
                reason=f"Excel/CSV Employee Import (Update mode: {update_existing})",
                ip_address=request.remote_addr
            )
            db.session.add(audit)
            db.session.commit()

            flash(
                f"Import Complete! {new_success_count} new employees created, {update_success_count} existing updated. {fail_count} records skipped/failed.",
                'success' if fail_count == 0 else 'warning'
            )
            return redirect(url_for('employee.index'))

    # GET request - show upload form & past history
    import_history = ImportLog.query.order_by(ImportLog.imported_at.desc()).limit(15).all()
    return render_template('employees/import.html', preview=False, history=import_history)
