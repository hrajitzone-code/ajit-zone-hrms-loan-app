from flask import Blueprint, render_template, request, redirect, url_for, flash, g
from models import db, SystemSetting, AuditLog
from routes.auth import login_required, permission_required
import json

settings_bp = Blueprint('settings', __name__)

DEFAULT_SETTINGS = {
    'company_name': 'AJIT ZONE PVT. LTD.',
    'company_address': 'Corporate Tower, Main Road, City',
    'company_phone': '+91 98765 43210',
    'company_email': 'hr@ajitzone.com',
    'default_deduction_day': '5',
    'min_salary': '20000',
    'min_service_period_months': '6',
    'max_loan_limit': '500000',
    'max_tenure_months': '36',
    'max_salary_emi_ratio': '0.50',
    'default_interest_rate': '8.5',
    'processing_fee_percent': '1.0',
    'loan_types_json': '["Personal Loan", "Emergency Advance", "Salary Advance", "Medical Loan", "Home Loan"]',
    'approval_rules_json': '{"auto_approve_below": 25000, "manager_approval_above": 100000}',
    'email_smtp_server': 'smtp.gmail.com',
    'email_smtp_port': '587',
    'whatsapp_api_gateway': 'https://api.whatsapp.com/send',
    'whatsapp_api_key': ''
}

@settings_bp.route('/settings', methods=['GET', 'POST'])
@login_required
@permission_required('settings', 'view')
def index():
    if request.method == 'POST':
        if not (g.user.is_superadmin() or g.user.has_permission('settings', 'manage')):
            flash('Access Denied: You do not have permission to manage system settings.', 'danger')
            return redirect(url_for('settings.index'))
        for key in DEFAULT_SETTINGS.keys():
            val = request.form.get(key, '').strip()
            setting = SystemSetting.query.filter_by(key=key).first()
            if setting:
                setting.value = val
            else:
                setting = SystemSetting(key=key, value=val)
                db.session.add(setting)

        audit = AuditLog(
            user_id=g.user.id,
            user_name=g.user.full_name,
            role=g.user.role,
            action='UPDATE',
            module='Settings',
            record_id='SystemConfig',
            new_value="Updated Dynamic System Business Rules & Loan Criteria",
            reason="Admin Settings Configuration Update"
        )
        db.session.add(audit)
        db.session.commit()

        flash("System business rules and settings updated successfully!", 'success')
        return redirect(url_for('settings.index'))

    settings_objs = SystemSetting.query.all()
    settings_dict = {s.key: s.value for s in settings_objs}

    for k, default_v in DEFAULT_SETTINGS.items():
        if k not in settings_dict:
            settings_dict[k] = default_v

    loan_types_list = []
    try:
        loan_types_list = json.loads(settings_dict.get('loan_types_json', '[]'))
    except Exception:
        loan_types_list = ["Personal Loan", "Emergency Advance", "Salary Advance", "Medical Loan", "Home Loan"]

    return render_template('settings/index.html', settings=settings_dict, loan_types_list=loan_types_list)

def get_system_setting(key, default_val=None):
    setting = SystemSetting.query.filter_by(key=key).first()
    if setting and setting.value is not None:
        return setting.value
    return DEFAULT_SETTINGS.get(key, default_val)
