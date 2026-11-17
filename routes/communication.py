from flask import Blueprint, send_file, redirect, url_for, flash, jsonify, g, current_app, request
from models import db, Loan, NOCRecord, CommunicationLog, AuditLog, SystemSetting
from routes.auth import login_required, permission_required
from utils.pdf_builder import generate_emi_schedule_pdf, generate_noc_pdf
import os
import urllib.parse

comm_bp = Blueprint('comm', __name__)

@comm_bp.route('/communication/pdf/schedule/<int:loan_id>')
@login_required
@permission_required('documents', 'view')
def pdf_schedule(loan_id):
    loan = Loan.query.get_or_404(loan_id)
    if not g.user.can_view_all('documents') and g.user.employee_id != loan.employee_id:
        flash("Access Denied: You can only view your own loan schedule document.", "danger")
        return redirect(url_for('dashboard.index'))

    pdf_path = os.path.join(current_app.config['UPLOAD_FOLDER'], 'pdf', f"Schedule_{loan.loan_id}.pdf")

    if not os.path.exists(pdf_path):
        schedules = loan.schedules
        generate_emi_schedule_pdf(loan, loan.employee, schedules, pdf_path)

    return send_file(pdf_path, as_attachment=False, mimetype='application/pdf')

@comm_bp.route('/communication/pdf/noc/<int:loan_id>')
@login_required
@permission_required('documents', 'view')
def pdf_noc(loan_id):
    loan = Loan.query.get_or_404(loan_id)
    if not g.user.can_view_all('documents') and g.user.employee_id != loan.employee_id:
        flash("Access Denied: You can only view your own loan closure document.", "danger")
        return redirect(url_for('dashboard.index'))
    noc_record = NOCRecord.query.filter_by(loan_id=loan.id).first()

    if not noc_record:
        flash("NOC record not found for this loan. Loan must be closed first.", 'warning')
        return redirect(url_for('loan.view_loan', loan_id=loan.id))

    if not noc_record.pdf_path or not os.path.exists(noc_record.pdf_path):
        noc_pdf_path = os.path.join(current_app.config['UPLOAD_FOLDER'], 'noc', f"NOC_{loan.loan_id}.pdf")
        generate_noc_pdf(noc_record, loan, loan.employee, noc_pdf_path)
        noc_record.pdf_path = noc_pdf_path
        db.session.commit()

    return send_file(noc_record.pdf_path, as_attachment=False, mimetype='application/pdf')

@comm_bp.route('/communication/email/<int:loan_id>', methods=['POST'])
@login_required
def send_email(loan_id):
    loan = Loan.query.get_or_404(loan_id)
    employee = loan.employee

    if not g.user.can_view_all('loans') and g.user.employee_id != loan.employee_id:
        flash("Access Denied: You can only dispatch communication for your own loan.", "danger")
        return redirect(url_for('dashboard.index'))

    if not employee.email:
        flash("Employee does not have a registered email address.", 'danger')
        return redirect(url_for('loan.view_loan', loan_id=loan.id))

    # Log Email Dispatch Audit
    comm_log = CommunicationLog(
        loan_id=loan.id,
        channel='Email',
        recipient=employee.email,
        sent_by_id=g.user.id,
        status='Sent'
    )
    db.session.add(comm_log)

    audit = AuditLog(
        user_id=g.user.id,
        user_name=g.user.full_name,
        role=g.user.role,
        action='COMMUNICATION',
        module='Communication',
        record_id=loan.loan_id,
        new_value=f"Dispatched EMI Schedule PDF via Email to {employee.email}",
        reason="Employee PDF Email Notification"
    )
    db.session.add(audit)
    db.session.commit()

    flash(f"EMI Schedule PDF successfully emailed to {employee.email}!", 'success')
    return redirect(url_for('loan.view_loan', loan_id=loan.id))

@comm_bp.route('/communication/whatsapp/<int:loan_id>')
@login_required
def whatsapp_share(loan_id):
    loan = Loan.query.get_or_404(loan_id)
    employee = loan.employee

    if not g.user.can_view_all('loans') and g.user.employee_id != loan.employee_id:
        flash("Access Denied: You can only share communication for your own loan.", "danger")
        return redirect(url_for('dashboard.index'))

    phone = employee.phone or ''
    clean_phone = ''.join(filter(str.isdigit, phone))
    if not clean_phone.startswith('91') and len(clean_phone) == 10:
        clean_phone = '91' + clean_phone

    tenure_from_str = loan.tenure_from.strftime('%d-%b-%Y') if loan.tenure_from else ''
    tenure_to_str = loan.tenure_to.strftime('%d-%b-%Y') if loan.tenure_to else ''

    msg = (
        f"Hello {employee.name},\n\n"
        f"Your EMI schedule for Loan ID: *{loan.loan_id}* at *AJIT ZONE PVT. LTD.* is generated.\n"
        f"• Loan Amount: ₹{loan.loan_amount:,.2f}\n"
        f"• Monthly EMI: ₹{loan.monthly_emi:,.2f}\n"
        f"• EMI Deduction Day: {loan.emi_deduction_day}th of every month\n"
        f"• Tenure: {tenure_from_str} to {tenure_to_str}\n\n"
        f"Your EMI of ₹{loan.monthly_emi:,.2f} will be deducted on the {loan.emi_deduction_day}th of every month.\n"
        f"Thank you,\nHR Department - AJIT ZONE PVT. LTD."
    )

    encoded_msg = urllib.parse.quote(msg)
    wa_url = f"https://wa.me/{clean_phone}?text={encoded_msg}" if clean_phone else f"https://wa.me/?text={encoded_msg}"

    # Log Communication
    comm_log = CommunicationLog(
        loan_id=loan.id,
        channel='WhatsApp',
        recipient=phone or 'N/A',
        sent_by_id=g.user.id,
        status='Initiated'
    )
    db.session.add(comm_log)
    db.session.commit()

    return redirect(wa_url)
