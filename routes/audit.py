from flask import Blueprint, render_template, request
from models import db, AuditLog
from routes.auth import login_required, permission_required

audit_bp = Blueprint('audit', __name__)

@audit_bp.route('/audit-logs')
@login_required
@permission_required('audit_logs', 'view_all')
def index():
    module_filter = request.args.get('module', '').strip()
    search_q = request.args.get('q', '').strip()
    page = request.args.get('page', 1, type=int)

    query = AuditLog.query

    if module_filter:
        query = query.filter(AuditLog.module == module_filter)

    if search_q:
        query = query.filter(
            (AuditLog.user_name.ilike(f'%{search_q}%')) |
            (AuditLog.action.ilike(f'%{search_q}%')) |
            (AuditLog.record_id.ilike(f'%{search_q}%')) |
            (AuditLog.new_value.ilike(f'%{search_q}%'))
        )

    pagination = query.order_by(AuditLog.timestamp.desc()).paginate(page=page, per_page=20, error_out=False)
    logs = pagination.items

    modules = db.session.query(AuditLog.module).distinct().all()
    modules = [m[0] for m in modules if m[0]]

    return render_template('audit/index.html', logs=logs, pagination=pagination, modules=modules, selected_module=module_filter, search_q=search_q)
