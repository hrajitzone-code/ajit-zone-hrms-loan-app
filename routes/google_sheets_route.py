from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, send_file, g
from models import db, Employee, Loan, EMISchedule, AuditLog
from routes.auth import login_required, permission_required
from utils.google_sheets_sync import (
    get_google_sheets_config,
    save_google_sheets_config,
    push_all_to_google_sheet,
    pull_all_from_google_sheet,
    test_google_sheet_connection,
    generate_master_excel_bytes
)
from utils.blob_db import is_vercel, sync_to_blob
from datetime import datetime
import io

google_sheets_bp = Blueprint('google_sheets', __name__)

GOOGLE_APPS_SCRIPT_TEMPLATE = """// ==============================================================
// AJIT ZONE PVT. LTD. HRMS — Google Sheets Live Database Connector
// Paste this code into: Extensions -> Apps Script -> Code.gs
// Then click Deploy -> New Deployment -> Web App (Anyone can access)
// ==============================================================

function doGet(e) {
  return handleRequest(e, 'GET');
}

function doPost(e) {
  return handleRequest(e, 'POST');
}

function handleRequest(e, method) {
  var lock = LockService.getScriptLock();
  lock.tryLock(15000);
  try {
    var ss = SpreadsheetApp.getActiveSpreadsheet();
    var data = {};
    if (e && e.postData && e.postData.contents) {
      try { data = JSON.parse(e.postData.contents); } catch (err) {}
    } else if (e && e.parameter) {
      data = e.parameter;
    }

    var action = data.action || (method === 'GET' ? 'pull_all' : 'sync_all');

    // 1. Connection Test
    if (action === 'test') {
      return jsonResponse({
        status: 'success',
        message: 'Connected to ' + ss.getName(),
        sheet_url: ss.getUrl()
      });
    }

    // 2. Sync from HRMS to Google Sheet
    if (action === 'sync_all') {
      if (data.employees && data.employees.length > 0) {
        var empSheet = getOrCreateSheet(ss, 'Employees Master', '#1e40af');
        writeTable(empSheet, [
          'Emp ID', 'Full Name', 'Department', 'Designation', 'Current Monthly Salary',
          'Status', 'Phone', 'Email', 'Joining Date'
        ], data.employees.map(function(emp) {
          return [emp.emp_id, emp.name, emp.department, emp.designation, emp.current_salary, emp.status, emp.phone, emp.email, emp.joining_date];
        }));
      }

      if (data.loans && data.loans.length > 0) {
        var loanSheet = getOrCreateSheet(ss, 'Loan Applications & Accounts', '#047857');
        writeTable(loanSheet, [
          'Loan ID', 'Emp ID', 'Employee Name', 'Loan Type', 'Loan Amount', 'Monthly EMI',
          'Tenure Months', 'Interest Rate %', 'Loan Status', 'Approval Status', 'Total Recovered',
          'Outstanding Balance', 'Reason', 'Application Date'
        ], data.loans.map(function(l) {
          return [l.loan_id, l.emp_id, l.employee_name, l.loan_type, l.loan_amount, l.monthly_emi, l.tenure_months, l.interest_rate, l.loan_status, l.approval_status, l.total_recovered, l.outstanding_balance, l.reason, l.application_date];
        }));
      }

      if (data.emi_schedules && data.emi_schedules.length > 0) {
        var emiSheet = getOrCreateSheet(ss, 'EMI Schedules', '#b45309');
        writeTable(emiSheet, [
          'Loan ID', 'Installment No', 'Due Date', 'Principal', 'Interest', 'Total EMI', 'Status', 'Paid Date'
        ], data.emi_schedules.map(function(s) {
          return [s.loan_id, s.installment_number, s.due_date, s.principal_component, s.interest_component, s.total_installment, s.status, s.paid_date];
        }));
      }

      return jsonResponse({
        status: 'success',
        message: 'All records synced successfully to Google Sheet',
        employees_count: (data.employees || []).length,
        loans_count: (data.loans || []).length,
        synced_at: new Date().toISOString()
      });
    }

    // 3. Pull from Google Sheet back to HRMS
    if (action === 'pull_all') {
      var result = { status: 'success', employees: [], loans: [] };
      
      var empSheet = ss.getSheetByName('Employees Master');
      if (empSheet) {
        var empRows = empSheet.getDataRange().getValues();
        for (var i = 1; i < empRows.length; i++) {
          var r = empRows[i];
          if (r[0]) {
            result.employees.push({
              emp_id: String(r[0]).trim(),
              name: String(r[1]).trim(),
              department: String(r[2]).trim(),
              designation: String(r[3]).trim(),
              current_salary: parseFloat(r[4]) || 0.0,
              status: String(r[5] || 'Active').trim(),
              phone: String(r[6] || '').trim(),
              email: String(r[7] || '').trim(),
              joining_date: r[8] ? String(r[8]).substring(0, 10) : ''
            });
          }
        }
      }

      var loanSheet = ss.getSheetByName('Loan Applications & Accounts');
      if (loanSheet) {
        var loanRows = loanSheet.getDataRange().getValues();
        for (var j = 1; j < loanRows.length; j++) {
          var lr = loanRows[j];
          if (lr[0]) {
            result.loans.push({
              loan_id: String(lr[0]).trim(),
              emp_id: String(lr[1]).trim(),
              employee_name: String(lr[2]).trim(),
              loan_type: String(lr[3]).trim(),
              loan_amount: parseFloat(lr[4]) || 0.0,
              monthly_emi: parseFloat(lr[5]) || 0.0,
              tenure_months: parseInt(lr[6]) || 12,
              interest_rate: parseFloat(lr[7]) || 0.0,
              loan_status: String(lr[8] || 'Pending').trim(),
              approval_status: String(lr[9] || 'Pending').trim(),
              total_recovered: parseFloat(lr[10]) || 0.0,
              outstanding_balance: parseFloat(lr[11]) || 0.0,
              reason: String(lr[12] || '').trim(),
              application_date: lr[13] ? String(lr[13]).substring(0, 10) : ''
            });
          }
        }
      }

      return jsonResponse(result);
    }

    return jsonResponse({ status: 'error', message: 'Unknown action: ' + action });
  } catch (err) {
    return jsonResponse({ status: 'error', message: err.toString() });
  } finally {
    lock.releaseLock();
  }
}

function getOrCreateSheet(ss, name, color) {
  var sheet = ss.getSheetByName(name);
  if (!sheet) {
    sheet = ss.insertSheet(name);
  }
  if (color) {
    try { sheet.setTabColor(color); } catch(e) {}
  }
  return sheet;
}

function writeTable(sheet, headers, rows) {
  sheet.clear();
  var allData = [headers].concat(rows);
  if (allData.length > 0 && allData[0].length > 0) {
    var range = sheet.getRange(1, 1, allData.length, allData[0].length);
    range.setValues(allData);

    var headerRange = sheet.getRange(1, 1, 1, headers.length);
    headerRange.setBackground('#1e293b');
    headerRange.setFontColor('#ffffff');
    headerRange.setFontWeight('bold');
    sheet.setFrozenRows(1);

    for (var col = 1; col <= headers.length; col++) {
      try { sheet.autoResizeColumn(col); } catch (e) {}
    }
  }
}

function jsonResponse(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}
"""

@google_sheets_bp.route('/google-sheets', methods=['GET'])
@login_required
@permission_required('settings', 'view')
def index():
    cfg = get_google_sheets_config()
    total_employees = Employee.query.count()
    total_loans = Loan.query.count()
    pending_loans = Loan.query.filter_by(approval_status='Pending').count()
    active_loans = Loan.query.filter_by(loan_status='Active').count()

    is_connected = bool(cfg.get('google_sheets_webapp_url'))

    return render_template(
        'google_sheets/index.html',
        cfg=cfg,
        is_connected=is_connected,
        total_employees=total_employees,
        total_loans=total_loans,
        pending_loans=pending_loans,
        active_loans=active_loans,
        apps_script_code=GOOGLE_APPS_SCRIPT_TEMPLATE
    )

@google_sheets_bp.route('/google-sheets/config', methods=['POST'])
@login_required
@permission_required('settings', 'manage')
def save_config():
    sheet_url = request.form.get('google_sheets_url', '').strip()
    webapp_url = request.form.get('google_sheets_webapp_url', '').strip()
    auto_sync = request.form.get('google_sheets_auto_sync') == 'on'

    save_google_sheets_config(sheet_url, webapp_url, auto_sync)
    flash('Google Sheets configuration saved successfully!', 'success')
    return redirect(url_for('google_sheets.index'))

@google_sheets_bp.route('/google-sheets/sync-to-sheet', methods=['POST'])
@login_required
@permission_required('settings', 'manage')
def sync_to_sheet():
    cfg = get_google_sheets_config()
    webapp_url = cfg.get('google_sheets_webapp_url')

    if not webapp_url:
        flash('Please enter and save your Google Apps Script Web App URL first.', 'warning')
        return redirect(url_for('google_sheets.index'))

    res = push_all_to_google_sheet(webapp_url)
    if res.get('success'):
        flash(res.get('message'), 'success')
    else:
        flash(res.get('message'), 'danger')

    return redirect(url_for('google_sheets.index'))

@google_sheets_bp.route('/google-sheets/sync-from-sheet', methods=['POST'])
@login_required
@permission_required('settings', 'manage')
def sync_from_sheet():
    cfg = get_google_sheets_config()
    webapp_url = cfg.get('google_sheets_webapp_url')

    if not webapp_url:
        flash('Please enter and save your Google Apps Script Web App URL first.', 'warning')
        return redirect(url_for('google_sheets.index'))

    res = pull_all_from_google_sheet(webapp_url, user_id=g.user.id)
    if res.get('success'):
        # Trigger persistence sync on Vercel
        if is_vercel():
            sync_to_blob()
        flash(res.get('message'), 'success')
    else:
        flash(res.get('message'), 'danger')

    return redirect(url_for('google_sheets.index'))

@google_sheets_bp.route('/google-sheets/test-connection', methods=['POST'])
@login_required
@permission_required('settings', 'manage')
def test_connection():
    webapp_url = request.form.get('webapp_url', '').strip()
    if not webapp_url:
        cfg = get_google_sheets_config()
        webapp_url = cfg.get('google_sheets_webapp_url', '')

    res = test_google_sheet_connection(webapp_url)
    return jsonify(res)

@google_sheets_bp.route('/google-sheets/download-excel', methods=['GET'])
@login_required
@permission_required('settings', 'view')
def download_excel():
    excel_bytes = generate_master_excel_bytes()
    filename = f"AJIT_ZONE_HRMS_GoogleSheets_Master_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return send_file(
        io.BytesIO(excel_bytes),
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=filename
    )

@google_sheets_bp.route('/api/google-sheets/webhook', methods=['POST'])
def webhook_sync():
    """
    Webhook endpoint callable by Google Apps Script triggers to synchronize data
    whenever edits occur in Google Sheets.
    """
    try:
        res = pull_all_from_google_sheet()
        if res.get('success') and is_vercel():
            sync_to_blob()
        return jsonify(res)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
