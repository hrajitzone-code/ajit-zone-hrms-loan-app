import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from datetime import datetime, date
import pandas as pd
import csv
import io
import os
import re

HEADER_MAPPING = {
    'emp_id': ['employee id', 'emp id', 'empid', 'id', 'employee_id', 'emp_no', 'staff id'],
    'name': ['employee name', 'emp name', 'name', 'full name', 'employee_name', 'staff name'],
    'department': ['department', 'dept', 'dept name', 'department name'],
    'designation': ['job title', 'designation', 'role', 'title', 'position'],
    'current_salary': ['current salary', 'salary', 'initial salary', 'basic salary', 'monthly salary', 'gross salary'],
    'joining_date': ['joining date', 'date of joining', 'doj', 'hiring date', 'hire date', 'start date'],
    'email': ['email', 'email address', 'official email', 'e-mail'],
    'phone': ['cell phone', 'phone', 'contact info', 'mobile', 'mobile number', 'contact number'],
    'pan_number': ['pan details', 'pan', 'pan number', 'pan card', 'pan no'],
    'aadhar_number': ['id / aadhar card', 'aadhar', 'aadhar card', 'aadhar number', 'national id', 'aadhaar'],
    'bank_name': ['bank name', 'bank'],
    'bank_account_no': ['bank account no', 'bank account', 'account number', 'account no', 'acc no', 'bank a/c no'],
    'ifsc_code': ['ifsc code', 'ifsc', 'ifsc code / branch'],
    'address': ['address', 'residence address', 'street address'],
    'city': ['city', 'location']
}

def normalize_header(header_val):
    if not header_val:
        return ''
    return str(header_val).strip().lower()

def map_excel_headers(headers):
    mapping = {}
    for idx, raw_h in enumerate(headers):
        norm_h = normalize_header(raw_h)
        for field, keywords in HEADER_MAPPING.items():
            if norm_h in keywords:
                mapping[field] = idx
                break
    return mapping

def parse_date_value(val):
    """Safely converts various date representations to a date object or string YYYY-MM-DD"""
    if not val:
        return None
    if isinstance(val, (datetime, date)):
        return val if isinstance(val, date) and not isinstance(val, datetime) else val.date()
    
    val_str = str(val).strip()
    if not val_str or val_str.lower() in ['none', 'null', 'na', 'n/a', '-']:
        return None
    
    # Try various formats
    formats = ['%Y-%m-%d', '%d-%m-%Y', '%d/%m/%Y', '%m/%d/%Y', '%d-%b-%Y', '%d-%B-%Y', '%Y/%m/%d']
    for fmt in formats:
        try:
            return datetime.strptime(val_str.split(' ')[0], fmt).date()
        except ValueError:
            continue
    return None

def parse_excel_employee_file(file_path, existing_emp_ids=None):
    """
    Parses both Excel (.xlsx, .xls) and CSV (.csv) files.
    Performs validation, duplicate detection (both in-file and existing in DB),
    and categorizes each row into NEW, UPDATE, DUPLICATE_IN_FILE, or INVALID.
    """
    if existing_emp_ids is None:
        existing_emp_ids = set()
    else:
        existing_emp_ids = set(existing_emp_ids)

    rows = []
    ext = os.path.splitext(file_path)[1].lower()

    if ext == '.csv':
        try:
            with open(file_path, mode='r', encoding='utf-8-sig', errors='replace') as f:
                reader = csv.reader(f)
                rows = list(reader)
        except Exception as e:
            return {'error': f"Failed to read CSV file: {str(e)}"}
    else:
        try:
            wb = openpyxl.load_workbook(file_path, data_only=True)
            target_sheet_name = 'HR_Data' if 'HR_Data' in wb.sheetnames else wb.sheetnames[0]
            ws = wb[target_sheet_name]
            rows = list(ws.iter_rows(values_only=True))
        except Exception as e:
            return {'error': f"Failed to read Excel workbook: {str(e)}"}

    if not rows or len(rows) < 2:
        return {'error': 'Uploaded file is empty or contains no data rows.'}

    raw_headers = [str(c).strip() if c is not None else '' for c in rows[0]]
    field_mapping = map_excel_headers(raw_headers)

    if 'emp_id' not in field_mapping or 'name' not in field_mapping:
        return {
            'error': 'Required columns missing! File must contain at least "Employee ID" and "Employee Name" columns.'
        }

    parsed_rows = []
    errors_list = []
    seen_in_file = set()

    for row_idx, row in enumerate(rows[1:], start=2):
        if not any(row):
            continue

        raw_emp_id = row[field_mapping['emp_id']] if 'emp_id' in field_mapping and field_mapping['emp_id'] < len(row) else ''
        raw_name = row[field_mapping['name']] if 'name' in field_mapping and field_mapping['name'] < len(row) else ''

        emp_id = str(raw_emp_id).strip() if raw_emp_id is not None else ''
        name = str(raw_name).strip() if raw_name is not None else ''

        row_errors = []
        status = 'NEW'

        # Check required fields
        if not emp_id or emp_id.lower() in ['none', 'null', 'nan']:
            row_errors.append("Missing Employee ID")
        if not name or name.lower() in ['none', 'null', 'nan']:
            row_errors.append("Missing Employee Name")

        # Duplicate in file detection
        if emp_id:
            if emp_id.upper() in seen_in_file:
                row_errors.append(f"Duplicate Employee ID '{emp_id}' in uploaded file")
                status = 'DUPLICATE_IN_FILE'
            else:
                seen_in_file.add(emp_id.upper())
                if emp_id in existing_emp_ids:
                    status = 'UPDATE'
                else:
                    status = 'NEW'

        # Parse remaining fields
        department = str(row[field_mapping['department']]).strip() if 'department' in field_mapping and field_mapping['department'] < len(row) and row[field_mapping['department']] is not None else 'General'
        designation = str(row[field_mapping['designation']]).strip() if 'designation' in field_mapping and field_mapping['designation'] < len(row) and row[field_mapping['designation']] is not None else 'Staff'

        salary = 0.0
        if 'current_salary' in field_mapping and field_mapping['current_salary'] < len(row) and row[field_mapping['current_salary']] is not None:
            raw_sal = str(row[field_mapping['current_salary']]).replace('₹', '').replace(',', '').strip()
            try:
                salary = max(0.0, float(raw_sal))
            except (ValueError, TypeError):
                salary = 0.0

        raw_date = row[field_mapping['joining_date']] if 'joining_date' in field_mapping and field_mapping['joining_date'] < len(row) else None
        joining_date_val = parse_date_value(raw_date)

        email = str(row[field_mapping['email']]).strip() if 'email' in field_mapping and field_mapping['email'] < len(row) and row[field_mapping['email']] is not None else ''
        phone = str(row[field_mapping['phone']]).strip() if 'phone' in field_mapping and field_mapping['phone'] < len(row) and row[field_mapping['phone']] is not None else ''
        pan = str(row[field_mapping['pan_number']]).strip() if 'pan_number' in field_mapping and field_mapping['pan_number'] < len(row) and row[field_mapping['pan_number']] is not None else ''
        aadhar = str(row[field_mapping['aadhar_number']]).strip() if 'aadhar_number' in field_mapping and field_mapping['aadhar_number'] < len(row) and row[field_mapping['aadhar_number']] is not None else ''
        bank_name = str(row[field_mapping['bank_name']]).strip() if 'bank_name' in field_mapping and field_mapping['bank_name'] < len(row) and row[field_mapping['bank_name']] is not None else ''
        bank_acc = str(row[field_mapping['bank_account_no']]).strip() if 'bank_account_no' in field_mapping and field_mapping['bank_account_no'] < len(row) and row[field_mapping['bank_account_no']] is not None else ''
        ifsc = str(row[field_mapping['ifsc_code']]).strip() if 'ifsc_code' in field_mapping and field_mapping['ifsc_code'] < len(row) and row[field_mapping['ifsc_code']] is not None else ''

        if row_errors:
            if status != 'DUPLICATE_IN_FILE':
                status = 'INVALID'
            for err in row_errors:
                errors_list.append({
                    'row_idx': row_idx,
                    'emp_id': emp_id or 'N/A',
                    'reason': err
                })

        parsed_rows.append({
            'row_idx': row_idx,
            'emp_id': emp_id,
            'name': name,
            'department': department if department.lower() != 'none' else 'General',
            'designation': designation if designation.lower() != 'none' else 'Staff',
            'current_salary': salary,
            'joining_date': joining_date_val,
            'email': email if email.lower() != 'none' else '',
            'phone': phone if phone.lower() != 'none' else '',
            'pan_number': pan if pan.lower() != 'none' else '',
            'aadhar_number': aadhar if aadhar.lower() != 'none' else '',
            'bank_name': bank_name if bank_name.lower() != 'none' else '',
            'bank_account_no': bank_acc if bank_acc.lower() != 'none' else '',
            'ifsc_code': ifsc if ifsc.lower() != 'none' else '',
            'status': status,
            'is_valid': len(row_errors) == 0,
            'error_message': "; ".join(row_errors)
        })

    valid_rows = [r for r in parsed_rows if r['is_valid']]
    new_count = len([r for r in valid_rows if r['status'] == 'NEW'])
    update_count = len([r for r in valid_rows if r['status'] == 'UPDATE'])
    duplicate_count = len([r for r in parsed_rows if r['status'] == 'DUPLICATE_IN_FILE'])
    error_count = len([r for r in parsed_rows if not r['is_valid']])

    return {
        'total_rows': len(parsed_rows),
        'valid_count': len(valid_rows),
        'new_count': new_count,
        'update_count': update_count,
        'duplicate_count': duplicate_count,
        'error_count': error_count,
        'parsed_rows': parsed_rows,
        'errors_list': errors_list
    }

def generate_blank_employee_template(file_format='xlsx'):
    """
    Generates a blank downloadable template for importing employees into the Master.
    Includes styled headers and sample reference rows.
    """
    headers = [
        'Employee ID',
        'Full Name',
        'Department',
        'Designation',
        'Current Monthly Salary',
        'Joining Date (YYYY-MM-DD)',
        'Email Address',
        'Phone Number',
        'PAN Number',
        'Aadhar Number',
        'Bank Name',
        'Bank Account Number',
        'IFSC Code'
    ]

    sample_rows = [
        [
            'EMP9001',
            'Rajesh Kumar Sharma',
            'Finance',
            'Accounts Manager',
            65000,
            '2024-01-15',
            'rajesh.sharma@ajitzone.com',
            '9876543210',
            'ABCDE1234F',
            '123456789012',
            'HDFC Bank',
            '50100234567890',
            'HDFC0001234'
        ],
        [
            'EMP9002',
            'Pooja Verma',
            'Human Resources',
            'HR Executive',
            42000,
            '2024-03-01',
            'pooja.verma@ajitzone.com',
            '9812345678',
            'FGHIJ5678K',
            '987654321098',
            'ICICI Bank',
            '001205004567',
            'ICIC0000012'
        ]
    ]

    if file_format.lower() == 'csv':
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(headers)
        writer.writerows(sample_rows)
        return io.BytesIO(output.getvalue().encode('utf-8'))

    # Excel format
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Employee_Import_Template"

    header_fill = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    align_center = Alignment(horizontal="center", vertical="center", wrap_text=True)

    border_thin = Border(
        left=Side(style='thin', color='CBD5E1'),
        right=Side(style='thin', color='CBD5E1'),
        top=Side(style='thin', color='CBD5E1'),
        bottom=Side(style='thin', color='CBD5E1')
    )

    ws.append(headers)
    ws.row_dimensions[1].height = 28

    for col_idx in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col_idx)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = align_center
        cell.border = border_thin

    for row_data in sample_rows:
        ws.append(row_data)

    sample_fill = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")
    for row in ws.iter_rows(min_row=2, max_row=ws.max_row, min_col=1, max_col=len(headers)):
        for cell in row:
            cell.border = border_thin
            cell.fill = sample_fill
            if isinstance(cell.value, (int, float)):
                cell.number_format = '#,##0.00'

    # Auto-adjust column widths
    for col in ws.columns:
        max_len = max(len(str(cell.value or '')) for cell in col)
        col_letter = get_column_letter(col[0].column)
        ws.column_dimensions[col_letter].width = max(max_len + 4, 15)

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return output

def export_employees_to_file(employees, file_format='xlsx'):
    """
    Exports a list of Employee database objects into a styled Excel workbook or CSV stream.
    """
    columns = [
        'Employee ID',
        'Full Name',
        'Department',
        'Designation',
        'Current Salary (₹)',
        'Joining Date',
        'Status',
        'Email Address',
        'Phone Number',
        'PAN Number',
        'Aadhar Number',
        'Bank Name',
        'Bank Account Number',
        'IFSC Code'
    ]

    rows = []
    for emp in employees:
        j_date = emp.joining_date.strftime('%Y-%m-%d') if emp.joining_date else (emp.hiring_date.strftime('%Y-%m-%d') if emp.hiring_date else '')
        rows.append([
            emp.emp_id,
            emp.name,
            emp.department,
            emp.designation,
            emp.current_salary,
            j_date,
            emp.status,
            emp.email or '',
            emp.phone or '',
            emp.pan_number or '',
            emp.aadhar_number or '',
            emp.bank_name or '',
            emp.bank_account_no or '',
            emp.ifsc_code or ''
        ])

    if file_format.lower() == 'csv':
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(columns)
        writer.writerows(rows)
        return io.BytesIO(output.getvalue().encode('utf-8'))

    return export_data_to_excel(columns, rows, sheet_title="Employee_Directory")

def export_data_to_excel(columns, data_rows, sheet_title="Report"):
    """
    Exports generic list of dicts or tuples to a styled Excel workbook stream.
    """
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet_title[:31]

    # Header styling
    header_fill = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    align_center = Alignment(horizontal="center", vertical="center", wrap_text=True)

    ws.append(columns)
    ws.row_dimensions[1].height = 26

    border_thin = Border(
        left=Side(style='thin', color='E2E8F0'),
        right=Side(style='thin', color='E2E8F0'),
        top=Side(style='thin', color='E2E8F0'),
        bottom=Side(style='thin', color='E2E8F0')
    )

    for col_num in range(1, len(columns) + 1):
        cell = ws.cell(row=1, column=col_num)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = align_center
        cell.border = border_thin

    for row_data in data_rows:
        ws.append(row_data)

    for row in ws.iter_rows(min_row=2, max_row=ws.max_row, min_col=1, max_col=len(columns)):
        for cell in row:
            cell.border = border_thin
            if isinstance(cell.value, (int, float)):
                cell.number_format = '#,##0.00'

    for col in ws.columns:
        max_len = max(len(str(cell.value or '')) for cell in col)
        col_letter = get_column_letter(col[0].column)
        ws.column_dimensions[col_letter].width = max(max_len + 4, 14)

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return output
