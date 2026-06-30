# Real-Time Multimodal AI Interview Framework

An end-to-end AI-powered interview platform that evaluates candidates across **three simultaneous modalities** — spoken language (Deepgram STT), facial emotion (MobileNetV2 CNN), and answer quality (Groq LLM) — and produces a unified weighted performance report with academic integrity analysis.

Designed to run natively on an 8 GB RAM Windows machine: no Docker, no local databases.

---

## Features

- **Two-role system** — Candidates self-schedule or accept recruiter-scheduled interviews; Recruiters create and manage interviews for specific candidates
- **Resume-aware questioning** — Upload a PDF resume; Groq parses skills and projects and weaves them into personalised questions
- **Three interview types** — Technical (depth-based), Behavioural (STAR-method only), HR/Culture-fit
- **Three difficulty levels** — Beginner, Intermediate, Advanced with type-specific guidance
- **Real-time emotion analysis** — MobileNetV2 (fine-tuned on RAF-DB, 7 classes) with Haar Cascade face detection; tracks full softmax probability distributions across frames
- **Presence detection** — Flags candidates who leave camera view; absence rate shown in report
- **Academic integrity detection** — Two-layer system: keyword patterns (14 regexes) + linguistic naturalness scoring (5 metrics); injected as objective facts into LLM prompt
- **Multimodal report card** — Weighted composite score (Communication 25%, Technical 35%, Confidence 25%, Visual Confidence 15%) with hire/maybe/no-hire verdict
- **Three-mode theming** — Dark, Light, Aesthetic (warm rose palette)
- **One-time role switching** — Users can switch between Candidate and Recruiter exactly once

---

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                   React 18 + Vite  (port 5173)               │
│                                                              │
│  Login → RoleSelect → Dashboard → InterviewPage → ReportPage │
│                          │                                   │
│               Candidate  │  Recruiter                        │
│               (self /    │  (schedule for                    │
│                scheduled)│   candidates)                     │
└──────────────────────────┼───────────────────────────────────┘
                           │  Single WebSocket per session
                           │  ws://{host}/api/v1/interviews/ws/{id}
                           │
                           │  ① PCM audio bytes → Deepgram STT
                           │  ② base64 JPEG frames → MobileNetV2
                           │  ③ end_answer JSON → Groq next question
                           ▼
┌──────────────────────────────────────────────────────────────┐
│                  FastAPI + Uvicorn  (port 8000)               │
│                                                              │
│  auth  │  interviews  │  analysis                            │
│                                                              │
│  ┌──────────────────┐   ┌────────────────────────────────┐  │
│  │   Service Layer  │   │         ML Layer               │  │
│  │  groq_service    │   │  emotion_analysis.py           │  │
│  │  resume_service  │   │  MobileNetV2 + Haar Cascade    │  │
│  │  deepgram_service│   │  app/ml/models/*.h5            │  │
│  │  evaluation_svc  │   └────────────────────────────────┘  │
│  └──────────────────┘                                        │
└──────────────────────────┬───────────────────────────────────┘
                           │
          ┌────────────────┼──────────────────┐
          ▼                ▼                  ▼
   ┌────────────┐  ┌──────────────┐  ┌──────────────┐
   │  Deepgram  │  │  Groq API    │  │ MongoDB Atlas│
   │  Nova-2    │  │ gpt-oss-120b │  │  (cloud)     │
   └────────────┘  └──────────────┘  └──────────────┘
          ▲
   ┌──────────────┐
   │   Firebase   │
   │   Auth       │
   └──────────────┘
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React 18, Vite, Zustand (persist), Tailwind CSS, react-router-dom v6 |
| Backend | FastAPI, Uvicorn (port 8000), Python 3.10 |
| Database | MongoDB Atlas (cloud) via Motor async driver |
| Auth | Firebase Authentication (Google + email/password) |
| LLM | Groq API — `openai/gpt-oss-120b` |
| STT | Deepgram Nova-2 (real-time WebSocket stream) |
| TTS | Web Speech API (`window.speechSynthesis`) |
| Emotion | MobileNetV2 fine-tuned on RAF-DB (7 classes) via tensorflow-cpu |
| Face detection | OpenCV Haar Cascade (`haarcascade_frontalface_default.xml`) |
| Audio analysis | librosa + soundfile |
| PDF parsing | pdfplumber 0.11.0 |

---

## Prerequisites

- **Python 3.10+** — `python --version`
- **Node.js 18+** — `node --version`
- **npm 9+** — `npm --version`
- A [MongoDB Atlas](https://www.mongodb.com/atlas) free cluster
- API keys for [Groq](https://console.groq.com), [Deepgram](https://console.deepgram.com), and [Firebase](https://console.firebase.google.com)

---

## Local Setup

### 1. Clone the repository

```bash
git clone https://github.com/devangwani/AI-Interviewer.git
cd AI-Interviewer
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

Create `backend/.env`:

```env
MONGO_URI=mongodb+srv://<user>:<pass>@<cluster>.mongodb.net/<dbname>?retryWrites=true&w=majority
GROQ_API_KEY=your_groq_api_key
DEEPGRAM_API_KEY=your_deepgram_api_key
FIREBASE_CREDENTIALS={"type":"service_account", ...}   # paste Firebase Admin SDK JSON
```

### 3. Frontend setup

```bash
cd frontend
npm install
```

Create `frontend/.env.local`:

```env
VITE_API_BASE_URL=http://localhost:8000
VITE_FIREBASE_API_KEY=your_key
VITE_FIREBASE_AUTH_DOMAIN=your_project.firebaseapp.com
VITE_FIREBASE_PROJECT_ID=your_project_id
VITE_FIREBASE_STORAGE_BUCKET=your_project.appspot.com
VITE_FIREBASE_MESSAGING_SENDER_ID=your_sender_id
VITE_FIREBASE_APP_ID=your_app_id
```

### 4. Run the backend

```bash
# From backend/ with venv active
python run.py
```

API available at `http://localhost:8000` — interactive docs at `http://localhost:8000/docs`

### 5. Run the frontend

```bash
# From frontend/
npm run dev
```

App available at `http://localhost:5173`

---

## API Routes

### Auth
| Method | Path | Description |
|---|---|---|
| POST | `/api/v1/auth/login` | Firebase token → upsert user in DB |
| GET | `/api/v1/auth/me` | Get current user profile |
| PATCH | `/api/v1/auth/me/role` | Set role for first time (candidate/recruiter) |
| POST | `/api/v1/auth/me/switch-role` | One-time role switch (enforced server-side) |
| GET | `/api/v1/auth/user-by-email` | Recruiter lookup of candidate by email |

### Interviews
| Method | Path | Description |
|---|---|---|
| POST | `/api/v1/interviews/` | Create self-scheduled interview |
| GET | `/api/v1/interviews/` | List candidate's own interviews |
| GET | `/api/v1/interviews/recruiter` | List interviews scheduled by recruiter |
| POST | `/api/v1/interviews/schedule` | Recruiter schedules interview for candidate |
| POST | `/api/v1/interviews/parse-resume` | Parse PDF resume → skills + projects JSON |
| GET | `/api/v1/interviews/{id}` | Get interview detail |
| DELETE | `/api/v1/interviews/{id}` | Delete interview (owner or scheduling recruiter) |
| PATCH | `/api/v1/interviews/{id}/resume-context` | Attach parsed resume to scheduled interview |
| WS | `/api/v1/interviews/ws/{id}` | Real-time session (audio + video + Q generation) |

### Analysis
| Method | Path | Description |
|---|---|---|
| GET | `/api/v1/analysis/{id}/report` | Multimodal report card for completed interview |

---

## Scoring System

| Dimension | Weight | Source |
|---|---|---|
| Communication | 25% | Deepgram transcript — fluency, clarity, pace |
| Technical / Behavioural | 35% | Groq LLM answer evaluation per question |
| Confidence | 25% | Audio metrics (pace, filler words, pauses) |
| Visual Confidence | 15% | Emotion CNN — Happiness/Neutral vs Sadness/Fear ratio |

**Hire thresholds:** ≥ 75 → Hire · 55–74 → Maybe · < 55 → No Hire

**Presence rate:** `frames_with_face / total_video_frames × 100` — shown as colour-coded bar; < 70% triggers absence warning; < 40% triggers critical warning.

**Academic integrity:** Two layers injected as objective facts into the report-card prompt:
1. 14 regex patterns for explicit AI self-disclosure
2. 5 linguistic naturalness metrics (disfluency rate, enumerative structure, AI hedging phrases, personal anecdotes, sentence completeness) → naturalness score 0–10
Risk levels: HIGH (naturalness ≤ 2) / MEDIUM (naturalness ≤ 4) / LOW

---

## Project Structure

```
AI-Interviewer/
├── frontend/
│   └── src/
│       ├── components/        # Navbar, ProtectedRoute
│       ├── pages/             # Login, RoleSelect, Dashboard, RecruiterDashboard,
│       │                      #   InterviewPage, ReportPage
│       ├── hooks/             # useWebRTC, useInterviewWS, useSpeechSynthesis,
│       │                      #   useVisibility
│       ├── services/          # api.js (Axios + Firebase token interceptor)
│       └── store/             # authStore, themeStore (Zustand persist)
│
├── backend/
│   ├── app/
│   │   ├── api/routes/        # auth.py, interview.py, analysis.py
│   │   ├── core/              # config.py, security.py
│   │   ├── db/                # MongoDB Motor client
│   │   ├── models/            # Pydantic schemas (user, interview)
│   │   ├── ml/
│   │   │   ├── emotion_analysis.py   # MobileNetV2 + Haar Cascade
│   │   │   └── models/
│   │   │       └── mobilenet_emotion_model.h5
│   │   └── services/
│   │       ├── groq_service.py        # Question generation + answer evaluation
│   │       ├── resume_service.py      # pdfplumber + Groq JSON extraction
│   │       └── evaluation_service.py  # Report card + integrity analysis
│   ├── ml/                    # speech_analysis.py, response_evaluator.py
│   └── requirements.txt
│
├── .gitignore
└── README.md
```

---

## Memory Footprint (8 GB RAM target)

| Process | Approx. RAM |
|---|---|
| FastAPI + Uvicorn | ~120 MB |
| tensorflow-cpu + MobileNetV2 | ~350 MB |
| OpenCV (Haar Cascade) | ~15 MB |
| librosa | ~60 MB |
| Vite dev server | ~80 MB |
| MongoDB Atlas | 0 MB (cloud) |
| **Total** | **~625 MB** |

---

## Key Implementation Notes

- **Deepgram lazy-connection** — Deepgram WebSocket opens on the first audio byte per question, not at session start. Upfront connection times out during TTS playback.
- **Emotion model preprocessing** — Model was trained with `rescale=1./255`; inference uses `rgb / 255.0`. Using MobileNetV2's native `preprocess_input` (`(x/127.5)-1`) causes 100% Neutral output.
- **Emotion stats** — Stored as softmax probability float sums across all 7 classes per frame (not top-1 counts), so secondary emotions are proportionally represented.
- **Groq cache defeat** — A UUID nonce is injected into the system prompt prefix `[sid:{nonce}]` on every session, defeating Groq's system-prompt-level response cache.
- **Role switch** — `role_switch_count` is enforced server-side via MongoDB `$inc`; the UI hides the option once count reaches 1.

---

## License

MIT
