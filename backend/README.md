# GadzIT C++ IDE - Cloudflare Migration

This project has been migrated to a Cloudflare Pages + Workers + Containers architecture.

## Architecture

1.  **Frontend (`/frontend`)**:
    *   Hosted on **Cloudflare Pages**.
    *   Static HTML/CSS/JS.
    *   Uses `fetch` and `EventSource` (SSE) to communicate with the backend.
    *   No server-side rendering.

2.  **Backend (`/backend`)**:
    *   Hosted on **Cloudflare Workers**.
    *   Acts as an API Gateway.
    *   Uses **Durable Objects** with **Containers** to run the Python/C++ logic.
    *   Handles CORS and session management.

3.  **Container (`/backend/container`)**:
    *   Runs the heavy Python logic and C++ compilation.
    *   Exposes an HTTP API (Flask) on port 8080.
    *   Managed by the Worker via the `MyContainer` binding.

## Deployment Instructions

### Prerequisites
*   Node.js and npm installed.
*   Cloudflare Wrangler CLI installed (`npm install -g wrangler`).
*   Docker installed (for building the container).
*   Access to Cloudflare Workers Containers (Private Beta).

### 1. Backend Deployment

Navigate to the backend directory:
```bash
cd backend
```

Install dependencies:
```bash
npm install
```

Deploy the Worker and Container:
```bash
wrangler deploy
```
*Note: This requires access to the Cloudflare Containers beta. If you do not have access, you will need to deploy the container to a separate service (e.g., Fly.io, Cloud Run) and update `src/index.js` to point to that external URL.*

### 2. Frontend Deployment

Navigate to the frontend directory:
```bash
cd ../frontend
```

Deploy to Cloudflare Pages:
```bash
wrangler pages deploy . --project-name gadzit-frontend
```

### 3. Configuration

*   Update `frontend/assets/app.js`:
    *   Change `const API_URL = '/api';` to your full Worker URL (e.g., `https://gadzit-cpp-ide.your-subdomain.workers.dev/api`) if not serving from the same domain.
    *   If using Custom Domains, ensure `/api` routes to the Worker and everything else to Pages.

## API Endpoints

*   `POST /api/run`: Submit code for compilation. Returns `sessionId`.
*   `GET /api/output/:sessionId`: Stream output (Server-Sent Events).
*   `POST /api/input/:sessionId`: Send input to stdin.

## Development

To run the backend locally (requires Docker):
```bash
cd backend
wrangler dev --remote
```

To serve the frontend:
```bash
cd frontend
npx serve .
```
