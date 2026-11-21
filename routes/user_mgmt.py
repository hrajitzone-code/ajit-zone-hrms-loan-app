from flask import Blueprint, render_template, request, redirect, url_for, flash, g, jsonify
from models import db, User, Employee, AuditLog
from routes.auth import login_required, superadmin_required
from utils.permissions import MODULES_DEF, ACTIONS_META, get_default_role_permissions
from utils.blob_db import sync_to_blob, sync_from_blob, is_vercel
from datetime import datetime
import json

user_mgmt_bp = Blueprint('user_mgmt', __name__)

ROLES_LIST = [
    'Super_Admin',
    'HR_Manager',
    'HR',
    'Finance_Payroll',
    'Manager',
    'Employee',
    'Viewer'
]

@user_mgmt_bp.route('/users')
@login_required
@superadmin_required
def index():
    """
    Main User Management & RBAC Console (Super Admin Sakshi Shukla only).
    Provides:
    1. Users Directory & Account Management
    2. Interactive Module Permission Matrix
    3. User Activity & Login Audit Trail
    """
    search_q = request.args.get('q', '').strip()
    role_filter = request.args.get('role', '').strip()
    active_tab = request.args.get('tab', 'users').strip()
    selected_user_id = request.args.get('selected_user', type=int)

    if is_vercel():
        sync_from_blob(force=True)
    db.session.expire_all()

    query = User.query

    if search_q:
        query = query.filter(
            (User.username.ilike(f'%{search_q}%')) |
            (User.full_name.ilike(f'%{search_q}%')) |
            (User.email.ilike(f'%{search_q}%'))
        )

    if role_filter:
        query = query.filter(User.role == role_filter)

    users = query.order_by(User.created_at.desc()).all()
    employees = Employee.query.order_by(Employee.name.asc()).all()

    # Query latest user & auth activity logs for the Activity Tab
    activity_logs = AuditLog.query.filter(
        AuditLog.module.in_(['Auth', 'Users', 'Security'])
    ).order_by(AuditLog.timestamp.desc()).limit(150).all()

    # Pre-parse each user's permissions for the Matrix Table
    user_perms_map = {}
    for u in users:
        user_perms_map[u.id] = u.get_permissions()

    return render_template(
        'users/index.html',
        users=users,
        employees=employees,
        roles=ROLES_LIST,
        search_q=search_q,
        selected_role=role_filter,
        active_tab=active_tab,
        selected_user_id=selected_user_id,
        activity_logs=activity_logs,
        modules_def=MODULES_DEF,
        actions_meta=ACTIONS_META,
        user_perms_map=user_perms_map
    )

@user_mgmt_bp.route('/users/create', methods=['POST'])
@login_required
@superadmin_required
def create_user():
    """Create unique User ID, credentials, and role."""
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '')
    full_name = request.form.get('full_name', '').strip()
    email = request.form.get('email', '').strip()
    role = request.form.get('role', 'HR').strip()
    emp_id_pk = request.form.get('employee_id', type=int)

    if not username or not password or not full_name:
        flash('Username, password, and full name are required to create a user account.', 'danger')
        return redirect(url_for('user_mgmt.index', tab='users'))

    existing = User.query.filter_by(username=username).first()
    if existing:
        flash(f"User ID / Username '{username}' already exists! Please choose a unique User ID.", 'danger')
        return redirect(url_for('user_mgmt.index', tab='users'))

    # Security check: Only primary super admin (Sakshi Shukla) can assign Super_Admin role
    if role == 'Super_Admin' and not (g.user.is_primary_superadmin or g.user.username == 'sakshi'):
        flash('Only Primary Super Admin (Sakshi Shukla) has authority to create Super Admin accounts.', 'danger')
        return redirect(url_for('user_mgmt.index', tab='users'))

    user = User(
        username=username,
        full_name=full_name,
        email=email,
        role=role,
        employee_id=emp_id_pk if emp_id_pk else None,
        is_active=True,
        is_primary_superadmin=False
    )
    user.set_password(password)
    db.session.add(user)

    audit = AuditLog(
        user_id=g.user.id,
        user_name=g.user.full_name,
        role=g.user.role,
        action='CREATE',
        module='Users',
        record_id=username,
        new_value=f"Created User ID '{username}', Full Name: '{full_name}', Role: '{role}', Linked Emp ID: {emp_id_pk}",
        reason="Super Admin User Creation",
        ip_address=request.remote_addr
    )
    db.session.add(audit)
    db.session.commit()
    if is_vercel():
        sync_to_blob()

    flash(f"User account '{username}' ({full_name}) created successfully with role '{role}'!", 'success')
    return redirect(url_for('user_mgmt.index', tab='users'))

@user_mgmt_bp.route('/users/<int:user_id>/edit', methods=['POST'])
@login_required
@superadmin_required
def edit_user(user_id):
    """Edit user details, role assignment, and employee master link."""
    if is_vercel():
        sync_from_blob(force=True)
    db.session.expire_all()
    target_user = User.query.get(user_id)
    if not target_user and is_vercel():
        sync_from_blob(force=True)
        target_user = User.query.get(user_id)
    if not target_user:
        flash(f"User account #{user_id} was not found.", 'warning')
        return redirect(url_for('user_mgmt.index', tab='users'))
    new_role = request.form.get('role', target_user.role).strip()
    full_name = request.form.get('full_name', target_user.full_name).strip()
    email = request.form.get('email', target_user.email).strip()
    emp_id_pk = request.form.get('employee_id', type=int)

    # Protect Primary Super Admin (Sakshi Shukla)
    if target_user.is_primary_superadmin or target_user.username == 'sakshi':
        if new_role != 'Super_Admin':
            flash('Protected Account: Primary Super Admin (Sakshi Shukla) cannot have their Super Admin role changed or demoted.', 'danger')
            return redirect(url_for('user_mgmt.index', tab='users'))

    # Security check: Only primary super admin (Sakshi Shukla) can assign Super_Admin role
    if new_role == 'Super_Admin' and not (g.user.is_primary_superadmin or g.user.username == 'sakshi'):
        flash('Only Primary Super Admin (Sakshi Shukla) has authority to assign the Super Admin role.', 'danger')
        return redirect(url_for('user_mgmt.index', tab='users'))

    old_role = target_user.role
    target_user.full_name = full_name
    target_user.email = email
    target_user.role = new_role
    target_user.employee_id = emp_id_pk if emp_id_pk else None

    audit = AuditLog(
        user_id=g.user.id,
        user_name=g.user.full_name,
        role=g.user.role,
        action='UPDATE',
        module='Users',
        record_id=target_user.username,
        old_value=f"Role: {old_role}",
        new_value=f"Role: {new_role}, Name: {full_name}, Linked Emp ID: {emp_id_pk}",
        reason="Super Admin User Details Edit",
        ip_address=request.remote_addr
    )
    db.session.add(audit)
    db.session.commit()
    if is_vercel():
        sync_to_blob()

    flash(f"User '{target_user.username}' updated successfully!", 'success')
    return redirect(url_for('user_mgmt.index', tab='users'))

@user_mgmt_bp.route('/users/<int:user_id>/reset-password', methods=['POST'])
@login_required
@superadmin_required
def reset_password(user_id):
    """Reset user password directly from Super Admin console."""
    if is_vercel():
        sync_from_blob(force=True)
    db.session.expire_all()
    target_user = User.query.get(user_id)
    if not target_user and is_vercel():
        sync_from_blob(force=True)
        target_user = User.query.get(user_id)
    if not target_user:
        flash(f"User account #{user_id} was not found.", 'warning')
        return redirect(url_for('user_mgmt.index', tab='users'))
    new_password = request.form.get('new_password', '')

    if not new_password:
        flash('New password cannot be empty.', 'danger')
        return redirect(url_for('user_mgmt.index', tab='users'))

    target_user.set_password(new_password)

    audit = AuditLog(
        user_id=g.user.id,
        user_name=g.user.full_name,
        role=g.user.role,
        action='PASSWORD_RESET',
        module='Users',
        record_id=target_user.username,
        new_value=f"Reset password for user '{target_user.username}'",
        reason="Super Admin Manual Password Reset",
        ip_address=request.remote_addr
    )
    db.session.add(audit)
    db.session.commit()
    if is_vercel():
        sync_to_blob()

    flash(f"Password for user '{target_user.username}' has been reset successfully!", 'success')
    return redirect(url_for('user_mgmt.index', tab='users'))

@user_mgmt_bp.route('/users/<int:user_id>/toggle-status', methods=['POST'])
@login_required
@superadmin_required
def toggle_status(user_id):
    """Activate or deactivate user account."""
    if is_vercel():
        sync_from_blob(force=True)
    db.session.expire_all()
    target_user = User.query.get(user_id)
    if not target_user and is_vercel():
        sync_from_blob(force=True)
        target_user = User.query.get(user_id)
    if not target_user:
        flash(f"User account #{user_id} was not found.", 'warning')
        return redirect(url_for('user_mgmt.index', tab='users'))

    # Protect Primary Super Admin (Sakshi Shukla) from deactivation
    if target_user.is_primary_superadmin or target_user.username == 'sakshi':
        flash('Security Lock: Primary Super Admin (Sakshi Shukla) cannot be deactivated.', 'danger')
        return redirect(url_for('user_mgmt.index', tab='users'))

    if target_user.id == g.user.id:
        flash('You cannot deactivate your own logged-in account.', 'warning')
        return redirect(url_for('user_mgmt.index', tab='users'))

    target_user.is_active = not target_user.is_active

    audit = AuditLog(
        user_id=g.user.id,
        user_name=g.user.full_name,
        role=g.user.role,
        action='STATUS_TOGGLE',
        module='Users',
        record_id=target_user.username,
        new_value=f"is_active={target_user.is_active}",
        reason="Super Admin Account Status Toggle",
        ip_address=request.remote_addr
    )
    db.session.add(audit)
    db.session.commit()
    if is_vercel():
        sync_to_blob()

    status_str = "Activated" if target_user.is_active else "Deactivated"
    flash(f"User account '{target_user.username}' has been {status_str}!", 'info')
    return redirect(url_for('user_mgmt.index', tab='users'))

@user_mgmt_bp.route('/users/<int:user_id>/delete', methods=['POST'])
@user_mgmt_bp.route('/users/delete', methods=['POST'])
@login_required
@superadmin_required
def delete_user(user_id=None):
    """Safely delete a user account with Super Admin protection."""
    if is_vercel():
        sync_from_blob(force=True)
    db.session.expire_all()

    if not user_id:
        user_id = request.form.get('user_id', type=int) or request.args.get('user_id', type=int)

    if not user_id:
        flash('No user account specified for deletion.', 'warning')
        return redirect(url_for('user_mgmt.index', tab='users'))

    target_user = User.query.get(user_id)
    if not target_user and is_vercel():
        sync_from_blob(force=True)
        target_user = User.query.get(user_id)

    if not target_user:
        flash(f"User account #{user_id} was not found or has already been deleted.", 'warning')
        return redirect(url_for('user_mgmt.index', tab='users'))

    # Strictly protect Primary Super Admin (Sakshi Shukla)
    if target_user.is_primary_superadmin or target_user.username == 'sakshi':
        flash('Security Protection: Primary Super Admin (Sakshi Shukla) cannot be deleted under any circumstances.', 'danger')
        return redirect(url_for('user_mgmt.index', tab='users'))

    if target_user.id == g.user.id:
        flash('You cannot delete your own currently logged-in account.', 'warning')
        return redirect(url_for('user_mgmt.index', tab='users'))

    username = target_user.username
    full_name = target_user.full_name
    role = target_user.role

    # Unlink employee if linked
    target_user.employee_id = None
    db.session.delete(target_user)

    audit = AuditLog(
        user_id=g.user.id,
        user_name=g.user.full_name,
        role=g.user.role,
        action='DELETE',
        module='Users',
        record_id=username,
        old_value=f"Username: {username}, Name: {full_name}, Role: {role}",
        new_value="DELETED",
        reason="Super Admin User Deletion",
        ip_address=request.remote_addr
    )
    db.session.add(audit)
    db.session.commit()
    if is_vercel():
        sync_to_blob()

    flash(f"User account '{username}' ({full_name}) has been permanently deleted.", 'success')
    return redirect(url_for('user_mgmt.index', tab='users'))

@user_mgmt_bp.route('/users/<int:user_id>/permissions', methods=['GET', 'POST'])
@user_mgmt_bp.route('/users/permissions', methods=['GET', 'POST'])
@user_mgmt_bp.route('/users/<int:user_id>/custom-metric', methods=['GET', 'POST'])
@user_mgmt_bp.route('/users/custom-metric', methods=['GET', 'POST'])
@user_mgmt_bp.route('/custom-metric', methods=['GET', 'POST'])
@login_required
@superadmin_required
def update_permissions(user_id=None):
    """
    Save custom module-wise permissions matrix / metric for an individual user.
    Supports both standard form submission and AJAX JSON payload.
    """
    if is_vercel():
        sync_from_blob(force=True)
    db.session.remove()
    db.session.expire_all()

    # Resolve target user_id from path param, form data, JSON body, or query args
    if not user_id:
        user_id = request.form.get('user_id', type=int) or request.args.get('user_id', type=int) or request.args.get('selected_user', type=int)
        if not user_id and request.is_json:
            data = request.get_json(silent=True) or {}
            user_id = data.get('user_id')

    if not user_id:
        if request.method == 'GET':
            return redirect(url_for('user_mgmt.index', tab='matrix'))
        if request.is_json:
            return jsonify({'success': False, 'message': 'No target user account specified.'}), 400
        flash('Please select a user account to configure custom permissions.', 'warning')
        return redirect(url_for('user_mgmt.index', tab='matrix'))

    # If GET request, safely redirect to the Matrix tab for this user instead of 404/405
    if request.method == 'GET':
        return redirect(url_for('user_mgmt.index', tab='matrix', selected_user=user_id))

    target_user = User.query.get(user_id)
    if not target_user and is_vercel():
        sync_from_blob(force=True)
        target_user = User.query.get(user_id)

    if not target_user:
        if request.is_json:
            return jsonify({'success': False, 'message': f'User account #{user_id} was not found.'}), 404
        flash(f"User account #{user_id} was not found. Please choose an active user account.", 'warning')
        return redirect(url_for('user_mgmt.index', tab='users'))

    # If primary superadmin, inform that they automatically retain 100% full access
    if target_user.is_primary_superadmin or target_user.username == 'sakshi':
        if request.is_json:
            return jsonify({'success': True, 'message': 'Primary Super Admin (Sakshi Shukla) automatically has full access to all modules.'})
        flash('Primary Super Admin (Sakshi Shukla) has full access across all modules by default.', 'info')
        return redirect(url_for('user_mgmt.index', tab='matrix', selected_user=target_user.id))

    custom_perms = {}

    if request.is_json:
        data = request.get_json(silent=True) or {}
        custom_perms = data.get('permissions', {})
    else:
        # Standard form post from matrix checkboxes
        for m in MODULES_DEF:
            mod_id = m['id']
            # Get list of checked actions for this module: form fields named perm_{mod_id}
            selected_actions = request.form.getlist(f"perm_{mod_id}")
            if selected_actions:
                custom_perms[mod_id] = selected_actions

    target_user.permissions = json.dumps(custom_perms)

    audit = AuditLog(
        user_id=g.user.id,
        user_name=g.user.full_name,
        role=g.user.role,
        action='UPDATE_PERMISSIONS',
        module='Users',
        record_id=target_user.username,
        new_value=json.dumps(custom_perms),
        reason="Super Admin Custom RBAC Permissions Matrix Configuration",
        ip_address=request.remote_addr
    )
    db.session.add(audit)
    db.session.commit()
    if is_vercel():
        sync_to_blob()

    if request.is_json:
        return jsonify({
            'success': True,
            'message': f"Custom metric & permissions matrix for user '{target_user.username}' saved successfully!",
            'permissions': custom_perms
        })

    flash(f"Custom metric & permissions for '{target_user.username}' saved successfully!", 'success')
    tab = request.form.get('active_tab', 'users')
    return redirect(url_for('user_mgmt.index', tab=tab, selected_user=target_user.id))

@user_mgmt_bp.route('/users/<int:user_id>/reset-permissions', methods=['GET', 'POST'])
@user_mgmt_bp.route('/users/reset-permissions', methods=['GET', 'POST'])
@login_required
@superadmin_required
def reset_permissions_to_default(user_id=None):
    """Reset custom permissions back to standard role defaults."""
    if is_vercel():
        sync_from_blob(force=True)
    db.session.remove()
    db.session.expire_all()

    if not user_id:
        user_id = request.form.get('user_id', type=int) or request.args.get('user_id', type=int) or request.args.get('selected_user', type=int)

    if not user_id:
        if request.method == 'GET':
            return redirect(url_for('user_mgmt.index', tab='matrix'))
        if request.is_json:
            return jsonify({'success': False, 'message': 'No target user account specified.'}), 400
        flash('Please select a user account to reset permissions.', 'warning')
        return redirect(url_for('user_mgmt.index', tab='matrix'))

    if request.method == 'GET':
        return redirect(url_for('user_mgmt.index', tab='matrix', selected_user=user_id))

    target_user = User.query.get(user_id)
    if not target_user and is_vercel():
        sync_from_blob(force=True)
        target_user = User.query.get(user_id)

    if not target_user:
        if request.is_json:
            return jsonify({'success': False, 'message': f'User account #{user_id} was not found.'}), 404
        flash(f"User account #{user_id} was not found.", 'warning')
        return redirect(url_for('user_mgmt.index', tab='users'))

    target_user.permissions = None

    audit = AuditLog(
        user_id=g.user.id,
        user_name=g.user.full_name,
        role=g.user.role,
        action='RESET_PERMISSIONS',
        module='Users',
        record_id=target_user.username,
        new_value=f"Reset to default role permissions for '{target_user.role}'",
        reason="Super Admin Reset to Role Defaults",
        ip_address=request.remote_addr
    )
    db.session.add(audit)
    db.session.commit()
    if is_vercel():
        sync_to_blob()

    if request.is_json:
        return jsonify({
            'success': True,
            'message': f"Custom metric & permissions for '{target_user.username}' reset to standard '{target_user.role}' defaults."
        })

    flash(f"Permissions for '{target_user.username}' reset to standard '{target_user.role}' defaults.", 'info')
    tab = request.form.get('active_tab', 'users')
    return redirect(url_for('user_mgmt.index', tab=tab, selected_user=target_user.id))

@user_mgmt_bp.route('/users/<int:user_id>/permissions/json')
@user_mgmt_bp.route('/users/permissions/json')
@login_required
@superadmin_required
def get_user_permissions(user_id=None):
    """API endpoint to fetch a user's current permissions JSON for dynamic UI modal loading."""
    if is_vercel():
        sync_from_blob(force=True)
    db.session.remove()
    db.session.expire_all()

    if not user_id:
        user_id = request.args.get('user_id', type=int) or request.args.get('selected_user', type=int)

    if not user_id:
        return jsonify({'status': 'error', 'message': 'User ID required'}), 400

    target_user = User.query.get(user_id)
    if not target_user and is_vercel():
        sync_from_blob(force=True)
        target_user = User.query.get(user_id)

    if not target_user:
        return jsonify({'status': 'error', 'message': 'User not found'}), 404

    resp = jsonify({
        'status': 'success',
        'user_id': target_user.id,
        'username': target_user.username,
        'full_name': target_user.full_name,
        'role': target_user.role,
        'is_superadmin': target_user.is_superadmin(),
        'is_primary_superadmin': target_user.is_primary_superadmin or target_user.username == 'sakshi',
        'has_custom_permissions': target_user.permissions is not None,
        'permissions': target_user.get_permissions()
    })
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate, max-age=0'
    resp.headers['Pragma'] = 'no-cache'
    return resp
