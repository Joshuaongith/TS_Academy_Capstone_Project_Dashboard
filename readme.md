# TS Auto Repair - Administrative Dashboard

A serverless administrative web dashboard built to manage and process customer feedback, track sentiment scores, and review AI-generated draft responses. This application is designed specifically for serverless deployment on Vercel and connects to a serverless Neon PostgreSQL database.

## Tech Stack

* **Backend:** Python 3.12, Flask
* **Database:** Neon PostgreSQL, SQLAlchemy, `psycopg` (v3)
* **Authentication:** Flask-Login
* **Deployment:** Vercel (Serverless Functions)
* **Frontend:** Jinja2 templates, Custom CSS, Vanilla JavaScript

## System Architecture Highlights

### 1. Serverless Database Connection Handling
Because Neon is a serverless database that aggressively drops idle connections, this application utilizes SQLAlchemy's **Pessimistic Disconnect Handling** (`pool_pre_ping=True`). This ensures that stale connections in the pool are silently tested and re-established before executing queries, completely preventing `OperationalError` crashes when the dashboard sits idle.

### 2. Mobile-Responsive Table Architecture
The dashboard utilises a custom CSS Grid system designed for complex data displays. On desktop, queues display as standard rows. On tablet and mobile breakpoints (under 768px), the CSS automatically reconfigures the rows into stacked cards, utilizing HTML `data-label` attributes to dynamically inject field headers above each data point for high readability. Vanilla JavaScript is used to manage interactive UI states, including the overlay-toggled mobile sidebar.

### 3. n8n Dead Letter Queue (DLQ) Resilience
This dashboard works in tandem with an external n8n automation pipeline. If critical relational data (like a missing Location ID or Job ID) causes a database insertion to fail, the n8n error workflow captures the exact webhook payload. This acts as a Dead Letter Queue, allowing administrators to manually correct the missing data and re-trigger the payload without losing the customer's original feedback.

## Local Development Setup

1. **Clone the repository:**
   ```bash
   git clone <your-repository-url>
   cd <your-repository-folder>
   ```

2. **Create and activate a virtual environment:**
    ```bash
    python3.12 -m venv .venv
    source .venv/bin/activate
    
    ```


3. **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    
    ```


4. **Environment Variables:**
Create a `.env` file in the root directory and add your credentials:
    ```env
    SECRET_KEY=your_secure_development_key
    DATABASE_URI=postgresql+psycopg://username:password@your-neon-hostname.neon.tech/dbname
    
    ```


5. **Run the application:**
    ```bash
    flask --app api/index.py run --debug
    
    ```


## Vercel Deployment

This repository is pre-configured for Vercel deployment via the `vercel.json` file, which maps static assets and routes all backend traffic through `api/index.py`.

1. Import the GitHub repository into your Vercel account.
2. In the deployment settings, add the following Environment Variables:
* `SECRET_KEY` (Generate a secure, random string)
* `DATABASE_URI` (Ensure the prefix is exactly `postgresql+psycopg://` to utilize the modern v3 driver).


3. Deploy.
