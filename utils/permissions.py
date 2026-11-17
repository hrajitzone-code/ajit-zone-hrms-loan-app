import json

# Master Module Definitions (12 HRMS Modules)
MODULES_DEF = [
    {
        'id': 'dashboard',
        'name': 'Dashboard',
        'category': 'Core',
        'description': 'Executive & Role-based Dashboards',
        'actions': ['view_all', 'manage']
    },
    {
        'id': 'employees',
        'name': 'Employee Master',
        'category': 'HRMS',
        'description': 'Staff records, profiles & directory',
        'actions': ['view_all', 'view_own', 'add', 'edit', 'delete', 'export', 'import']
    },
    {
        'id': 'loan_applications',
        'name': 'Loan Applications',
        'category': 'Loan',
        'description': 'Loan application creation, review & approval',
        'actions': ['view_all', 'view_own', 'add', 'edit', 'approve', 'delete', 'export']
    },
    {
        'id': 'loans',
        'name': 'Active & Closed Loans',
        'category': 'Loan',
        'description': 'Loan accounts, schedules & closure/NOCs',
        'actions': ['view_all', 'view_own', 'edit', 'delete', 'export']
    },
    {
        'id': 'emi',
        'name': 'EMI Management',
        'category': 'Finance',
        'description': 'Monthly deduction entries & EMI tracking',
        'actions': ['view_all', 'view_own', 'add', 'edit', 'export']
    },
    {
        'id': 'adjustments',
        'name': 'Missed EMI & Adjustments',
        'category': 'Finance',
        'description': 'EMI adjustments, tenure extensions & approvals',
        'actions': ['view_all', 'view_own', 'add', 'approve', 'export']
    },
    {
        'id': 'salary',
        'name': 'Salary Integration',
        'category': 'Payroll',
        'description': 'Salary sheet sync & deduction push to payroll',
        'actions': ['view_all', 'import', 'export', 'manage']
    },
    {
        'id': 'reports',
        'name': 'Reports Center',
        'category': 'Analytics',
        'description': 'Department, financial & recovery reports',
        'actions': ['view_all', 'view_own', 'export']
    },
    {
        'id': 'documents',
        'name': 'Documents & Downloads',
        'category': 'HRMS',
        'description': 'Loan documents, schedule PDFs & NOCs',
        'actions': ['view_all', 'view_own', 'add', 'export']
    },
    {
        'id': 'audit_logs',
        'name': 'Audit Logs',
        'category': 'Security',
        'description': 'System security & activity audit trail',
        'actions': ['view_all', 'export']
    },
    {
        'id': 'user_mgmt',
        'name': 'User Management',
        'category': 'Security',
        'description': 'User accounts, roles & custom permissions matrix',
        'actions': ['view_all', 'add', 'edit', 'delete', 'manage']
    },
    {
        'id': 'settings',
        'name': 'System Settings',
        'category': 'System',
        'description': 'Company rules, interest rates & configuration',
        'actions': ['view_all', 'manage']
    }
]

ACTIONS_META = {
    'view_all': {'label': 'View All', 'badge': 'bg-primary', 'icon': 'fa-eye'},
    'view_own': {'label': 'View Own', 'badge': 'bg-secondary', 'icon': 'fa-user'},
    'add': {'label': 'Add', 'badge': 'bg-success', 'icon': 'fa-plus'},
    'edit': {'label': 'Edit', 'badge': 'bg-warning text-dark', 'icon': 'fa-pen'},
    'delete': {'label': 'Delete', 'badge': 'bg-danger', 'icon': 'fa-trash'},
    'approve': {'label': 'Approve', 'badge': 'bg-purple text-white', 'icon': 'fa-check-double'},
    'export': {'label': 'Export', 'badge': 'bg-teal text-white', 'icon': 'fa-file-excel'},
    'import': {'label': 'Import', 'badge': 'bg-dark', 'icon': 'fa-file-import'},
    'manage': {'label': 'Manage', 'badge': 'bg-indigo text-white', 'icon': 'fa-gears'}
}

def get_all_modules_map():
    return {m['id']: m for m in MODULES_DEF}

def get_default_role_permissions(role):
    """Returns standard default permissions if no custom permissions JSON is configured."""
    perms = {}
    
    if role == 'Super_Admin':
        for m in MODULES_DEF:
            perms[m['id']] = list(m['actions'])
            
    elif role == 'Admin':
        for m in MODULES_DEF:
            perms[m['id']] = list(m['actions'])
            
    elif role == 'HR_Manager':
        perms['dashboard'] = ['view_all']
        perms['employees'] = ['view_all', 'add', 'edit', 'export', 'import']
        perms['loan_applications'] = ['view_all', 'add', 'edit', 'approve', 'delete', 'export']
        perms['loans'] = ['view_all', 'edit', 'delete', 'export']
        perms['emi'] = ['view_all', 'add', 'edit', 'export']
        perms['adjustments'] = ['view_all', 'add', 'approve', 'export']
        perms['salary'] = ['view_all', 'export']
        perms['reports'] = ['view_all', 'export']
        perms['documents'] = ['view_all', 'add', 'export']
        perms['audit_logs'] = ['view_all']

    elif role == 'Manager':
        perms['dashboard'] = ['view_all']
        perms['employees'] = ['view_all']
        perms['loan_applications'] = ['view_all', 'add', 'approve', 'export']
        perms['loans'] = ['view_all', 'export']
        perms['emi'] = ['view_all', 'export']
        perms['adjustments'] = ['view_all', 'approve', 'export']
        perms['reports'] = ['view_all', 'export']
        perms['documents'] = ['view_all', 'export']
        
    elif role == 'HR':
        perms['dashboard'] = ['view_all']
        perms['employees'] = ['view_all', 'add', 'edit', 'export', 'import']
        perms['loan_applications'] = ['view_all', 'add', 'edit', 'export']
        perms['loans'] = ['view_all', 'export']
        perms['emi'] = ['view_all', 'add', 'export']
        perms['adjustments'] = ['view_all', 'add', 'export']
        perms['salary'] = ['view_all', 'export']
        perms['reports'] = ['view_all', 'export']
        perms['documents'] = ['view_all', 'add', 'export']
        
    elif role == 'Finance_Payroll':
        perms['dashboard'] = ['view_all']
        perms['salary'] = ['view_all', 'import', 'export', 'manage']
        perms['emi'] = ['view_all', 'add', 'edit', 'export']
        perms['loans'] = ['view_all', 'export']
        perms['adjustments'] = ['view_all', 'export']
        perms['reports'] = ['view_all', 'export']
        perms['documents'] = ['view_all', 'export']
        
    elif role == 'Employee':
        perms['dashboard'] = ['view_all']
        perms['employees'] = ['view_own']
        perms['loan_applications'] = ['view_own', 'add']
        perms['loans'] = ['view_own']
        perms['emi'] = ['view_own']
        perms['documents'] = ['view_own']
        perms['reports'] = ['view_own']
        
    elif role == 'Viewer':
        perms['dashboard'] = ['view_all']
        perms['employees'] = ['view_all', 'export']
        perms['loans'] = ['view_all', 'export']
        perms['emi'] = ['view_all', 'export']
        perms['reports'] = ['view_all', 'export']
        perms['documents'] = ['view_all']

    return perms

def parse_user_permissions(permissions_json, role='Employee'):
    """Parses JSON or returns role defaults."""
    if permissions_json:
        try:
            return json.loads(permissions_json)
        except Exception:
            pass
    return get_default_role_permissions(role)
