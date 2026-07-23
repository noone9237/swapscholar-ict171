# SwapScholar verification report

Date checked: 23 July 2026

## Homepage expansion

- Added proposal-level problem/solution content and project purpose.
- Added six searchable skill-category entry points.
- Explained mutual swaps and time-credit exchanges.
- Added account, confirmation, review and validation trust information.
- Added live database activity statistics and the deployed technology stack.
- Added accessible FAQ content and stronger registration/browse calls to action.
- Reviewed the complete long-form page for layout consistency and horizontal overflow.

## Private exchange chat

- Accepted and completed exchanges include a private message thread.
- Only the requester and recipient can open or post to the conversation.
- Pending exchanges and unrelated accounts receive an authorization error.
- Messages are CSRF-protected, length-limited, timestamped and stored in SQLite.
- Existing databases receive the new message table automatically at application startup.

## Proposal coverage review

| Proposal requirement | Implementation |
| --- | --- |
| Student accounts and login | Registration, hashed passwords, login, logout and protected member routes |
| Student profiles | University, course, biography, availability, rating and credit balance |
| Offered/wanted skills | Add, list and remove skills in two separate directions |
| Search and discovery | Search by skill, description, student, university and category |
| Compatible matching | Mutual matches compare wanted skills with other students' offered skills |
| Exchange requests | Direct swaps or one-credit requests with message and schedule |
| Request decisions | Accept, reject and requester cancellation rules |
| Completion | Both students must independently confirm completion |
| Trust layer | Reviews and 1–5 ratings are limited to completed exchanges |
| Time credits | Credit is reserved on acceptance and transferred to the teacher on completion |
| Statistics | Live totals, categories and trusted-member data from SQLite |
| Azure stack | Deployment files for Ubuntu, Apache, Gunicorn/Flask, SQLite and HTTPS |

## Review passes completed

### 1. Functional workflow tests

Eight automated tests pass:

- Public pages and seeded content
- Registration, password hashing and starting credits
- CSRF rejection for unprotected form submissions
- Skill creation and mutual matching
- Complete direct-swap workflow and review
- Credit reservation and final transfer
- Rejection of an action by an unrelated user
- Rejection of private chat access by pending and unrelated users

### 2. Static code review

- Python syntax compilation passed.
- Ruff code-quality checks passed.
- Bandit security scan passed with no reported issues.
- JavaScript syntax check passed.
- All 13 POST forms were checked and contain CSRF tokens.
- No unsafe template `safe` filters, HTML injection, shell execution or dynamic
  evaluation patterns were found.

### 3. Runtime review

The production Gunicorn entry point started successfully with a temporary
SQLite database. The following routes returned HTTP 200:

- `/`
- `/browse`
- `/how-it-works`
- `/statistics`
- `/login`
- `/register`

### 4. Interface review

- Desktop rendering was visually inspected against the supplied proposal
  screenshot.
- The dark navy grid, mint accent, outlined title, exchange preview and card
  treatment follow the original theme.
- A viewport-edge issue on the floating hero tags was found and corrected.
- Responsive breakpoints are included for desktop, tablet and mobile layouts.
- Focus indicators, reduced-motion support, labelled forms and a skip link are
  included for accessibility.

### 5. Deployment review

- Gunicorn runs only on `127.0.0.1:8000`.
- Apache continues to own the public HTTP/HTTPS connection.
- The existing proposal directory is backed up before deployment.
- The application is installed in a separate `/var/www/swapscholar` directory.
- Secrets live in a protected environment file rather than source code.
- The SQLite instance directory is the only application directory granted
  write access by the system service.

### 6. Live production verification

The completed application was deployed to:

`https://swapscholar36018014.japaneast.cloudapp.azure.com/`

The live workflow was manually demonstrated using two different student
accounts:

- Account registration and secure login
- Profile and offered/wanted skill updates
- Request creation, receipt and acceptance
- Private messages sent by both participants
- Independent completion confirmation
- Review availability after completion

The maintenance script was installed at
`/usr/local/sbin/swapscholar-maintenance` and returned:

- SwapScholar service active
- Apache service active
- Public HTTPS response `200`
- TLS certificate valid for more than 14 days
- SQLite integrity result `ok`
- Timestamped database backup created with SHA-256 checksum
- Summary: `6 passed, 0 failed`

### 7. GitHub continuous integration

The public repository includes `.github/workflows/tests.yml`. GitHub Actions
successfully installed the application dependencies and ran all eight tests on
an Ubuntu runner after the workflow was committed.

The green workflow result provides independently visible evidence that the
repository can be tested from a clean environment.
