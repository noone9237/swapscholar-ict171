# SwapScholar

SwapScholar is a functional student-to-student skill exchange platform built for
the ICT171 cloud server project.

**Tagline:** Teach what you know. Learn what you need.

The application keeps the same dark Azure/teal visual identity as the original
proposal website while turning the proposal into a working Flask and SQLite
system.

The expanded public homepage presents the full project concept, skill categories,
exchange models, trust controls, live platform activity, architecture, FAQs and
clear calls to action.

## Implemented functions

- Secure registration, login and logout with hashed passwords
- Student profiles, university, course, biography and availability
- Offered and wanted skill management
- Search by skill, student, university or category
- Mutual match ranking based on compatible offered/wanted skills
- Direct skill swaps and one-credit learning requests
- Incoming/outgoing request dashboard
- Private participant-only messaging for accepted and completed exchanges
- Accept, reject and cancel workflow
- Two-sided completion confirmation
- Time-credit reservation and transfer
- Reviews and 1–5 ratings after completed exchanges
- Live community statistics generated from SQLite
- CSRF protection, server-side validation and ownership permission checks
- Responsive desktop, tablet and mobile interface

## Demonstration accounts

Run `flask --app app seed-demo` once, then use:

| Name | Email | Password |
| --- | --- | --- |
| Aisha Rahman | aisha@demo.swapscholar | Demo123! |
| Daniel Kim | daniel@demo.swapscholar | Demo123! |
| Mia Chen | mia@demo.swapscholar | Demo123! |
| Omar Hassan | omar@demo.swapscholar | Demo123! |

The seeded database includes skills, one completed exchange and one pending
request so the interface is useful immediately.

## Local development

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
export SWAPSCHOLAR_SECRET_KEY="local-development-secret"
flask --app app init-db
flask --app app seed-demo
flask --app app run --debug --port 8000
```

Open `http://127.0.0.1:8000`.

## Main project files

- `app.py` — application factory, database helpers, routes and workflow rules
- `schema.sql` — SQLite tables, constraints and indexes
- `templates/` — reusable Jinja interface pages
- `static/css/style.css` — proposal-matched responsive design system
- `static/js/app.js` — menu and form interactions
- `tests/test_app.py` — automated functional and security tests
- `deploy/` — Apache, systemd and environment examples for the Azure VM
- `DEPLOYMENT_GUIDE.md` — safe deployment procedure

## Important production note

The production environment must use a long random secret key and HTTPS cookies.
The supplied systemd/environment examples enable those settings. Do not publish
the development fallback key.
