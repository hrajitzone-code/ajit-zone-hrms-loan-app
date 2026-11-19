import json
import urllib.request
import urllib.error
from datetime import datetime, date
from flask import current_app
from models import db, Employee, Loan, EMISchedule, SystemSetting, AuditLog
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
import io

class GasRedirectHandler(urllib.request.HTTPRedirectHandler):
    """
    Handles Google Apps Script Web App 302 redirects.
    Google Apps Script responds to POST requests with a 302 redirect
    to a temporary URL on script.googleusercontent.com where the JSON payload is served via GET.
    """
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return urllib.request.Request(newurl, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AjitZoneHRMS/1.0',
            'Accept': 'application/json'
        })

def get_opener():
    return urllib.request.build_opener(GasRedirectHandler())

def get_google_sheets_config():
    """Returns the current Google Sheets integration settings from the database."""
    settings = {}
    keys = [
        'google_sheets_url',
        'google_sheets_webapp_url',
        'google_sheets_auto_sync',
        'google_sheets_last_sync',
        'google_sheets_last_status'
    ]
    for k in keys:
        s = SystemSetting.query.filter_by(key=k).first()
        settings[k] = s.value if s else ''
    return settings

def save_google_sheets_config(sheet_url, webapp_url, auto_sync):
    """Saves Google Sheets settings into SystemSetting table."""
    configs = {
        'google_sheets_url': sheet_url.strip(),
        'google_sheets_webapp_url': webapp_url.strip(),
        'google_sheets_auto_sync': '1' if auto_sync else '0'
    }
    for k, v in configs.items():
        s = SystemSetting.query.filter_by(key=k).first()
        if s:
            s.value = v
        else:
            db.session.add(SystemSetting(key=k, value=v))
    db.session.commit()

def export_database_to_dict():
    """
    Serializes all employees, loans, and schedules into a structured dictionary
    ready for Google Sheets synchronization.
    """
    employees = Employee.query.order_by(Employee.id.asc()).all()
    loans = Loan.query.order_by(Loan.id.asc()).all()
    schedules = EMISchedule.query.order_by(EMISchedule.loan_id.asc(), EMISchedule.emi_no.asc()).all()

    emp_list = []
    for e in employees:
        emp_list.append({
            'emp_id': e.emp_id,
            'name': e.name,
            'department': e.department,
            'designation': e.designation,
            'current_salary': float(e.current_salary or 0.0),
            'status': e.status or 'Active',
            'phone': e.phone or '',
            'email': e.email or '',
            'pan_number': e.pan_number or '',
            'aadhar_number': e.aadhar_number or '',
            'bank_name': e.bank_name or '',
            'bank_account_no': e.bank_account_no or '',
            'ifsc_code': e.ifsc_code or '',
            'joining_date': str(e.joining_date) if e.joining_date else (str(e.hiring_date) if e.hiring_date else '')
        })

    loan_list = []
    for l in loans:
        emp_name = l.employee.name if l.employee else 'Unknown'
        emp_code = l.employee.emp_id if l.employee else ''
        loan_list.append({
            'loan_id': l.loan_id,
            'emp_id': emp_code,
            'employee_name': emp_name,
            'loan_type': l.loan_type,
            'loan_amount': float(l.loan_amount or 0.0),
            'monthly_emi': float(l.monthly_emi or 0.0),
            'tenure_months': int(l.tenure_months or 12),
            'interest_rate': float(l.interest_rate or 0.0),
            'emi_start_date': str(l.emi_start_date) if l.emi_start_date else '',
            'emi_deduction_day': int(l.emi_deduction_day or 5),
            'loan_status': l.loan_status,
            'approval_status': l.approval_status,
            'workflow_status': l.workflow_status or 'Submitted',
            'total_recovered': float(l.total_recovered or 0.0),
            'outstanding_balance': float(l.outstanding_balance or 0.0),
            'reason': l.reason or '',
            'application_date': str(l.application_date) if l.application_date else (str(l.created_at.date()) if l.created_at else '')
        })

    sch_list = []
    for s in schedules:
        sch_list.append({
            'schedule_id': s.id,
            'loan_id': s.loan.loan_id if s.loan else f"ID-{s.loan_id}",
            'installment_number': s.emi_no,
            'due_date': str(s.due_date) if s.due_date else '',
            'scheduled_emi': float(s.scheduled_emi or 0.0),
            'actual_deduction': float(s.actual_deduction or 0.0),
            'actual_deduction_date': str(s.actual_deduction_date) if s.actual_deduction_date else '',
            'outstanding_after': float(s.outstanding_after or 0.0),
            'status': s.status
        })

    return {
        'company': 'AJIT ZONE PVT. LTD.',
        'exported_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'total_employees': len(emp_list),
        'total_loans': len(loan_list),
        'employees': emp_list,
        'loans': loan_list,
        'emi_schedules': sch_list
    }

def test_google_sheet_connection(webapp_url):
    """Pings the Google Apps Script Web App URL to verify connectivity."""
    if not webapp_url:
        return {'success': False, 'message': 'Google Apps Script Web App URL is not provided.'}

    try:
        payload = json.dumps({'action': 'test'}).encode('utf-8')
        req = urllib.request.Request(webapp_url, data=payload, headers={
            'Content-Type': 'application/json',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AjitZoneHRMS/1.0'
        }, method='POST')

        opener = get_opener()
        with opener.open(req, timeout=12.0) as resp:
            content = resp.read().decode('utf-8')
            res = json.loads(content)
            if res.get('status') == 'success':
                return {
                    'success': True,
                    'message': f"Connected successfully! Linked to: {res.get('message', 'Google Sheet')}",
                    'sheet_url': res.get('sheet_url', '')
                }
            return {'success': False, 'message': res.get('message', 'Unknown response from Google Apps Script')}
    except urllib.error.HTTPError as e:
        return {'success': False, 'message': f"HTTP Error {e.code}: {e.reason}"}
    except urllib.error.URLError as e:
        return {'success': False, 'message': f"Connection Error: {e.reason}"}
    except Exception as e:
        return {'success': False, 'message': f"Error: {str(e)}"}

def push_all_to_google_sheet(webapp_url=None):
    """
    Pushes all employees, loans, and schedules from SQLite into the connected Google Sheet.
    """
    cfg = get_google_sheets_config()
    target_url = (webapp_url or cfg.get('google_sheets_webapp_url', '')).strip()

    if not target_url:
        return {'success': False, 'message': 'No Google Apps Script Web App URL configured.'}

    data = export_database_to_dict()
    data['action'] = 'sync_all'

    try:
        payload = json.dumps(data).encode('utf-8')
        req = urllib.request.Request(target_url, data=payload, headers={
            'Content-Type': 'application/json',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AjitZoneHRMS/1.0'
        }, method='POST')

        opener = get_opener()
        with opener.open(req, timeout=25.0) as resp:
            raw_res = resp.read().decode('utf-8')
            res = json.loads(raw_res)

        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        # Update last sync timestamp
        for k, v in [('google_sheets_last_sync', now_str), ('google_sheets_last_status', 'Success')]:
            s = SystemSetting.query.filter_by(key=k).first()
            if s:
                s.value = v
            else:
                db.session.add(SystemSetting(key=k, value=v))
        db.session.commit()

        return {
            'success': True,
            'message': f"Successfully synced {data['total_employees']} employees and {data['total_loans']} loan applications to Google Sheet!",
            'synced_at': now_str,
            'details': res
        }
    except Exception as e:
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        err_msg = str(e)
        s = SystemSetting.query.filter_by(key='google_sheets_last_status').first()
        if s:
            s.value = f"Failed: {err_msg[:60]}"
            db.session.commit()
        return {'success': False, 'message': f"Failed to push to Google Sheet: {err_msg}"}

def pull_all_from_google_sheet(webapp_url=None, user_id=None):
    """
    Pulls data from the connected Google Sheet and updates/creates records in the HRMS SQLite database.
    """
    cfg = get_google_sheets_config()
    target_url = (webapp_url or cfg.get('google_sheets_webapp_url', '')).strip()

    if not target_url:
        return {'success': False, 'message': 'No Google Apps Script Web App URL configured.'}

    try:
        payload = json.dumps({'action': 'pull_all'}).encode('utf-8')
        req = urllib.request.Request(target_url, data=payload, headers={
            'Content-Type': 'application/json',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AjitZoneHRMS/1.0'
        }, method='POST')

        opener = get_opener()
        with opener.open(req, timeout=25.0) as resp:
            res = json.loads(resp.read().decode('utf-8'))

        if res.get('status') != 'success':
            return {'success': False, 'message': res.get('message', 'Failed to retrieve data from sheet')}

        sheet_employees = res.get('employees', [])
        sheet_loans = res.get('loans', [])

        emp_updated = 0
        emp_created = 0
        loan_updated = 0
        loan_created = 0

        # Process Employees from Google Sheet
        for emp_row in sheet_employees:
            emp_code = emp_row.get('emp_id', '').strip()
            if not emp_code:
                continue

            existing = Employee.query.filter_by(emp_id=emp_code).first()
            if existing:
                existing.name = emp_row.get('name') or existing.name
                existing.department = emp_row.get('department') or existing.department
                existing.designation = emp_row.get('designation') or existing.designation
                if 'current_salary' in emp_row and float(emp_row['current_salary']) > 0:
                    existing.current_salary = float(emp_row['current_salary'])
                if emp_row.get('phone'):
                    existing.phone = emp_row['phone']
                if emp_row.get('email'):
                    existing.email = emp_row['email']
                if emp_row.get('status'):
                    existing.status = emp_row['status']
                emp_updated += 1
            else:
                new_emp = Employee(
                    emp_id=emp_code,
                    name=emp_row.get('name', 'Staff Member'),
                    department=emp_row.get('department', 'General'),
                    designation=emp_row.get('designation', 'Staff'),
                    current_salary=float(emp_row.get('current_salary', 0.0)),
                    phone=emp_row.get('phone', ''),
                    email=emp_row.get('email', ''),
                    status=emp_row.get('status', 'Active'),
                    joining_date=datetime.strptime(emp_row['joining_date'], '%Y-%m-%d').date() if emp_row.get('joining_date') else date.today()
                )
                db.session.add(new_emp)
                emp_created += 1

        db.session.flush()

        # Process Loans from Google Sheet
        for loan_row in sheet_loans:
            loan_code = loan_row.get('loan_id', '').strip()
            emp_code = loan_row.get('emp_id', '').strip()
            if not loan_code or not emp_code:
                continue

            emp = Employee.query.filter_by(emp_id=emp_code).first()
            if not emp:
                continue

            existing_loan = Loan.query.filter_by(loan_id=loan_code).first()
            if existing_loan:
                if 'loan_amount' in loan_row and float(loan_row['loan_amount']) > 0:
                    existing_loan.loan_amount = float(loan_row['loan_amount'])
                if 'monthly_emi' in loan_row and float(loan_row['monthly_emi']) > 0:
                    existing_loan.monthly_emi = float(loan_row['monthly_emi'])
                if 'tenure_months' in loan_row and int(loan_row['tenure_months']) > 0:
                    existing_loan.tenure_months = int(loan_row['tenure_months'])
                if loan_row.get('loan_status'):
                    existing_loan.loan_status = loan_row['loan_status']
                if loan_row.get('approval_status'):
                    existing_loan.approval_status = loan_row['approval_status']
                if 'total_recovered' in loan_row:
                    existing_loan.total_recovered = float(loan_row['total_recovered'])
                if 'outstanding_balance' in loan_row:
                    existing_loan.outstanding_balance = float(loan_row['outstanding_balance'])
                loan_updated += 1
            else:
                amt = float(loan_row.get('loan_amount', 0.0))
                emi = float(loan_row.get('monthly_emi', 0.0))
                new_loan = Loan(
                    loan_id=loan_code,
                    employee_id=emp.id,
                    loan_type=loan_row.get('loan_type', 'Personal Loan'),
                    loan_amount=amt,
                    monthly_emi=emi,
                    tenure_months=int(loan_row.get('tenure_months', 12)),
                    interest_rate=float(loan_row.get('interest_rate', 0.0)),
                    emi_start_date=date.today(),
                    emi_deduction_day=5,
                    reason=loan_row.get('reason', 'Imported from Google Sheet'),
                    approval_status=loan_row.get('approval_status', 'Pending'),
                    loan_status=loan_row.get('loan_status', 'Pending'),
                    workflow_status='Submitted',
                    total_recovered=float(loan_row.get('total_recovered', 0.0)),
                    outstanding_balance=float(loan_row.get('outstanding_balance', amt))
                )
                db.session.add(new_loan)
                loan_created += 1

        # Audit Log
        audit = AuditLog(
            user_id=user_id or 1,
            user_name='Google Sheets Sync',
            role='System',
            action='IMPORT',
            module='GoogleSheets',
            record_id='BULK',
            new_value=f"Pulled from Google Sheet: {emp_created} new / {emp_updated} updated employees, {loan_created} new / {loan_updated} updated loans",
            reason='Google Sheet Database Sync'
        )
        db.session.add(audit)
        db.session.commit()

        # Update last sync timestamp
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        s = SystemSetting.query.filter_by(key='google_sheets_last_sync').first()
        if s:
            s.value = now_str
            db.session.commit()

        return {
            'success': True,
            'message': f"Sync complete! Employees: {emp_created} created, {emp_updated} updated. Loans: {loan_created} created, {loan_updated} updated.",
            'emp_created': emp_created,
            'emp_updated': emp_updated,
            'loan_created': loan_created,
            'loan_updated': loan_updated,
            'synced_at': now_str
        }

    except Exception as e:
        return {'success': False, 'message': f"Failed to pull from Google Sheet: {str(e)}"}

def trigger_auto_sync_if_enabled():
    """
    Called after mutations (loan application, approval, employee creation/deletion).
    If auto-sync is toggled on, pushes changes to Google Sheet.
    """
    cfg = get_google_sheets_config()
    if cfg.get('google_sheets_auto_sync') == '1' and cfg.get('google_sheets_webapp_url'):
        try:
            push_all_to_google_sheet(cfg.get('google_sheets_webapp_url'))
        except Exception as e:
            print(f"[GOOGLE SHEETS AUTO-SYNC ERROR]: {e}")

def generate_master_excel_bytes():
    """
    Generates a beautifully formatted multi-tab Excel workbook containing all
    employees, loans, and schedules for direct upload into Google Drive / Google Sheets.
    """
    wb = openpyxl.Workbook()
    
    # 1. Employees Tab
    ws_emp = wb.active
    ws_emp.title = "Employees Master"
    
    header_fill = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    
    emp_headers = [
        "Employee ID", "Full Name", "Department", "Designation",
        "Current Monthly Salary", "Status", "Mobile Phone", "Email Address",
        "PAN Number", "Aadhaar Number", "Bank Name", "IFSC Code", "Joining Date"
    ]
    ws_emp.append(emp_headers)
    for col_num in range(1, len(emp_headers) + 1):
        cell = ws_emp.cell(row=1, column=col_num)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")

    employees = Employee.query.order_by(Employee.id.asc()).all()
    for e in employees:
        ws_emp.append([
            e.emp_id,
            e.name,
            e.department,
            e.designation,
            float(e.current_salary or 0.0),
            e.status or 'Active',
            e.phone or '',
            e.email or '',
            e.pan_number or '',
            e.aadhar_number or '',
            e.bank_name or '',
            e.ifsc_code or '',
            str(e.joining_date) if e.joining_date else (str(e.hiring_date) if e.hiring_date else '')
        ])

    for col in ws_emp.columns:
        max_len = max(len(str(cell.value or '')) for cell in col)
        col_letter = openpyxl.utils.get_column_letter(col[0].column)
        ws_emp.column_dimensions[col_letter].width = max(max_len + 3, 12)

    # 2. Loans Tab
    ws_loan = wb.create_sheet(title="Loan Applications & Accounts")
    loan_headers = [
        "Loan ID", "Employee ID", "Employee Name", "Department",
        "Loan Type", "Loan Amount (Rs.)", "Monthly EMI (Rs.)", "Tenure (Months)",
        "Interest Rate (%)", "Approval Status", "Loan Status", "Workflow Status",
        "Total Recovered (Rs.)", "Outstanding Balance (Rs.)", "Purpose / Reason", "Application Date"
    ]
    ws_loan.append(loan_headers)
    for col_num in range(1, len(loan_headers) + 1):
        cell = ws_loan.cell(row=1, column=col_num)
        cell.fill = PatternFill(start_color="047857", end_color="047857", fill_type="solid")
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")

    loans = Loan.query.order_by(Loan.id.asc()).all()
    for l in loans:
        emp_name = l.employee.name if l.employee else 'Unknown'
        emp_code = l.employee.emp_id if l.employee else ''
        emp_dept = l.employee.department if l.employee else ''
        ws_loan.append([
            l.loan_id,
            emp_code,
            emp_name,
            emp_dept,
            l.loan_type,
            float(l.loan_amount or 0.0),
            float(l.monthly_emi or 0.0),
            int(l.tenure_months or 12),
            float(l.interest_rate or 0.0),
            l.approval_status,
            l.loan_status,
            l.workflow_status or 'Submitted',
            float(l.total_recovered or 0.0),
            float(l.outstanding_balance or 0.0),
            l.reason or '',
            str(l.application_date) if l.application_date else (str(l.created_at.date()) if l.created_at else '')
        ])

    for col in ws_loan.columns:
        max_len = max(len(str(cell.value or '')) for cell in col)
        col_letter = openpyxl.utils.get_column_letter(col[0].column)
        ws_loan.column_dimensions[col_letter].width = max(max_len + 3, 12)

    # 3. EMI Schedules Tab
    ws_sch = wb.create_sheet(title="EMI Schedules")
    sch_headers = [
        "Schedule ID", "Loan ID", "EMI No", "Due Date",
        "Scheduled EMI (Rs.)", "Actual Deduction (Rs.)", "Actual Deduction Date", "Outstanding After (Rs.)", "Status"
    ]
    ws_sch.append(sch_headers)
    for col_num in range(1, len(sch_headers) + 1):
        cell = ws_sch.cell(row=1, column=col_num)
        cell.fill = PatternFill(start_color="B45309", end_color="B45309", fill_type="solid")
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")

    schedules = EMISchedule.query.order_by(EMISchedule.loan_id.asc(), EMISchedule.emi_no.asc()).all()
    for s in schedules:
        ws_sch.append([
            s.id,
            s.loan.loan_id if s.loan else f"ID-{s.loan_id}",
            s.emi_no,
            str(s.due_date) if s.due_date else '',
            float(s.scheduled_emi or 0.0),
            float(s.actual_deduction or 0.0),
            str(s.actual_deduction_date) if s.actual_deduction_date else '',
            float(s.outstanding_after or 0.0),
            s.status
        ])

    for col in ws_sch.columns:
        max_len = max(len(str(cell.value or '')) for cell in col)
        col_letter = openpyxl.utils.get_column_letter(col[0].column)
        ws_sch.column_dimensions[col_letter].width = max(max_len + 3, 12)

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return output.getvalue()
