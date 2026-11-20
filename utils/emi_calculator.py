import math
from datetime import datetime, date
import calendar
from models import SystemSetting

def add_months(orig_date, months, target_day=None):
    year = orig_date.year + (orig_date.month + months - 1) // 12
    month = (orig_date.month + months - 1) % 12 + 1
    max_day = calendar.monthrange(year, month)[1]
    if target_day is not None:
        day = min(target_day, max_day)
    else:
        day = min(orig_date.day, max_day)
    return date(year, month, day)

def calculate_emi_schedule(loan_amount, monthly_emi, start_date, deduction_day=5, tenure_months=None, interest_rate=0.0):
    """
    Calculates EMI schedule with exact date alignment and final installment auto-adjustment.
    """
    if isinstance(start_date, str):
        start_date = datetime.strptime(start_date, '%Y-%m-%d').date()

    if not tenure_months or tenure_months <= 0:
        if monthly_emi and monthly_emi > 0:
            tenure_months = math.ceil(loan_amount / monthly_emi)
        else:
            tenure_months = 12
    if not monthly_emi or monthly_emi <= 0:
        monthly_emi = round(loan_amount / tenure_months, 2)

    schedule = []
    accumulated_emi = 0.0
    
    first_year = start_date.year
    first_month = start_date.month
    max_day_first = calendar.monthrange(first_year, first_month)[1]
    aligned_day = min(deduction_day, max_day_first)
    
    if start_date.day > aligned_day:
        first_due_date = add_months(date(first_year, first_month, 1), 1, target_day=deduction_day)
    else:
        first_due_date = date(first_year, first_month, aligned_day)

    for i in range(1, tenure_months + 1):
        if i == 1:
            due_date = first_due_date
        else:
            due_date = add_months(first_due_date, i - 1, target_day=deduction_day)

        if i == tenure_months:
            scheduled_emi = round(loan_amount - accumulated_emi, 2)
        else:
            scheduled_emi = round(monthly_emi, 2)
            if accumulated_emi + scheduled_emi > loan_amount:
                scheduled_emi = round(loan_amount - accumulated_emi, 2)

        accumulated_emi += scheduled_emi
        outstanding_after = max(0.0, round(loan_amount - accumulated_emi, 2))

        schedule.append({
            'emi_no': i,
            'due_date': due_date,
            'scheduled_emi': scheduled_emi,
            'outstanding_after': outstanding_after
        })

        if outstanding_after == 0:
            break

    tenure_from = schedule[0]['due_date'] if schedule else first_due_date
    tenure_to = schedule[-1]['due_date'] if schedule else first_due_date

    return {
        'schedule': schedule,
        'actual_tenure': len(schedule),
        'tenure_from': tenure_from,
        'tenure_to': tenure_to,
        'total_calculated': round(accumulated_emi, 2)
    }

def validate_loan_eligibility(employee, loan_amount, tenure_months, monthly_emi):
    """
    Dynamically validates loan criteria against Admin System Settings without code hardcoding.
    """
    def get_setting(key, default_val):
        st = SystemSetting.query.filter_by(key=key).first()
        if st and st.value is not None and st.value != '':
            try:
                return type(default_val)(st.value)
            except Exception:
                return default_val
        return default_val

    min_salary = get_setting('min_salary', 20000.0)
    min_service_months = get_setting('min_service_period_months', 6)
    max_loan_limit = get_setting('max_loan_limit', 500000.0)
    max_tenure_months = get_setting('max_tenure_months', 36)
    max_emi_ratio = get_setting('max_salary_emi_ratio', 0.50)

    errors = []

    if employee.current_salary < min_salary:
        errors.append(f"Employee salary (₹{employee.current_salary:,.2f}) is below minimum requirement of ₹{min_salary:,.2f}")

    if loan_amount > max_loan_limit:
        errors.append(f"Loan amount (₹{loan_amount:,.2f}) exceeds maximum allowed limit of ₹{max_loan_limit:,.2f}")

    if tenure_months > max_tenure_months:
        errors.append(f"Tenure ({tenure_months} months) exceeds maximum allowed limit of {max_tenure_months} months")

    max_allowed_emi = employee.current_salary * max_emi_ratio
    if monthly_emi > max_allowed_emi:
        errors.append(f"Monthly EMI (₹{monthly_emi:,.2f}) exceeds {int(max_emi_ratio*100)}% of employee salary limit (Max ₹{max_allowed_emi:,.2f})")

    # Check Service Period if joining date or hiring date is set
    service_date = employee.joining_date or employee.hiring_date
    if service_date:
        today = date.today()
        months_worked = (today.year - service_date.year) * 12 + (today.month - service_date.month)
        if months_worked < min_service_months:
            errors.append(f"Employee service period ({months_worked} months) is less than required {min_service_months} months")

    return {
        'is_eligible': len(errors) == 0,
        'errors': errors
    }
