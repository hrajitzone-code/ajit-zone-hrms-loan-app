from flask import Blueprint, render_template, jsonify, g, request
from models import db, Employee, Loan, EMISchedule, LoanClosure, AuditLog, SalarySheetSync
from routes.auth import login_required, permission_required
from utils.automation import run_daily_loan_automation
from utils.blob_db import sync_from_blob, is_vercel
from datetime import datetime, date, timedelta
from sqlalchemy import func

dashboard_bp = Blueprint('dashboard', __name__)

@dashboard_bp.route('/')
@dashboard_bp.route('/dashboard')
@login_required
@permission_required('dashboard', 'view')
def index():
    # Force cloud sync if manual refresh is requested, or ensure latest data from Vercel Blob
    force_refresh = request.args.get('refresh') == '1'
    if is_vercel():
        sync_from_blob(force=force_refresh)

    run_daily_loan_automation(system_user_id=g.user.id if g.user else 1)

    user_role = g.user.role if g.user else 'HR'
    today = date.today()
    last_updated_str = datetime.now().strftime('%d %b %Y, %I:%M %p')

    # 1. EMPLOYEE ROLE DASHBOARD
    if user_role == 'Employee':
        emp = g.user.employee if g.user else None
        emp_id_pk = emp.id if emp else None
        
        my_loans = Loan.query.filter_by(employee_id=emp_id_pk).order_by(Loan.created_at.desc(), Loan.id.desc()).all() if emp_id_pk else []
        active_loan = Loan.query.filter_by(employee_id=emp_id_pk, loan_status='Active').first() if emp_id_pk else None
        
        my_schedules = []
        remaining_emis_count = 0
        if active_loan:
            my_schedules = EMISchedule.query.filter_by(loan_id=active_loan.id).order_by(EMISchedule.emi_no.asc()).all()
            remaining_emis_count = len([s for s in my_schedules if s.status in ['Upcoming', 'Due', 'Pending', 'Overdue']])

        emp_stats = {
            'total_loans': len(my_loans),
            'active_loan': active_loan,
            'my_loans': my_loans,
            'schedules': my_schedules,
            'remaining_emis': remaining_emis_count,
            'outstanding': active_loan.outstanding_balance if active_loan else 0.0,
            'monthly_emi': active_loan.monthly_emi if active_loan else 0.0
        }
        return render_template('dashboard.html', view_type='employee', emp_stats=emp_stats, last_updated=last_updated_str)

    # 2. FINANCE / PAYROLL ROLE DASHBOARD
    elif user_role == 'Finance_Payroll':
        current_m_str = today.strftime('%Y-%m')
        sync_items = SalarySheetSync.query.filter_by(salary_month=current_m_str).all()
        
        deductions_m = EMISchedule.query.filter(
            func.strftime('%Y-%m', EMISchedule.due_date) == current_m_str
        ).all()

        all_loans = Loan.query.all()
        active_loans = [l for l in all_loans if l.loan_status in ['Active', 'Approved']]

        fin_stats = {
            'total_loan_applications': len(all_loans),
            'total_loan_amount': sum(float(l.loan_amount or 0.0) for l in all_loans),
            'total_recovered_all': sum(float(l.total_recovered or 0.0) for l in all_loans),
            'total_outstanding_active': sum(float(l.outstanding_balance or 0.0) for l in active_loans),
            'current_month_scheduled': sum(float(s.scheduled_emi or 0.0) for s in deductions_m),
            'current_month_deducted': sum(float(s.actual_deduction or 0.0) for s in deductions_m),
            'sync_pending_count': len([s for s in sync_items if s.deduction_status == 'Pending']),
            'sync_processed_count': len([s for s in sync_items if s.deduction_status == 'Processed']),
            'closures_count': LoanClosure.query.count()
        }

        recent_deductions = EMISchedule.query.filter(EMISchedule.status.in_(['Deducted', 'Partial', 'Overdue'])).order_by(EMISchedule.actual_deduction_date.desc()).limit(10).all()
        return render_template('dashboard.html', view_type='finance', fin_stats=fin_stats, recent_deductions=recent_deductions, last_updated=last_updated_str)

    # 3. HR / ADMIN / SUPER ADMIN / MANAGER EXECUTIVE DASHBOARD
    else:
        total_employees = Employee.query.filter_by(status='Active').count()
        
        # Loan Application Status Counts
        total_applications_count = Loan.query.count()
        pending_apps_count = Loan.query.filter_by(loan_status='Pending').count()
        active_loans_count = Loan.query.filter(Loan.loan_status.in_(['Active', 'Approved'])).count()
        closed_loans_count = Loan.query.filter_by(loan_status='Closed').count()
        rejected_apps_count = Loan.query.filter_by(loan_status='Rejected').count()

        # Loan Amounts Across All Applications
        all_loans = Loan.query.all()
        total_loan_amount = sum(float(l.loan_amount or 0.0) for l in all_loans)
        pending_loan_amount = sum(float(l.loan_amount or 0.0) for l in all_loans if l.loan_status == 'Pending')
        active_disbursed_amount = sum(float(l.loan_amount or 0.0) for l in all_loans if l.loan_status in ['Active', 'Approved'])
        total_recovered = sum(float(l.total_recovered or 0.0) for l in all_loans)
        total_outstanding = sum(float(l.outstanding_balance or 0.0) for l in all_loans if l.loan_status == 'Active')

        current_month_schedules = EMISchedule.query.filter(
            func.strftime('%Y-%m', EMISchedule.due_date) == today.strftime('%Y-%m')
        ).all()

        current_month_emi_total = sum(float(s.scheduled_emi or 0.0) for s in current_month_schedules)
        deducted_emi_total = sum(float(s.actual_deduction or 0.0) for s in current_month_schedules)

        overdue_schedules = EMISchedule.query.filter(EMISchedule.status == 'Overdue').all()
        overdue_emi_total = sum(float(s.scheduled_emi or 0.0) - float(s.actual_deduction or 0.0) for s in overdue_schedules)
        overdue_count = len(overdue_schedules)

        recent_audits = AuditLog.query.order_by(AuditLog.timestamp.desc()).limit(8).all()
        recent_loans = Loan.query.order_by(Loan.created_at.desc(), Loan.id.desc()).limit(8).all()

        stats = {
            'total_employees': total_employees,
            'total_applications': total_applications_count,
            'active_loans': active_loans_count,
            'pending_apps': pending_apps_count,
            'closed_loans': closed_loans_count,
            'rejected_apps': rejected_apps_count,
            'total_loan_amount': round(total_loan_amount, 2),
            'pending_loan_amount': round(pending_loan_amount, 2),
            'active_disbursed_amount': round(active_disbursed_amount, 2),
            'total_recovered': round(total_recovered, 2),
            'total_outstanding': round(total_outstanding, 2),
            'current_month_emi': round(current_month_emi_total, 2),
            'deducted_emi': round(deducted_emi_total, 2),
            'overdue_emi': round(overdue_emi_total, 2),
            'overdue_count': overdue_count
        }

        return render_template(
            'dashboard.html',
            view_type='hr',
            stats=stats,
            recent_audits=recent_audits,
            recent_loans=recent_loans,
            last_updated=last_updated_str
        )

@dashboard_bp.route('/api/dashboard/chart-data')
@login_required
def chart_data():
    if is_vercel():
        sync_from_blob()

    today = date.today()

    dept_data = db.session.query(
        Employee.department,
        func.sum(Loan.loan_amount)
    ).join(Loan, Loan.employee_id == Employee.id)\
     .group_by(Employee.department).all()

    dept_labels = [d[0] for d in dept_data] or ['General']
    dept_values = [float(d[1] or 0.0) for d in dept_data] or [0.0]

    active_cnt = Loan.query.filter(Loan.loan_status.in_(['Active', 'Approved'])).count()
    closed_cnt = Loan.query.filter_by(loan_status='Closed').count()
    pending_cnt = Loan.query.filter_by(loan_status='Pending').count()
    rejected_cnt = Loan.query.filter_by(loan_status='Rejected').count()

    months_labels = []
    recovery_values = []
    scheduled_values = []

    for i in range(5, -1, -1):
        target_month = date(today.year, today.month, 1) - timedelta(days=i*30)
        m_str = target_month.strftime('%Y-%m')
        m_name = target_month.strftime('%b %Y')
        months_labels.append(m_name)

        scheds = EMISchedule.query.filter(func.strftime('%Y-%m', EMISchedule.due_date) == m_str).all()
        sched_total = sum(float(s.scheduled_emi or 0.0) for s in scheds)
        act_total = sum(float(s.actual_deduction or 0.0) for s in scheds)

        scheduled_values.append(round(sched_total, 2))
        recovery_values.append(round(act_total, 2))

    return jsonify({
        'dept_labels': dept_labels,
        'dept_values': dept_values,
        'status_labels': ['Pending Approval', 'Active Loans', 'Closed', 'Rejected'],
        'status_values': [pending_cnt, active_cnt, closed_cnt, rejected_cnt],
        'monthly_labels': months_labels,
        'scheduled_monthly': scheduled_values,
        'recovered_monthly': recovery_values
    })
