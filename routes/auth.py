from flask import Blueprint, render_template, request, redirect, url_for, flash, session, g
from models import db, User, AuditLog
from functools import wraps
from datetime import datetime
from extensions import limiter

auth_bp = Blueprint('auth', __name__)

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('auth.login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not g.user:
                flash('Please log in to access this page.', 'warning')
                return redirect(url_for('auth.login', next=request.url))
            if g.user.is_superadmin():
                return f(*args, **kwargs)
            if g.user.role not in roles:
                flash('Unauthorized access: You do not have permission for this action.', 'danger')
                return redirect(url_for('dashboard.index'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def superadmin_required(f):
    """Restricts access strictly to Primary Super Admin (Sakshi Shukla)."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not g.user:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('auth.login', next=request.url))
        if not (g.user.is_primary_superadmin or g.user.username == 'sakshi'):
            flash('Access Denied: Only Primary Super Admin (Sakshi Shukla) has permission to manage users and RBAC controls.', 'danger')
            return redirect(url_for('dashboard.index'))
        return f(*args, **kwargs)
    return decorated_function

def permission_required(module, action):
    """
    Fine-grained permission decorator.
    Verifies that the logged-in user possesses the specified action permission for the module.
    Super Admin (Sakshi Shukla) has full access to all modules and actions.
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not g.user:
                flash('Please log in to access this page.', 'warning')
                return redirect(url_for('auth.login', next=request.url))
            
            # Super Admin bypasses all checks
            if g.user.is_superadmin():
                return f(*args, **kwargs)

            # Check if user has permission
            if not g.user.has_permission(module, action):
                flash(f'Access Denied: You do not have permission to perform "{action.replace("_", " ").title()}" on {module.replace("_", " ").title()}.', 'danger')
                if request.endpoint == 'dashboard.index':
                    return render_template('base.html', denied=True), 403
                return redirect(url_for('dashboard.index'))
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

@auth_bp.before_app_request
def load_logged_in_user():
    user_id = session.get('user_id')
    if user_id is None:
        g.user = None
    else:
        g.user = User.query.get(user_id)
        if g.user:
            # Immediate deactivation protection: If deactivated while logged in, revoke session instantly
            if not g.user.is_active:
                session.clear()
                g.user = None
                flash('Account Deactivated: Your user account is currently disabled. Access denied.', 'danger')
                return redirect(url_for('auth.login'))
            # Refresh session to always match live database state
            session['user_role'] = g.user.role
            session['is_superadmin'] = g.user.is_superadmin()
            session['is_primary_superadmin'] = g.user.is_primary_superadmin
        else:
            # User was deleted from DB while logged in
            session.clear()
            g.user = None
            flash('Account no longer exists. Access denied.', 'danger')
            return redirect(url_for('auth.login'))

@auth_bp.route('/login', methods=['GET', 'POST'])
@limiter.limit("10 per minute; 50 per hour", methods=["POST"])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        if not username or not password:
            flash('Please provide both Username and Password.', 'danger')
            return render_template('login.html')

        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            if not user.is_active:
                flash('Account Deactivated: Your user account is currently disabled. Please contact Super Admin.', 'danger')
                return render_template('login.html')

            session.clear()
            session.permanent = True
            session['user_id'] = user.id
            session['username'] = user.username
            session['user_role'] = user.role
            session['full_name'] = user.full_name
            session['is_superadmin'] = user.is_superadmin()
            session['is_primary_superadmin'] = user.is_primary_superadmin

            # Audit log
            log = AuditLog(
                user_id=user.id,
                user_name=user.full_name,
                role=user.role,
                action='LOGIN',
                module='Auth',
                reason=f"User logged in successfully as {user.role}",
                ip_address=request.remote_addr
            )
            db.session.add(log)
            db.session.commit()

            flash(f'Welcome back, {user.full_name}!', 'success')
            next_page = request.args.get('next')
            return redirect(next_page or url_for('dashboard.index'))
        else:
            flash('Invalid username or password. Access denied.', 'danger')

    return render_template('login.html')

@auth_bp.route('/logout')
def logout():
    if g.user:
        log = AuditLog(
            user_id=g.user.id,
            user_name=g.user.full_name,
            role=g.user.role,
            action='LOGOUT',
            module='Auth',
            reason="User logged out",
            ip_address=request.remote_addr
        )
        db.session.add(log)
        db.session.commit()
    session.clear()
    flash('You have been logged out successfully.', 'info')
    return redirect(url_for('auth.login'))
