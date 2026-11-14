# HACKED-BETA-2026- Zero Hero
**Less waste. More possibility.**

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
## Demo
<table>
  <tr>
    <td align="center" width="33%">
      <img src="https://github.com/user-attachments/assets/e86f11d8-1fc6-4700-a7b1-5ecb93bac8f8" width="300" alt="Homepage" />
    </td>
    <td align="center" width="33%">
      <img src="https://github.com/user-attachments/assets/c0a4bfb1-3df7-4a7d-a4e8-b25d618fc711" width="300" alt="Interactive Map" />
    </td>
    <td align="center" width="33%">
      <img src="https://github.com/user-attachments/assets/46611955-870b-4a2f-8399-f0b142aa3e42" width="300" alt="AI Chat" />
    </td>
  </tr>
  <tr>
    <td align="center"><b>Homepage</b></td>
    <td align="center"><b>Interactive Map</b></td>
    <td align="center"><b>AI Chat</b></td>
  </tr>
</table>
video link:
https://github.com/user-attachments/assets/4c14c0ab-4aa3-4a2e-a9dd-011817fe485d
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

