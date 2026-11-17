from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

db = SQLAlchemy()

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    full_name = db.Column(db.String(128), nullable=False)
    email = db.Column(db.String(128), nullable=True)
    role = db.Column(db.String(32), nullable=False, default='HR') 
    # Roles: Super_Admin, HR, Finance_Payroll, Manager, Employee, Viewer
    employee_id = db.Column(db.Integer, db.ForeignKey('employees.id'), nullable=True)
    permissions = db.Column(db.Text, nullable=True)
    is_primary_superadmin = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    employee = db.relationship('Employee', foreign_keys=[employee_id], backref='user_account', uselist=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def is_superadmin(self):
        return self.role == 'Super_Admin' or self.is_primary_superadmin

    def get_permissions(self):
        """Returns the dictionary of module permissions for this user."""
        if self.is_superadmin():
            from utils.permissions import MODULES_DEF
            perms = {}
            for m in MODULES_DEF:
                perms[m['id']] = list(m['actions'])
            return perms

        from utils.permissions import parse_user_permissions
        return parse_user_permissions(self.permissions, self.role)

    def has_permission(self, module, action):
        """Checks if user has specific action permission on a given module."""
        if self.is_superadmin():
            return True
        if not self.is_active:
            return False

        perms = self.get_permissions()
        module_actions = perms.get(module, [])
        if isinstance(module_actions, list):
            # 'view' covers view_all or view_own
            if action == 'view':
                return 'view_all' in module_actions or 'view_own' in module_actions
            return action in module_actions
        return False

    def can_view_all(self, module):
        if self.is_superadmin():
            return True
        perms = self.get_permissions()
        actions = perms.get(module, [])
        return 'view_all' in actions

    def can_view_own_only(self, module):
        if self.is_superadmin():
            return False
        perms = self.get_permissions()
        actions = perms.get(module, [])
        return 'view_own' in actions and 'view_all' not in actions

class Employee(db.Model):
    __tablename__ = 'employees'
    id = db.Column(db.Integer, primary_key=True)
    emp_id = db.Column(db.String(32), unique=True, nullable=False, index=True)
    name = db.Column(db.String(128), nullable=False)
    department = db.Column(db.String(64), nullable=False, index=True)
    designation = db.Column(db.String(64), nullable=False)
    current_salary = db.Column(db.Float, nullable=False, default=0.0)
    email = db.Column(db.String(128), nullable=True)
    phone = db.Column(db.String(32), nullable=True)
    pan_number = db.Column(db.String(32), nullable=True)
    aadhar_number = db.Column(db.String(32), nullable=True)
    bank_name = db.Column(db.String(64), nullable=True)
    bank_account_no = db.Column(db.String(64), nullable=True)
    ifsc_code = db.Column(db.String(32), nullable=True)
    status = db.Column(db.String(16), nullable=False, default='Active') # Active, Inactive, Terminated
    hiring_date = db.Column(db.Date, nullable=True)
    joining_date = db.Column(db.Date, nullable=True)
    address = db.Column(db.Text, nullable=True)
    city = db.Column(db.String(64), nullable=True)
    emergency_contact = db.Column(db.String(64), nullable=True)
    emergency_relation = db.Column(db.String(32), nullable=True)
    emergency_phone = db.Column(db.String(32), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    loans = db.relationship('Loan', backref='employee', lazy=True)

class Loan(db.Model):
    __tablename__ = 'loans'
    id = db.Column(db.Integer, primary_key=True)
    loan_id = db.Column(db.String(32), unique=True, nullable=False, index=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employees.id'), nullable=False)
    loan_type = db.Column(db.String(64), nullable=False) # Personal Loan, Emergency Advance, Salary Advance, Medical Loan, Home Loan
    loan_amount = db.Column(db.Float, nullable=False)
    monthly_emi = db.Column(db.Float, nullable=False)
    interest_rate = db.Column(db.Float, default=0.0) # Annual Interest Rate %
    processing_fee = db.Column(db.Float, default=0.0) # Processing Fee Amount
    emi_start_date = db.Column(db.Date, nullable=False)
    emi_deduction_day = db.Column(db.Integer, nullable=False, default=5)
    tenure_months = db.Column(db.Integer, nullable=False)
    tenure_from = db.Column(db.Date, nullable=True)
    tenure_to = db.Column(db.Date, nullable=True)
    reason = db.Column(db.Text, nullable=True)
    remarks = db.Column(db.Text, nullable=True)
    declaration_accepted = db.Column(db.Boolean, default=True)
    application_date = db.Column(db.Date, default=datetime.utcnow().date)
    approval_status = db.Column(db.String(32), nullable=False, default='Pending') # Pending, Approved, Rejected
    approval_date = db.Column(db.DateTime, nullable=True)
    approved_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    disbursement_date = db.Column(db.DateTime, nullable=True)
    loan_status = db.Column(db.String(32), nullable=False, default='Pending') # Pending, Active, Closed, Rejected
    workflow_status = db.Column(db.String(32), nullable=False, default='Submitted') 
    # Workflow Statuses: Submitted -> Under_Review -> Approved -> Disbursed -> EMI_Deducted -> Closed (or Rejected)
    total_recovered = db.Column(db.Float, default=0.0)
    outstanding_balance = db.Column(db.Float, default=0.0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    schedules = db.relationship('EMISchedule', backref='loan', cascade='all, delete-orphan', lazy=True)
    deductions = db.relationship('EMIDeduction', backref='loan', cascade='all, delete-orphan', lazy=True)
    adjustments = db.relationship('EMIAdjustment', backref='loan', cascade='all, delete-orphan', lazy=True)
    documents = db.relationship('LoanDocument', backref='loan', cascade='all, delete-orphan', lazy=True)
    closure = db.relationship('LoanClosure', backref='loan', uselist=False, cascade='all, delete-orphan')

class EMISchedule(db.Model):
    __tablename__ = 'emi_schedule'
    id = db.Column(db.Integer, primary_key=True)
    loan_id = db.Column(db.Integer, db.ForeignKey('loans.id'), nullable=False)
    emi_no = db.Column(db.Integer, nullable=False)
    due_date = db.Column(db.Date, nullable=False, index=True)
    scheduled_emi = db.Column(db.Float, nullable=False)
    actual_deduction = db.Column(db.Float, default=0.0)
    actual_deduction_date = db.Column(db.Date, nullable=True)
    outstanding_after = db.Column(db.Float, default=0.0)
    status = db.Column(db.String(32), nullable=False, default='Upcoming') 
    # Upcoming, Due, Deducted, Partial, Pending, Overdue, Adjusted, Closed
    remarks = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    deductions = db.relationship('EMIDeduction', backref='schedule_item', lazy=True)

class EMIDeduction(db.Model):
    __tablename__ = 'emi_deductions'
    id = db.Column(db.Integer, primary_key=True)
    loan_id = db.Column(db.Integer, db.ForeignKey('loans.id'), nullable=False)
    emi_schedule_id = db.Column(db.Integer, db.ForeignKey('emi_schedule.id'), nullable=False)
    deduction_date = db.Column(db.Date, nullable=False)
    amount_deducted = db.Column(db.Float, nullable=False)
    payment_mode = db.Column(db.String(32), default='Payroll Deduction')
    transaction_ref = db.Column(db.String(64), nullable=True)
    deduction_status = db.Column(db.String(32), default='Processed')
    # Statuses: Pending, Processed, Partially Deducted, Adjusted, Failed
    recorded_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    remarks = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class EMIAdjustment(db.Model):
    __tablename__ = 'emi_adjustments'
    id = db.Column(db.Integer, primary_key=True)
    loan_id = db.Column(db.Integer, db.ForeignKey('loans.id'), nullable=False)
    emi_schedule_id = db.Column(db.Integer, db.ForeignKey('emi_schedule.id'), nullable=True)
    adjustment_type = db.Column(db.String(64), nullable=False) 
    # Add_To_Next_Month, Extend_Tenure, Custom_Waiver, Custom_Penalty
    amount = db.Column(db.Float, nullable=False)
    old_emi_amount = db.Column(db.Float, nullable=True)
    new_emi_amount = db.Column(db.Float, nullable=True)
    reason = db.Column(db.Text, nullable=False)
    requested_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    approved_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    approval_status = db.Column(db.String(32), nullable=False, default='Pending') # Pending, Approved, Rejected
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class SalarySheetSync(db.Model):
    __tablename__ = 'salary_sheet_syncs'
    id = db.Column(db.Integer, primary_key=True)
    sync_batch_id = db.Column(db.String(64), nullable=False, index=True)
    salary_month = db.Column(db.String(16), nullable=False) # YYYY-MM
    employee_id = db.Column(db.Integer, db.ForeignKey('employees.id'), nullable=False)
    loan_id = db.Column(db.Integer, db.ForeignKey('loans.id'), nullable=True)
    emi_amount = db.Column(db.Float, default=0.0)
    deduction_amount = db.Column(db.Float, default=0.0)
    outstanding_balance = db.Column(db.Float, default=0.0)
    deduction_status = db.Column(db.String(32), nullable=False, default='Pending')
    # Statuses: Pending, Processed, Partially Deducted, Adjusted, Failed
    sync_source = db.Column(db.String(32), default='Google_Sheets_API')
    # Sources: Google_Sheets_API, Excel_Import, CSV_Export, Manual
    error_log = db.Column(db.Text, nullable=True)
    synced_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    synced_at = db.Column(db.DateTime, default=datetime.utcnow)

    employee = db.relationship('Employee', backref='salary_syncs', lazy=True)
    loan = db.relationship('Loan', backref='salary_syncs', lazy=True)

class LoanDocument(db.Model):
    __tablename__ = 'loan_documents'
    id = db.Column(db.Integer, primary_key=True)
    loan_id = db.Column(db.Integer, db.ForeignKey('loans.id'), nullable=False)
    document_name = db.Column(db.String(128), nullable=False)
    file_path = db.Column(db.String(256), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)

class LoanClosure(db.Model):
    __tablename__ = 'loan_closures'
    id = db.Column(db.Integer, primary_key=True)
    loan_id = db.Column(db.Integer, db.ForeignKey('loans.id'), nullable=False, unique=True)
    closure_date = db.Column(db.Date, nullable=False)
    total_loan_amount = db.Column(db.Float, nullable=False)
    total_recovered = db.Column(db.Float, nullable=False)
    final_outstanding = db.Column(db.Float, default=0.0)
    closed_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    remarks = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class NOCRecord(db.Model):
    __tablename__ = 'noc_records'
    id = db.Column(db.Integer, primary_key=True)
    noc_number = db.Column(db.String(64), unique=True, nullable=False, index=True)
    loan_id = db.Column(db.Integer, db.ForeignKey('loans.id'), nullable=False)
    employee_id = db.Column(db.Integer, db.ForeignKey('employees.id'), nullable=False)
    generated_date = db.Column(db.DateTime, default=datetime.utcnow)
    pdf_path = db.Column(db.String(256), nullable=True)
    generated_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

class Notification(db.Model):
    __tablename__ = 'notifications'
    id = db.Column(db.Integer, primary_key=True)
    recipient_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    title = db.Column(db.String(128), nullable=False)
    message = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class CommunicationLog(db.Model):
    __tablename__ = 'communication_logs'
    id = db.Column(db.Integer, primary_key=True)
    loan_id = db.Column(db.Integer, db.ForeignKey('loans.id'), nullable=False)
    channel = db.Column(db.String(32), nullable=False) # Email, WhatsApp
    recipient = db.Column(db.String(128), nullable=False)
    sent_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    status = db.Column(db.String(32), default='Sent')
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class AuditLog(db.Model):
    __tablename__ = 'audit_logs'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    user_name = db.Column(db.String(64), nullable=True)
    role = db.Column(db.String(32), nullable=True)
    action = db.Column(db.String(64), nullable=False) # CREATE, UPDATE, DELETE, APPROVE, REJECT, ADJUST, IMPORT, SYNC
    module = db.Column(db.String(64), nullable=False) # Loans, Employees, EMI, Settings, System, Users, SalarySync
    record_id = db.Column(db.String(64), nullable=True)
    old_value = db.Column(db.Text, nullable=True)
    new_value = db.Column(db.Text, nullable=True)
    reason = db.Column(db.Text, nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    ip_address = db.Column(db.String(45), nullable=True)

class SystemSetting(db.Model):
    __tablename__ = 'system_settings'
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(64), unique=True, nullable=False)
    value = db.Column(db.Text, nullable=True)
    description = db.Column(db.String(256), nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class ImportLog(db.Model):
    __tablename__ = 'import_logs'
    id = db.Column(db.Integer, primary_key=True)
    file_name = db.Column(db.String(128), nullable=False)
    records_processed = db.Column(db.Integer, default=0)
    records_success = db.Column(db.Integer, default=0)
    records_failed = db.Column(db.Integer, default=0)
    error_details = db.Column(db.Text, nullable=True)
    imported_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    imported_at = db.Column(db.DateTime, default=datetime.utcnow)
