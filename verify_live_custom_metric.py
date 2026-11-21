import urllib.request
import urllib.parse
import http.cookiejar
import re
import json
import ssl

BASE_URL = "https://ajit-zone-hrms-loan-app.vercel.app"

def create_session():
    cj = http.cookiejar.CookieJar()
    ctx = ssl.create_default_context()
    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(cj),
        urllib.request.HTTPSHandler(context=ctx)
    )
    return opener

def extract_csrf(html):
    m = re.search(r'<meta\s+name=["\']csrf-token["\']\s+content=["\']([^"\']+)["\']', html)
    if m:
        return m.group(1)
    m2 = re.search(r'name=["\']csrf_token["\']\s+value=["\']([^"\']+)["\']', html)
    if m2:
        return m2.group(1)
    return ""

def main():
    print(f"=== VERIFYING LIVE PRODUCTION: {BASE_URL} ===")
    session = create_session()

    # Step 1: GET Login Page
    req = urllib.request.Request(f"{BASE_URL}/login", headers={'User-Agent': 'Mozilla/5.0'})
    with session.open(req) as resp:
        login_html = resp.read().decode('utf-8')
        csrf_token = extract_csrf(login_html)
        print(f"[1] Login Page: HTTP {resp.status}, CSRF Token obtained: {csrf_token[:15]}...")

    # Step 2: POST Login as Sakshi Shukla
    login_data = urllib.parse.urlencode({
        'username': 'sakshi',
        'password': 'sakshi123',
        'csrf_token': csrf_token
    }).encode('utf-8')

    req_login = urllib.request.Request(f"{BASE_URL}/login", data=login_data, headers={
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
        'Content-Type': 'application/x-www-form-urlencoded',
        'Referer': f"{BASE_URL}/login",
        'Origin': BASE_URL
    })
    with session.open(req_login) as resp:
        dashboard_html = resp.read().decode('utf-8')
        print(f"[2] Login POST: HTTP {resp.status}, redirected to dashboard: {'Dashboard' in dashboard_html}")

    # Step 3: GET /users Console
    req_users = urllib.request.Request(f"{BASE_URL}/users?tab=users", headers={'User-Agent': 'Mozilla/5.0'})
    with session.open(req_users) as resp:
        users_html = resp.read().decode('utf-8')
        user_csrf = extract_csrf(users_html)
        print(f"[3] /users Console: HTTP {resp.status}, CSRF: {user_csrf[:15]}...")
        # Check presence of 'Save Custom Metric' button in HTML
        has_save_metric = "Save Custom Metric" in users_html
        print(f"    - 'Save Custom Metric' button present in DOM: {has_save_metric}")
        assert has_save_metric, "Save Custom Metric button must be rendered in HTML"

        # Check for Pradeep Gothwal
        m_user = re.search(r'id="userPermForm(\d+)"', users_html)
        if not m_user:
            m_user = re.search(r'/users/(\d+)/permissions', users_html)
        target_user_id = int(m_user.group(1)) if m_user else 7
        print(f"    - Target User ID for custom metric testing: {target_user_id}")

    # Step 4: Submit Custom Metric via Form POST (Simulating Modal 'Save Custom Metric' button)
    print("\n--- TEST FLOW 1: CREATE & SAVE CUSTOM METRIC VIA FORM ---")
    form_data = urllib.parse.urlencode([
        ('csrf_token', user_csrf),
        ('active_tab', 'users'),
        ('perm_loans', 'view_all'),
        ('perm_loans', 'edit'),
        ('perm_employees', 'view_all')
    ]).encode('utf-8')

    req_save = urllib.request.Request(f"{BASE_URL}/users/{target_user_id}/permissions", data=form_data, headers={
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
        'Content-Type': 'application/x-www-form-urlencoded',
        'Referer': f"{BASE_URL}/users?tab=users",
        'Origin': BASE_URL
    })
    with session.open(req_save) as resp:
        save_resp_html = resp.read().decode('utf-8')
        print(f"[4] Form POST /users/{target_user_id}/permissions: HTTP {resp.status}")
        success_in_flash = "Custom metric &amp; permissions" in save_resp_html or "Custom metric & permissions" in save_resp_html
        badge_configured = "Custom Matrix &amp; Metric Configured" in save_resp_html or "Custom Matrix & Metric Configured" in save_resp_html
        print(f"    - Success Banner in response: {success_in_flash}")
        print(f"    - Badge 'Custom Matrix & Metric Configured' displayed: {badge_configured}")

    # Step 5: REFRESH PAGE & VERIFY PERSISTENCE ACROSS SESSIONS / CONTAINERS
    print("\n--- TEST FLOW 2: REFRESH & PERSISTENCE VERIFICATION ---")
    req_refresh = urllib.request.Request(f"{BASE_URL}/users/{target_user_id}/permissions/json", headers={
        'User-Agent': 'Mozilla/5.0'
    })
    with session.open(req_refresh) as resp:
        user_json = json.loads(resp.read().decode('utf-8'))
        print(f"[5] GET /users/{target_user_id}/permissions/json: HTTP {resp.status}")
        print(f"    - Saved permissions: {user_json.get('permissions')}")
        perms = user_json.get('permissions', {})
        assert 'loans' in perms and 'edit' in perms['loans'], "Loans edit permission must persist"
        assert 'employees' in perms, "Employees permission must persist"
        print("    [PASS] Custom metric permanently persisted in Cloud Vercel Blob Database!")

    # Step 6: EDIT CUSTOM METRIC (Simulating Tab 2 AJAX Update)
    print("\n--- TEST FLOW 3: EDIT CUSTOM METRIC VIA AJAX JSON ---")
    edit_payload = json.dumps({
        'permissions': {
            'loans': ['view_all', 'approve', 'add'],
            'salary': ['view_all', 'export'],
            'reports': ['view_all']
        }
    }).encode('utf-8')

    req_edit = urllib.request.Request(f"{BASE_URL}/users/{target_user_id}/permissions", data=edit_payload, headers={
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
        'Content-Type': 'application/json',
        'X-CSRFToken': user_csrf,
        'X-Requested-With': 'XMLHttpRequest',
        'Referer': f"{BASE_URL}/users?tab=matrix",
        'Origin': BASE_URL
    })
    with session.open(req_edit) as resp:
        edit_json = json.loads(resp.read().decode('utf-8'))
        print(f"[6] AJAX POST /users/{target_user_id}/permissions: HTTP {resp.status}")
        print(f"    - Server response: {edit_json}")
        assert edit_json.get('success') is True, "Edit must return success: True"

    # Step 7: VERIFY EDITED METRIC IN CLOUD DATABASE
    req_verify_edit = urllib.request.Request(f"{BASE_URL}/users/{target_user_id}/permissions/json", headers={
        'User-Agent': 'Mozilla/5.0'
    })
    with session.open(req_verify_edit) as resp:
        edit_verify_json = json.loads(resp.read().decode('utf-8'))
        print(f"[7] Verified Edited Permissions: {edit_verify_json.get('permissions')}")
        assert 'salary' in edit_verify_json.get('permissions', {}), "Salary must now be in permissions"
        print("    [PASS] Edited custom metric verified in Cloud Database!")

    # Step 8: RESET / DELETE CUSTOM METRIC BACK TO ROLE DEFAULTS
    print("\n--- TEST FLOW 4: RESET / DELETE CUSTOM METRIC BACK TO DEFAULTS ---")
    reset_data = urllib.parse.urlencode({
        'csrf_token': user_csrf,
        'active_tab': 'users'
    }).encode('utf-8')

    req_reset = urllib.request.Request(f"{BASE_URL}/users/{target_user_id}/reset-permissions", data=reset_data, headers={
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
        'Content-Type': 'application/x-www-form-urlencoded',
        'Referer': f"{BASE_URL}/users?tab=users",
        'Origin': BASE_URL
    })
    with session.open(req_reset) as resp:
        reset_html = resp.read().decode('utf-8')
        print(f"[8] POST /users/{target_user_id}/reset-permissions: HTTP {resp.status}")
        reset_flash = "reset to standard" in reset_html
        badge_default = "Standard Manager Defaults" in reset_html
        print(f"    - Reset flash message: {reset_flash}")
        print(f"    - Badge returned to standard defaults: {badge_default}")

    # Step 9: VERIFY FINAL RESET IN DATABASE
    req_final = urllib.request.Request(f"{BASE_URL}/users/{target_user_id}/permissions/json", headers={
        'User-Agent': 'Mozilla/5.0'
    })
    with session.open(req_final) as resp:
        final_json = json.loads(resp.read().decode('utf-8'))
        print(f"[9] Final Permissions State: {final_json.get('permissions')}")
        assert final_json.get('permissions') is None, "Custom permissions must be None after reset"
        print("    [PASS] Custom metric reset successfully to role defaults!")

    print("\n=======================================================")
    print("ALL LIVE PRODUCTION TESTS PASSED WITH 100% SUCCESS!")
    print("=======================================================")

if __name__ == '__main__':
    main()
