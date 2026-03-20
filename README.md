# Printssistant ⚡

A web-based toolkit for prepress and commercial printing professionals. Upload PDFs and images, get production-ready output in seconds.

**Live at [printssistant.com](https://printssistant.com)**

## Tools

### Free (20 jobs/month)
- **Duplexer** — Duplicates every page in a PDF (front/back) for duplex printing workflows
- **Auto-Cropper** — Splits PDF pages into a grid (rows × columns) for gang-run cutting
- **Insert Between** — Interleaves pages from a second PDF at a set interval (slip sheets, inserts)

### Open (no account needed)
- **Even/Odd Generator** — Generates even or odd page number sequences for selective printing

### Pro (one-time lifetime purchase)
- **Vectorizer** — Converts raster images to production-quality SVG with prepress-tuned presets
- **Swatch Set Generator** — Creates CMYK swatch variation sheets for ink matching and color correction

## Tech Stack

- **Backend**: Python / FastAPI / Uvicorn
- **Database**: Supabase (PostgreSQL)
- **Auth**: Custom JWT (bcrypt + python-jose)
- **Payments**: Stripe Checkout (one-time lifetime Pro upgrade)
- **Hosting**: Railway
- **Frontend**: Vanilla HTML/CSS/JS

## Local Development

```bash
git clone https://github.com/BmartOcho/Printssistant.git
cd Printssistant
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Set environment variables:
```bash
export SUPABASE_URL="your-supabase-url"
export SUPABASE_SERVICE_KEY="your-service-key"
export JWT_SECRET="your-secret"
export STRIPE_SECRET_KEY="your-stripe-key"
export STRIPE_WEBHOOK_SECRET="your-webhook-secret"
```

Run:
```bash
uvicorn app:app --host 0.0.0.0 --port 8000
```

## Author

**Benjamin Martinec** · [BmartOcho](https://github.com/BmartOcho)
