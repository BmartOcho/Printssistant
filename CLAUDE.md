# Printssistant — Claude Code Context

## Architecture & Implementation Patterns

**FastAPI Middleware for Caching**: Use middleware to intercept static file requests (.css, .js, etc.) and apply centralized Cache-Control headers. Pattern: check request path in middleware, return header dict if matched.

**Async CPU-Bound Work**: Use `asyncio.to_thread()` to delegate CPU-heavy operations (PDF rendering, image tracing) to thread pool. Prevents event loop blocking. Wrap in `asyncio.get_event_loop().run_in_executor(None, fn, *args)` for older Python versions.

**BackgroundTask for Non-Blocking Ops**: Import `BackgroundTasks`, add to route signature, then `.add_task(fn, *args)` for post-response cleanup (temp file deletion, job logging). Won't block response.

**Gunicorn + UvicornWorker**: Railway Procfile: `web: gunicorn app:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:$PORT`. The UvicornWorker is key—it manages async contexts across processes. Use `-w 4` for multi-core Railway instances.

**Job History Logging**: Async function in db.py that inserts to Supabase `job_history` table (user_id, tool_name, timestamp, file_size, processing_ms). Schedule via BackgroundTask. Enables data-driven optimization decisions.

## Tech Stack & Dependencies

- FastAPI + Uvicorn (async web framework)
- Gunicorn (multi-process manager)
- PyPDF (not PyPDF2—deprecated; drop-in replacement)
- Supabase (PostgreSQL, database queries in db.py)
- Stripe (one-time lifetime Pro payment)
- VTracer + Potrace (image vectorization)
- cairosvg (SVG preview generation)
- ReportLab (PDF/EPS output)

## Testing Approach

**Live Deployment Testing**: Use browser automation against Railway preview URL. Verify:
- `/health` endpoint returns 200 with `{"status": "ok"}`
- Each tool interface loads and processes sample input
- Cache-Control headers present on static assets
- Download links generated with proper timestamps
- No console errors or API failures

**Network Inspection**: Fetch static assets and inspect response headers via JavaScript in browser console.

## File Structure

- `app.py` (~900 lines): Main FastAPI app, all routes, middleware, auth dependency injection
- `auth.py`: JWT encode/decode, dependency functions
- `db.py`: Supabase client singleton, all DB queries, job history logging
- `*_logic.py` (e.g., `vectorizer.py`, `swatchset_logic.py`): Tool-specific processing logic
- `static/`: HTML, CSS, JS (vanilla SPA, no build tools)
- `Procfile`: Railway deployment config
- `requirements.txt`: Python dependencies + gunicorn

## Known Quirks & Gotchas

**Railway Filesystem**: Ephemeral—files written to `/tmp` are lost on dyno restart. Don't rely on persistent local storage; use Supabase or Vercel Blob.

**JWT_SECRET**: Must be set as env var in Railway dashboard. No hardcoded fallback—app fails fast if missing (correct behavior).

**Auth Middleware**: Check `auth.py` for JWT decode logic. Routes use `current_user: str = Depends(get_current_user)` to inject authenticated user ID.

**PyPDF vs PyPDF2**: Switch completed. `from pypdf import PdfReader, PdfWriter` (not `PyPDF2`).

**Temp File Cleanup**: Uploaded PDFs go to `UPLOAD_DIR`, processed files to `PROCESSED_DIR`. BackgroundTask deletes after response. Check if cleanup is actually running in production logs.

## Priority Implementation Order (from audit)

- ✅ #1 JWT_SECRET safety (no fallback)
- ✅ #2 File size limits (MAX_UPLOAD_BYTES check)
- ✅ #3 Temp file cleanup (BackgroundTask)
- ✅ #4 CORS locked to domain (not `["*"]`)
- ✅ #5 CPU-bound ops to executor (asyncio.to_thread)
- ✅ #6 Multi-worker Gunicorn config
- ✅ #7 PyPDF2 → pypdf migration
- ✅ #8 Health check endpoint
- ✅ #10 Rate limiting on auth (slowapi)
- ✅ #15 Input validation bounds (Pydantic Query, ge/le)
- ⏳ #11-14, #16-17: Medium priority (logging, UX, preview handling)
- ⏳ #22-24: Low priority (subscriptions, queues, streaming)

## Debugging Tips

**Check Railway Logs**: `vercel logs` or Railway dashboard. Look for unhandled exceptions, slow endpoints, database connection failures.

**Frontend Errors**: Open browser console (F12). Check for CORS errors, auth failures, API response errors.

**Supabase Queries**: Test in Supabase dashboard SQL editor first. Verify table structure and RLS policies allow operations.

**Procfile Syntax**: Indent with spaces, not tabs. Test locally with `honcho start` before pushing.
