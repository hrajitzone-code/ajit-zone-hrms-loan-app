import os
from flask import Flask, render_template
from config import Config
from models import db, User, SystemSetting

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Initialize extensions
    db.init_app(app)

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

    # Database Initialization & Seeding
    with app.app_context():
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
        os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'pdf'), exist_ok=True)
        os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'noc'), exist_ok=True)
        os.makedirs(os.path.dirname(app.config['SQLALCHEMY_DATABASE_URI'].replace('sqlite:///', '')), exist_ok=True)

        # On Vercel: copy bundled instance/loan_system.db to writable /tmp/loan_system.db
        is_vercel = os.environ.get('VERCEL') == '1' or os.environ.get('VERCEL_ENV') is not None
        if is_vercel:
            bundled_db = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'instance', 'loan_system.db')
            target_tmp_db = '/tmp/loan_system.db'
            if os.path.exists(bundled_db) and (not os.path.exists(target_tmp_db) or os.path.getsize(target_tmp_db) == 0):
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

if __name__ == '__main__':
    app = create_app()
    app.run(host='0.0.0.0', port=8080, debug=True)
