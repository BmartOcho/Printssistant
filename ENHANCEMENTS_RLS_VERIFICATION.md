# Item 2: Supabase RLS Verification Report

**Status:** Manual verification required (not code implementation)

## What to Check

The following Supabase tables need to be verified for proper Row-Level Security (RLS) configuration:

### 1. `preflight_jobs` Table
- **RLS Status:** Should be ENABLED
- **Expected Policies:**
  - Authenticated users can only read/update their own jobs (where `user_id = auth.uid()`)
  - Anonymous users can only see jobs matching their IP address
  - Service role should bypass RLS for background tasks
- **Current Risk:** Without RLS, any authenticated user could view/modify other users' preflight results

### 2. `users` Table
- **RLS Status:** Should be ENABLED
- **Expected Policies:**
  - Each user can only read/update their own row (where `id = auth.uid()`)
  - Public profile reads should be allowed (for discovering OG/DG users)
- **Current Risk:** Without RLS, users could modify or view other users' personal data

### 3. `job_history` Table
- **RLS Status:** Should be ENABLED
- **Expected Policies:**
  - Users can only read their own job history (where `user_id = auth.uid()`)
  - Service role needs full access for analytics/logging
- **Current Risk:** Without RLS, usage patterns and job metadata could leak between users

## How to Verify

1. Go to https://app.supabase.com
2. Navigate to your Printssistant project
3. Go to **Authentication** → **Policies**
4. For each table above:
   - Confirm RLS is toggled ON (green switch)
   - Review all policies listed
   - Ensure policies match expected rules above

## Important Note

The Python code in `app.py` includes auth checks (is_pro, quota enforcement) that provide defense-in-depth, but RLS is the **final security boundary**. If someone obtains a leaked Supabase key and bypasses the API, RLS prevents unauthorized data access at the database level.

**ACTION REQUIRED:** Manually verify in Supabase dashboard and report findings before production deployment.

## Checklist

- [ ] `preflight_jobs` RLS enabled with user_id/IP policies
- [ ] `users` RLS enabled with id = auth.uid() policy
- [ ] `job_history` RLS enabled with user_id policy
- [ ] All policies reviewed and match security requirements
- [ ] Production deployment approved
