# HACKED-BETA-2026
# Zero Hero

**Less waste. More possibility.**

An AI-powered environmental reporting web app built for **HACKED 2026**.

## Quick Start

### 1. Setup

Create a file named `agent/.env` in the project root and add your [Groq API key](https://console.groq.com/keys):

```env
GROQ_API_KEY=your_groq_api_key_here
```

### 2. Dependencies

Run these commands from the project root:

```bash
uv --directory backend sync
cd frontend
npm install
cd ..
```

### 3. Run the Application

Open **two separate terminals**, both starting from the project root.

**Terminal 1 — Backend**

```bash
PYTHONPATH="$PWD" uv --directory backend run \
  --env-file ../agent/.env \
  uvicorn app.main:app --reload --port 8000
```

**Terminal 2 — Frontend**

```bash
cd frontend
npm start
```

### 4. Open

http://localhost:####

The Zero Hero web app is ready to use.

## Technical Implementation

### Frontend
- **React + TypeScript:** Interactive user interface for map-based reporting, AI conversations, and personalized action plans.
- **Vite:** Frontend development and build tooling.
- **MapLibre GL JS + OpenStreetMap:** Interactive maps for locating, submitting, and tracking environmental reports.
- **CSS:** Custom responsive UI with a sustainability-focused design.

### Backend
- **FastAPI (Python):** Handles report management, API requests, file uploads, and AI integration.
- **LangGraph:** Orchestrates the AI workflow, including analysis, information retrieval, action planning, and human approval.
- **SQLAlchemy + SQLite / PostgreSQL:** Database management for reports, agent execution states, and tracking.

### AI & Intelligence
- **Groq API (GPT-OSS 20B):** Processes natural-language reports, classifies environmental issues, and generates AI-assisted recommendations.
- **Retrieval-Augmented Generation (RAG):** Retrieves relevant municipal waste guidelines and contact information to support recommendations.
- **Structured AI Output:** Organizes results into safety risk, recyclability, waste category, 311 assistance, and action steps.
- **Location-Aware Assistance:** Uses report descriptions and geographic coordinates to provide locally relevant guidance.
- **Human-in-the-Loop:** Requires user approval before external communication. The AI can prepare 311 reporting instructions without automatically submitting reports.

### Development & Deployment
- **Git + GitHub:** Version control and team collaboration through branches and pull requests.
- **Docker Compose:** Containerized application deployment configuration.
- **AWS:** Cloud deployment configuration and documentation.

