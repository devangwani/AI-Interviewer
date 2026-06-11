# Real-Time Multimodal AI Interview Framework

An end-to-end AI-powered interview platform that evaluates candidates across **three simultaneous modalities** — spoken language (via Deepgram STT), facial emotion (via FER + OpenCV), and answer quality (via Groq LLM) — and produces a unified, weighted performance report.

Designed to run natively on an 8 GB RAM machine: no Docker, no heavy local databases.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                        React + Vite (port 5173)                     │
│                                                                     │
│  ┌──────────┐  ┌───────────────┐  ┌────────────┐  ┌─────────────┐ │
│  │  Camera  │  │  Microphone   │  │  Question  │  │   Report    │ │
│  │  Feed    │  │  Capture      │  │  Display   │  │   View      │ │
│  └────┬─────┘  └──────┬────────┘  └─────┬──────┘  └──────┬──────┘ │
│       │ JPEG frames   │ PCM audio        │ REST            │ REST   │
└───────┼───────────────┼──────────────────┼─────────────────┼────────┘
        │ POST          │ WebSocket         │                 │
        ▼               ▼                   ▼                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                   FastAPI Backend (port 8000)                       │
│                                                                     │
│  ┌─────────────────┐  ┌──────────────────┐  ┌──────────────────┐  │
│  │  /analysis      │  │ /interviews/     │  │  /auth           │  │
│  │  emotion-frame  │  │ {id}/stream (WS) │  │  Firebase verify │  │
│  │  speech-metrics │  │ submit-answer    │  │                  │  │
│  └────────┬────────┘  └────────┬─────────┘  └────────┬─────────┘  │
│           │                   │                       │            │
│  ┌────────▼────────┐  ┌───────▼──────────┐           │            │
│  │   ML Layer      │  │  Service Layer   │           │            │
│  │ emotion_analysis│  │  deepgram_service│  firebase │            │
│  │ speech_analysis │  │  groq_service    │  _service │            │
│  │ response_eval   │  └───────┬──────────┘           │            │
│  └─────────────────┘          │                       │            │
└──────────────────────────────┼───────────────────────┼────────────┘
                                │                       │
         ┌──────────────────────┤      ┌────────────────┘
         ▼                      ▼      ▼
   ┌───────────┐        ┌────────────────────────────┐
   │  Deepgram │        │  MongoDB Atlas (cloud)     │
   │  STT API  │        │  users / interviews        │
   └───────────┘        └────────────────────────────┘
         │
         ▼
   ┌───────────┐
   │  Groq LLM │
   │  API      │
   └───────────┘
```

---

## Tech Stack

| Layer      | Technology                          |
|------------|-------------------------------------|
| Frontend   | React 18, Vite, Zustand, Tailwind   |
| Backend    | FastAPI, Uvicorn, Motor (async)     |
| Database   | MongoDB Atlas (cloud — no local DB) |
| Auth       | Firebase Authentication             |
| LLM        | Groq (llama3-70b-8192)              |
| STT        | Deepgram Nova-2 (real-time WS)      |
| Emotion    | FER + OpenCV (headless)             |
| Audio      | librosa + soundfile                 |

---

## Prerequisites

- **Python 3.11+** — `python --version`
- **Node.js 18+** — `node --version`
- **npm 9+** — `npm --version`
- A [MongoDB Atlas](https://www.mongodb.com/atlas) free cluster
- API keys for [Groq](https://console.groq.com), [Deepgram](https://console.deepgram.com), and [Firebase](https://console.firebase.google.com)

---

## Local Setup

### 1. Clone and configure environment

```bash
git clone https://github.com/your-org/ai-interviewer.git
cd ai-interviewer

# Copy the template and fill in your real keys
cp .env.example backend/.env
```

Edit `backend/.env` with your actual API keys and MongoDB URI.

For the frontend, create `frontend/.env.local`:

```bash
cp .env.example frontend/.env.local
# Then uncomment and fill in the VITE_* block at the bottom
```

### 2. Backend setup

```bash
cd backend

# Create and activate virtual environment
python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Frontend setup

```bash
cd frontend
npm install
```

### 4. Run the backend

```bash
# From the backend/ directory with venv active
python run.py
```

The API is now available at `http://localhost:8000`.
Interactive docs: `http://localhost:8000/docs`

### 5. Run the frontend

```bash
# From the frontend/ directory
npm run dev
```

The app is now available at `http://localhost:5173`.

---

## API Routes Reference

### Auth
| Method | Path                  | Description                         |
|--------|-----------------------|-------------------------------------|
| POST   | `/api/v1/auth/login`  | Firebase token → upsert user in DB  |
| GET    | `/api/v1/auth/me`     | Get current user profile            |

### Interviews
| Method | Path                                       | Description                        |
|--------|--------------------------------------------|------------------------------------|
| POST   | `/api/v1/interviews/`                      | Create interview + generate Qs     |
| GET    | `/api/v1/interviews/`                      | List user's interviews             |
| GET    | `/api/v1/interviews/{id}`                  | Get interview detail               |
| POST   | `/api/v1/interviews/{id}/start`            | Mark interview as in-progress      |
| POST   | `/api/v1/interviews/{id}/submit-answer`    | Submit transcript + get LLM score  |
| POST   | `/api/v1/interviews/{id}/complete`         | Finalize + compute overall score   |
| WS     | `/api/v1/interviews/{id}/stream`           | Real-time Deepgram STT stream      |

### Analysis
| Method | Path                              | Description                        |
|--------|-----------------------------------|------------------------------------|
| POST   | `/api/v1/analysis/emotion-frame`  | Analyse single video frame         |
| POST   | `/api/v1/analysis/speech-metrics` | Analyse audio clip metrics         |
| GET    | `/api/v1/analysis/{id}/report`    | Aggregated multimodal report       |

---

## Project Structure

```
AI-Interviewer/
├── frontend/               # React + Vite SPA
│   ├── src/
│   │   ├── components/
│   │   ├── pages/
│   │   ├── hooks/
│   │   ├── services/
│   │   ├── store/
│   │   └── utils/
│   └── package.json
│
├── backend/
│   ├── app/
│   │   ├── api/routes/     # auth, interview, analysis
│   │   ├── core/           # config, security
│   │   ├── db/             # MongoDB Motor client
│   │   ├── models/         # Pydantic schemas
│   │   └── services/       # Groq, Deepgram, Firebase
│   ├── ml/                 # emotion_analysis, speech_analysis, response_evaluator
│   └── requirements.txt
│
├── .env.example
├── .gitignore
└── README.md
```

---

## Memory Footprint (8 GB RAM target)

| Process              | Approx. RAM |
|----------------------|-------------|
| FastAPI + Uvicorn    | ~120 MB     |
| FER (mtcnn=False)    | ~180 MB     |
| librosa              | ~60 MB      |
| Vite dev server      | ~80 MB      |
| MongoDB Atlas        | 0 MB (cloud)|
| **Total**            | **~440 MB** |

All heavy model downloads (e.g. MTCNN weights) are deferred to first use and cached on disk.

---

## License

MIT
