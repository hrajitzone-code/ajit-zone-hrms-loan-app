// AJIT ZONE PVT. LTD. - Client-side Logic & Interactions

// CSRF Protection Interceptor for AJAX / Fetch Requests
(function setupCSRF() {
    const metaTag = document.querySelector('meta[name="csrf-token"]');
    const csrfToken = metaTag ? metaTag.getAttribute('content') : '';
    if (!csrfToken) return;

    const originalFetch = window.fetch;
    window.fetch = function(url, options = {}) {
        const method = (options.method || 'GET').toUpperCase();
        if (['POST', 'PUT', 'DELETE', 'PATCH'].includes(method)) {
            if (!options.headers) {
                options.headers = {};
            }
            if (options.headers instanceof Headers) {
                if (!options.headers.has('X-CSRFToken')) {
                    options.headers.append('X-CSRFToken', csrfToken);
                }
            } else if (Array.isArray(options.headers)) {
                options.headers.push(['X-CSRFToken', csrfToken]);
            } else {
                if (!options.headers['X-CSRFToken']) {
                    options.headers['X-CSRFToken'] = csrfToken;
                }
            }
        }
        return originalFetch(url, options);
    };
})();

document.addEventListener('DOMContentLoaded', function() {
    initEmployeeLookup();
    initEmiPreviewCalculator();
    initDashboardCharts();
});

// 1. Real-time Employee Lookup in Loan Application Form (Auto-Fetch)
function initEmployeeLookup() {
    const empInput = document.getElementById('employee_id_input');
    const empDropdown = document.getElementById('employee_select_dropdown');

    if (!empInput) return;

    let debounceTimer = null;

    // Trigger on typing or choosing from datalist
    empInput.addEventListener('input', function() {
        const val = this.value.trim();
        // Sync with dropdown if match found
        if (empDropdown) {
            empDropdown.value = val;
        }
        clearTimeout(debounceTimer);
        if (val.length >= 2) {
            debounceTimer = setTimeout(() => fetchEmployeeDetails(val), 250);
        } else if (val.length === 0) {
            clearEmployeeMasterFields();
        }
    });

    empInput.addEventListener('change', function() {
        if (this.value.trim()) {
            fetchEmployeeDetails(this.value.trim());
        }
    });

    empInput.addEventListener('blur', function() {
        if (this.value.trim()) {
            fetchEmployeeDetails(this.value.trim());
        }
    });

    // Auto-fetch default value if already populated (e.g. employee login mode)
    if (empInput.value.trim()) {
        fetchEmployeeDetails(empInput.value.trim());
    }
}

function fetchEmployeeDetails(empCode) {
    if (!empCode) {
        clearEmployeeMasterFields();
        return;
    }
    
    fetch(`/api/employee/lookup/${encodeURIComponent(empCode)}`)
        .then(response => {
            if (!response.ok) {
                throw new Error('Not found');
            }
            return response.json();
        })
        .then(data => {
            if (data.success) {
                const emp = data.employee;
                setInputValue('emp_name_display', emp.name);
                setInputValue('emp_dept_display', emp.department);
                setInputValue('emp_desig_display', emp.designation);
                setInputValue('emp_joining_display', emp.joining_date || '-');
                setInputValue('emp_salary_display', emp.current_salary ? `₹${parseFloat(emp.current_salary).toLocaleString('en-IN', {minimumFractionDigits: 2})}` : '₹0.00');
                
                const contactStr = [emp.phone, emp.email].filter(Boolean).join(' | ') || '-';
                setInputValue('emp_contact_display', contactStr);

                // Financial status notice
                const statusBox = document.getElementById('emp_loan_status_alert');
                if (statusBox) {
                    statusBox.style.display = 'block';
                    if (emp.status !== 'Active') {
                        statusBox.innerHTML = `
                            <div class="alert alert-danger py-2 mb-0 small">
                                <i class="fa-solid fa-triangle-exclamation me-1"></i>
                                <strong>Employee Inactive:</strong> This employee is marked as <strong>${emp.status}</strong> in the Employee Master.
                            </div>
                        `;
                    } else if (emp.active_loans_count > 0) {
                        statusBox.innerHTML = `
                            <div class="alert alert-warning py-2 mb-0 small">
                                <i class="fa-solid fa-triangle-exclamation me-1 text-warning"></i>
                                <strong>Active Loan Notice:</strong> Employee has <strong>${emp.active_loans_count} active loan(s)</strong> with an outstanding balance of <strong>₹${parseFloat(emp.total_outstanding).toLocaleString('en-IN', {minimumFractionDigits: 2})}</strong>.
                            </div>
                        `;
                    } else {
                        statusBox.innerHTML = `
                            <div class="alert alert-success py-2 mb-0 small">
                                <i class="fa-solid fa-circle-check me-1 text-success"></i>
                                <strong>Verification Passed:</strong> Active employee record verified with no existing loan liabilities.
                            </div>
                        `;
                    }
                }

                // Sync dropdown value
                const empDropdown = document.getElementById('employee_select_dropdown');
                if (empDropdown && empDropdown.value !== emp.emp_id) {
                    empDropdown.value = emp.emp_id;
                }

                calculateLiveEmiPreview();
            } else {
                showNotFoundEmployeeFields();
            }
        })
        .catch(err => {
            showNotFoundEmployeeFields();
        });
}

function clearEmployeeMasterFields() {
    setInputValue('emp_name_display', '');
    setInputValue('emp_dept_display', '');
    setInputValue('emp_desig_display', '');
    setInputValue('emp_joining_display', '');
    setInputValue('emp_salary_display', '');
    setInputValue('emp_contact_display', '');
    const statusBox = document.getElementById('emp_loan_status_alert');
    if (statusBox) statusBox.style.display = 'none';
}

function showNotFoundEmployeeFields() {
    setInputValue('emp_name_display', 'Employee Not Found');
    setInputValue('emp_dept_display', '-');
    setInputValue('emp_desig_display', '-');
    setInputValue('emp_joining_display', '-');
    setInputValue('emp_salary_display', '-');
    setInputValue('emp_contact_display', '-');
    const statusBox = document.getElementById('emp_loan_status_alert');
    if (statusBox) {
        statusBox.style.display = 'block';
        statusBox.innerHTML = `
            <div class="alert alert-danger py-2 mb-0 small">
                <i class="fa-solid fa-circle-xmark me-1"></i>
                No matching employee record found in Employee Master. Please check the Employee ID.
            </div>
        `;
    }
}

function setInputValue(id, val) {
    const el = document.getElementById(id);
    if (el) {
        if (el.tagName === 'INPUT' || el.tagName === 'SELECT') {
            el.value = val;
        } else {
            el.innerText = val;
        }
    }
}

// 2. Real-time EMI Calculator & Final EMI Auto-adjustment Preview
function initEmiPreviewCalculator() {
    const amountInput = document.getElementById('loan_amount');
    const emiInput = document.getElementById('monthly_emi');
    const tenureInput = document.getElementById('tenure_months');

    if (!amountInput || !emiInput) return;

    amountInput.addEventListener('input', calculateLiveEmiPreview);
    emiInput.addEventListener('input', calculateLiveEmiPreview);
    if (tenureInput) tenureInput.addEventListener('input', calculateLiveEmiPreview);
}

function calculateLiveEmiPreview() {
    const amount = parseFloat(document.getElementById('loan_amount')?.value || 0);
    const monthlyEmi = parseFloat(document.getElementById('monthly_emi')?.value || 0);
    const tenureInput = document.getElementById('tenure_months');
    
    const previewContainer = document.getElementById('emi_live_preview_box');
    if (!previewContainer) return;

    if (amount <= 0 || monthlyEmi <= 0) {
        previewContainer.innerHTML = '<span class="text-muted small">Enter Loan Amount and Monthly EMI to preview schedule calculations.</span>';
        return;
    }

    const calculatedTenure = Math.ceil(amount / monthlyEmi);
    if (tenureInput && (!tenureInput.value || tenureInput.value <= 0)) {
        tenureInput.value = calculatedTenure;
    }

    const tenure = parseInt(tenureInput?.value || calculatedTenure);
    const regularTotal = (tenure - 1) * monthlyEmi;
    const finalEmi = Math.max(0, amount - regularTotal);

    previewContainer.innerHTML = `
        <div class="alert alert-info py-2 mb-0" style="font-size: 0.9rem;">
            <strong>EMI Calculation Summary:</strong><br/>
            • Total Installments: <strong>${tenure} Months</strong><br/>
            • Regular Installments (1 to ${tenure - 1}): <strong>₹${monthlyEmi.toLocaleString('en-IN')} / month</strong><br/>
            • <strong>Final EMI Auto-Adjusted Balance:</strong> <span class="text-success font-weight-bold">₹${finalEmi.toLocaleString('en-IN')}</span>
        </div>
    `;
}

// 3. Initialize Dashboard Chart.js Widgets
function initDashboardCharts() {
    const deptCanvas = document.getElementById('deptChart');
    const statusCanvas = document.getElementById('statusChart');
    const monthlyCanvas = document.getElementById('monthlyChart');

    if (!deptCanvas || !statusCanvas || !monthlyCanvas) return;

    fetch('/api/dashboard/chart-data')
        .then(res => res.json())
        .then(data => {
            new Chart(deptCanvas.getContext('2d'), {
                type: 'doughnut',
                data: {
                    labels: data.dept_labels,
                    datasets: [{
                        data: data.dept_values,
                        backgroundColor: ['#2563eb', '#16a34a', '#d97706', '#9333ea', '#0284c7', '#ec4899']
                    }]
                },
                options: {
                    responsive: true,
                    plugins: { legend: { position: 'bottom' } }
                }
            });

            new Chart(statusCanvas.getContext('2d'), {
                type: 'pie',
                data: {
                    labels: data.status_labels,
                    datasets: [{
                        data: data.status_values,
                        backgroundColor: ['#16a34a', '#64748b', '#d97706', '#dc2626']
                    }]
                },
                options: {
                    responsive: true,
                    plugins: { legend: { position: 'bottom' } }
                }
            });

            new Chart(monthlyCanvas.getContext('2d'), {
                type: 'bar',
                data: {
                    labels: data.monthly_labels,
                    datasets: [
                        {
                            label: 'Scheduled EMI (₹)',
                            data: data.scheduled_monthly,
                            backgroundColor: '#3b82f6'
                        },
                        {
                            label: 'Actual Recovered (₹)',
                            data: data.recovered_monthly,
                            backgroundColor: '#16a34a'
                        }
                    ]
                },
                options: {
                    responsive: true,
                    scales: { y: { beginAtZero: true } },
                    plugins: { legend: { position: 'top' } }
                }
            });
        })
        .catch(err => console.error('Chart Data Error:', err));
}
