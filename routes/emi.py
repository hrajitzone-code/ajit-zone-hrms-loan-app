from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, g
from models import db, Loan, Employee, EMISchedule, EMIDeduction, EMIAdjustment, AuditLog
from routes.auth import login_required, role_required, permission_required
from utils.automation import run_daily_loan_automation
from datetime import datetime, date

emi_bp = Blueprint('emi', __name__)

@emi_bp.route('/emi/management')
@login_required
@permission_required('emi', 'view')
def management():
    status_filter = request.args.get('status', '').strip()
    month_filter = request.args.get('month', '').strip() # YYYY-MM
    search_q = request.args.get('q', '').strip()

    run_daily_loan_automation(system_user_id=g.user.id if g.user else 1)

    query = EMISchedule.query.join(Loan).join(Employee)

    # Scope: If user only has view_own, restrict to own loans
    if not g.user.can_view_all('emi'):
        if g.user.employee_id:
            query = query.filter(Loan.employee_id == g.user.employee_id)
        else:
            query = query.filter(EMISchedule.id == -1)

    if status_filter:
        query = query.filter(EMISchedule.status == status_filter)

    if month_filter:
        query = query.filter(db.func.strftime('%Y-%m', EMISchedule.due_date) == month_filter)

    if search_q:
        query = query.filter(
            (Loan.loan_id.ilike(f'%{search_q}%')) |
            (Employee.name.ilike(f'%{search_q}%')) |
            (Employee.emp_id.ilike(f'%{search_q}%'))
        )

    schedules = query.order_by(EMISchedule.due_date.asc()).all()
    today = date.today()

    return render_template('emi/management.html', schedules=schedules, selected_status=status_filter, selected_month=month_filter, search_q=search_q, today=today)

@emi_bp.route('/emi/deduct/<int:schedule_id>', methods=['POST'])
@login_required
@permission_required('emi', 'add')
def record_deduction(schedule_id):
    schedule_item = EMISchedule.query.get_or_404(schedule_id)
    loan = schedule_item.loan

    amount_deducted = request.form.get('amount_deducted', 0.0, type=float)
    deduction_date_str = request.form.get('deduction_date', '').strip()
    payment_mode = request.form.get('payment_mode', 'Payroll Deduction').strip()
    transaction_ref = request.form.get('transaction_ref', '').strip()
    remarks = request.form.get('remarks', '').strip()

    ded_date = datetime.strptime(deduction_date_str, '%Y-%m-%d').date() if deduction_date_str else date.today()

    if amount_deducted < 0:
        flash("Deduction amount cannot be negative.", 'danger')
        return redirect(url_for('emi.management'))

    schedule_item.actual_deduction = round(amount_deducted, 2)
    schedule_item.actual_deduction_date = ded_date
    schedule_item.remarks = remarks

    # Status Determination
    if amount_deducted >= schedule_item.scheduled_emi:
        schedule_item.status = 'Deducted'
    elif amount_deducted > 0:
        schedule_item.status = 'Partial'
    else:
        schedule_item.status = 'Pending'

    deduction_record = EMIDeduction(
        loan_id=loan.id,
        emi_schedule_id=schedule_item.id,
        deduction_date=ded_date,
        amount_deducted=amount_deducted,
        payment_mode=payment_mode,
        transaction_ref=transaction_ref,
        recorded_by_id=g.user.id,
        remarks=remarks
    )
    db.session.add(deduction_record)

    # Recalculate Loan Totals
    total_recovered = sum(s.actual_deduction for s in loan.schedules)
    loan.total_recovered = round(total_recovered, 2)
    loan.outstanding_balance = max(0.0, round(loan.loan_amount - total_recovered, 2))

    audit = AuditLog(
        user_id=g.user.id,
        user_name=g.user.full_name,
        role=g.user.role,
        action='UPDATE',
        module='EMI',
        record_id=f"{loan.loan_id}-EMI#{schedule_item.emi_no}",
        new_value=f"Recorded deduction ₹{amount_deducted:,.2f} for EMI #{schedule_item.emi_no} (Status: {schedule_item.status})",
        reason=remarks or "Monthly EMI Deduction"
    )
    db.session.add(audit)
    db.session.commit()

    # Trigger automation check (auto-closure if balance = 0)
    run_daily_loan_automation(system_user_id=g.user.id)

    flash(f"EMI Deduction of ₹{amount_deducted:,.2f} recorded for {loan.employee.name} (Status: {schedule_item.status})!", 'success')
    return redirect(url_for('emi.management'))

@emi_bp.route('/emi/adjustments', methods=['GET', 'POST'])
@login_required
@permission_required('adjustments', 'view')
def adjustments():
    if request.method == 'POST':
        if not (g.user.is_superadmin() or g.user.has_permission('adjustments', 'add')):
            flash('Access Denied: You do not have permission to submit EMI adjustments.', 'danger')
            return redirect(url_for('emi.adjustments'))

        loan_id_pk = request.form.get('loan_id', type=int)
        schedule_id_pk = request.form.get('schedule_id', type=int)
        adj_type = request.form.get('adjustment_type', '').strip()
        amount = request.form.get('amount', 0.0, type=float)
        reason = request.form.get('reason', '').strip()

        loan = Loan.query.get_or_404(loan_id_pk)
        
        # Scoping check: If user cannot view all adjustments, they may only request for their own loan
        if not g.user.can_view_all('adjustments') and g.user.employee_id:
            if loan.employee_id != g.user.employee_id:
                flash('Access Denied: You may only request adjustments for your own loan.', 'danger')
                return redirect(url_for('emi.adjustments'))
        
        adj = EMIAdjustment(
            loan_id=loan.id,
            emi_schedule_id=schedule_id_pk if schedule_id_pk else None,
            adjustment_type=adj_type,
            amount=amount,
            reason=reason,
            requested_by_id=g.user.id,
            approval_status='Pending'
        )
        db.session.add(adj)

        audit = AuditLog(
            user_id=g.user.id,
            user_name=g.user.full_name,
            role=g.user.role,
            action='CREATE',
            module='EMI',
            record_id=loan.loan_id,
            new_value=f"Submitted adjustment request ({adj_type}: ₹{amount:,.2f}) for Loan {loan.loan_id}",
            reason=reason
        )
        db.session.add(audit)
        db.session.commit()

        flash("EMI Adjustment request submitted and pending approval!", 'info')
        return redirect(url_for('emi.adjustments'))

    adj_query = EMIAdjustment.query.join(Loan)
    loans_query = Loan.query.filter_by(loan_status='Active')

    if not g.user.can_view_all('adjustments'):
        if g.user.employee_id:
            adj_query = adj_query.filter(Loan.employee_id == g.user.employee_id)
            loans_query = loans_query.filter(Loan.employee_id == g.user.employee_id)
        else:
            adj_query = adj_query.filter(EMIAdjustment.id == -1)
            loans_query = loans_query.filter(Loan.id == -1)

    adjustments_list = adj_query.order_by(EMIAdjustment.created_at.desc()).all()
    active_loans = loans_query.all()

    return render_template('emi/adjustments.html', adjustments=adjustments_list, loans=active_loans)

@emi_bp.route('/emi/adjustments/<int:adj_id>/action', methods=['POST'])
@login_required
@permission_required('adjustments', 'approve')
def approve_adjustment(adj_id):
    adj = EMIAdjustment.query.get_or_404(adj_id)
    action = request.form.get('action', 'approve')

    if action == 'approve':
        adj.approval_status = 'Approved'
        adj.approved_by_id = g.user.id

        loan = adj.loan
        if adj.adjustment_type == 'Add_To_Next_Month' and adj.emi_schedule_id:
            curr_sch = EMISchedule.query.get(adj.emi_schedule_id)
            next_sch = EMISchedule.query.filter(
                EMISchedule.loan_id == loan.id,
                EMISchedule.emi_no > curr_sch.emi_no
            ).order_by(EMISchedule.emi_no.asc()).first()

            if next_sch:
                adj.old_emi_amount = next_sch.scheduled_emi
                next_sch.scheduled_emi = round(next_sch.scheduled_emi + adj.amount, 2)
                adj.new_emi_amount = next_sch.scheduled_emi
                curr_sch.status = 'Adjusted'

        elif adj.adjustment_type == 'Extend_Tenure':
            last_sch = EMISchedule.query.filter_by(loan_id=loan.id).order_by(EMISchedule.emi_no.desc()).first()
            new_emi_no = (last_sch.emi_no + 1) if last_sch else 1
            
            from utils.emi_calculator import add_months
            new_due_date = add_months(last_sch.due_date, 1, target_day=loan.emi_deduction_day) if last_sch else date.today()

            new_sch = EMISchedule(
                loan_id=loan.id,
                emi_no=new_emi_no,
                due_date=new_due_date,
                scheduled_emi=adj.amount,
                actual_deduction=0.0,
                outstanding_after=0.0,
                status='Upcoming'
            )
            db.session.add(new_sch)
            loan.tenure_months += 1
            loan.tenure_to = new_due_date

        audit = AuditLog(
            user_id=g.user.id,
            user_name=g.user.full_name,
            role=g.user.role,
            action='APPROVE',
            module='EMI',
            record_id=loan.loan_id,
            new_value=f"Approved adjustment {adj.adjustment_type} of ₹{adj.amount:,.2f} for Loan {loan.loan_id}",
            reason=adj.reason
        )
        db.session.add(audit)
        db.session.commit()

        flash("Adjustment approved and EMI schedule updated!", 'success')
    else:
        adj.approval_status = 'Rejected'
        adj.approved_by_id = g.user.id
        db.session.commit()
        flash("Adjustment request rejected.", 'info')

    return redirect(url_for('emi.adjustments'))
