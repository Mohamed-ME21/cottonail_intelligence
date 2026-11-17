# Cottonil Intelligence Hub

Ten analysis pages (React + Vite) on a FastAPI + pandas backend:
- `frontend`: React + Vite
- `backend`: FastAPI
- Existing project data and scripts are not modified.

## 1) Copy into your existing project

Extract/copy the `frontend` and `backend` folders into:

`H:\Cottonil_Intelligence_Hub`

The result should look like:

```text
H:\Cottonil_Intelligence_Hub\
  frontend\
  backend\
  scripts\                 # existing
  data\
    processed\             # existing
  reports\                 # existing
```

## 2) Start the backend (PowerShell window 1)

```powershell
cd H:\Cottonil_Intelligence_Hub
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install --upgrade pip
py -m pip install -r backend\requirements.txt
py -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

Check:
- API health: http://127.0.0.1:8000/api/health
- API docs: http://127.0.0.1:8000/docs

If PowerShell blocks activation, run this once in the same window:
```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```
Then activate the environment again.

## 3) Start the frontend (PowerShell window 2)

```powershell
cd H:\Cottonil_Intelligence_Hub\frontend
npm install
npm run dev
```

Open the local URL printed by Vite, usually http://localhost:5173.

## Pages and endpoints

| Page | Endpoint |
|---|---|
| Executive Overview | `/api/analytics/executive-overview` |
| Sales Performance | `/api/analytics/sales-performance` |
| Branches & Geography | `/api/analytics/branches` |
| Products & Profitability | `/api/analytics/products` |
| Customer Intelligence | `/api/analytics/customers` |
| Returns & Delivery | `/api/analytics/returns` |
| Inventory & Transfers | `/api/analytics/inventory` |
| Procurement & Imports | `/api/analytics/procurement` |
| Marketing ROI | `/api/analytics/marketing` |
| Workforce & Costs | `/api/analytics/workforce` |

The interface switches between English and Arabic (RTL). Test the backend with `py -m pytest backend/tests -q`.

## Data notes shown in the app
- Data ends mid-month, so month-over-month uses the last complete month.
- Orders without a customer ID are excluded from customer metrics.
- Imports are in USD and never added to EGP totals.
- Campaign `orders_attributed` and purchase-order quantities do not reconcile with sales; the pages warn instead of showing derived ratios.

## Notes
- This first version intentionally displays placeholders, not business KPIs.
- No AI API key is required at this stage.
- Never put an AI API key in frontend code. It will be configured server-side in a later phase.
