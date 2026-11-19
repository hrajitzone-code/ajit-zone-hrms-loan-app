import os
from flask import Flask, render_template
from config import Config
from models import db, User, SystemSetting

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Initialize extensions
    db.init_app(app)
    from extensions import csrf, limiter
    csrf.init_app(app)
    limiter.init_app(app)

    # Security Error Handlers
    from flask_wtf.csrf import CSRFError
    from flask_limiter.errors import RateLimitExceeded
    from flask import flash, redirect, request, jsonify, url_for

    @app.errorhandler(CSRFError)
    def handle_csrf_error(e):
        if request.is_json or request.path.startswith('/api/'):
            return jsonify({'success': False, 'error': 'CSRF token missing or invalid', 'message': e.description}), 400
        flash('Security Warning: Session expired or security token invalid. Please try submitting again.', 'danger')
        return redirect(request.referrer or url_for('dashboard.index')), 400

    @app.errorhandler(429)
    @app.errorhandler(RateLimitExceeded)
    def handle_ratelimit_error(e):
        if request.is_json or request.path.startswith('/api/'):
            return jsonify({'success': False, 'error': 'Rate limit exceeded', 'message': 'Too many requests. Please wait a minute.'}), 429
        flash('Security Alert: Too many login attempts. Please wait a minute before trying again.', 'danger')
        return render_template('login.html'), 429

    # Register Blueprints
    from routes.auth import auth_bp
    from routes.dashboard import dashboard_bp
    from routes.employee import employee_bp
    from routes.loan import loan_bp
    from routes.emi import emi_bp
    from routes.communication import comm_bp
    from routes.reports import reports_bp
    from routes.audit import audit_bp
    from routes.settings import settings_bp
    from routes.user_mgmt import user_mgmt_bp
    from routes.salary_route import salary_bp
    from routes.google_sheets_route import google_sheets_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(employee_bp)
    app.register_blueprint(loan_bp)
    app.register_blueprint(emi_bp)
    app.register_blueprint(comm_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(audit_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(user_mgmt_bp)
    app.register_blueprint(salary_bp)
    app.register_blueprint(google_sheets_bp)

    # Custom Jinja Filters
    @app.template_filter('inr')
    def inr_format(amount):
        if amount is None:
            return "₹0.00"
        return f"₹{float(amount):,.2f}"

    @app.template_filter('datefmt')
    def date_format(d, fmt='%d-%b-%Y'):
        if not d:
            return ""
        return d.strftime(fmt)

    # Context Processors
    @app.context_processor
    def inject_global_utilities():
        from flask import g
        from utils.permissions import MODULES_DEF, ACTIONS_META
        company_setting = SystemSetting.query.filter_by(key='company_name').first()
        company_name = company_setting.value if company_setting and company_setting.value else "AJIT ZONE PVT. LTD."
        
        def has_perm(module, action):
            if hasattr(g, 'user') and g.user:
                return g.user.has_permission(module, action)
            return False

        def can_view_all(module):
            if hasattr(g, 'user') and g.user:
                return g.user.can_view_all(module)
            return False

        def can_view_own(module):
            if hasattr(g, 'user') and g.user:
                return g.user.can_view_own_only(module)
            return False

        def is_superadmin():
            if hasattr(g, 'user') and g.user:
                return g.user.is_superadmin()
            return False

        return dict(
            COMPANY_NAME=company_name,
            has_perm=has_perm,
            can_view_all=can_view_all,
            can_view_own=can_view_own,
            is_superadmin=is_superadmin,
            MODULES_DEF=MODULES_DEF,
            ACTIONS_META=ACTIONS_META
        )

    # Health Check Endpoint
    @app.route('/api/health')
    def health_check():
        from flask import jsonify
        import time
        start = time.time()
        db_type = 'PostgreSQL' if app.config.get('IS_POSTGRES') else 'SQLite'
        try:
            db.session.execute(db.text('SELECT 1'))
            latency_ms = round((time.time() - start) * 1000, 2)
            return jsonify({
                'status': 'healthy',
                'database_type': db_type,
                'database_connected': True,
                'latency_ms': latency_ms,
                'company': app.config.get('COMPANY_NAME')
            }), 200
        except Exception as e:
            return jsonify({
                'status': 'degraded',
                'database_type': db_type,
                'database_connected': False,
                'error': str(e)
            }), 500

    # Vercel Serverless Persistence Synchronization
    @app.after_request
    def auto_sync_to_blob(response):
        from flask import request
        # If running on managed PostgreSQL, ACID persistence is already guaranteed in cloud database
        if app.config.get('IS_POSTGRES'):
            return response

        from utils.blob_db import sync_to_blob, is_vercel
        import time
        if is_vercel() and request.method in ['POST', 'PUT', 'DELETE', 'PATCH']:
            if response.status_code < 400:
                try:
                    db.session.commit()
                except Exception:
                    pass
                try:
                    # Retry with exponential backoff on transient network failures
                    synced = False
                    for attempt in range(1, 4):
                        if sync_to_blob():
                            synced = True
                            break
                        time.sleep(0.15 * attempt)
                    if not synced:
                        print("[BLOB AUTO-SYNC CRITICAL] Failed to upload database to blob after 3 attempts!", flush=True)
                except Exception as e:
                    print(f"[BLOB AUTO-SYNC ERROR] {e}", flush=True)
        return response

    # Database Initialization & Seeding
    with app.app_context():
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
        os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'pdf'), exist_ok=True)
        os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'noc'), exist_ok=True)

        is_postgres_active = app.config.get('IS_POSTGRES', False)

        if not is_postgres_active:
            db_uri_str = app.config['SQLALCHEMY_DATABASE_URI']
            if db_uri_str.startswith('sqlite:///'):
                db_file = db_uri_str.replace('sqlite:///', '')
                if os.path.dirname(db_file):
                    os.makedirs(os.path.dirname(db_file), exist_ok=True)

            # On Vercel with SQLite: sync cloud database from Vercel Blob or initialize from seed
            is_vercel_env = os.environ.get('VERCEL') == '1' or os.environ.get('VERCEL_ENV') is not None
            if is_vercel_env:
                from utils.blob_db import sync_from_blob
                target_tmp_db = '/tmp/loan_system.db'
                synced = sync_from_blob(force=True)
                if not synced or not os.path.exists(target_tmp_db) or os.path.getsize(target_tmp_db) == 0:
                    bundled_db = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'instance', 'loan_system.db')
                    if os.path.exists(bundled_db):
                        import shutil
                        shutil.copyfile(bundled_db, target_tmp_db)

        db.create_all()

        # Seed Primary Super Admin (Sakshi Shukla)
        if not User.query.filter_by(username='sakshi').first():
            sakshi_sa = User(
                username='sakshi',
                full_name='Sakshi Shukla',
                role='Super_Admin',
                email='sakshi.shukla@ajitzone.com',
                is_primary_superadmin=True,
                is_active=True
            )
            sakshi_sa.set_password('sakshi123')
            db.session.add(sakshi_sa)

        db.session.commit()

    return app

app = create_app()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=True)
