import { useState, useCallback, useEffect } from "react";
import { useNavigate, Link } from "react-router-dom";
import Navbar from "../components/Navbar";
import useAuthStore from "../store/authStore";
import useInterviewStore from "../store/interviewStore";
import { createInterview, startInterview, parseResume, setInterviewResume, listInterviews, deleteInterview } from "../services/api";
import RecruiterDashboard from "./RecruiterDashboard";

const DIFFICULTIES = ["beginner", "intermediate", "advanced"];
const INTERVIEW_TYPES = ["technical", "behavioural", "system_design", "hr"];
const QUESTION_COUNTS = [3, 5, 7, 10];

const ROLE_SUGGESTIONS = [
  "Frontend Engineer", "Backend Engineer", "Full Stack Developer",
  "Data Scientist", "ML Engineer", "DevOps Engineer",
  "Product Manager", "System Design Architect",
];

function StatusBadge({ status }) {
  const styles = {
    scheduled:   "bg-sky-500/15 border-sky-500/30 text-sky-300",
    pending:     "bg-slate-500/15 border-slate-500/30 text-slate-300",
    in_progress: "bg-amber-500/15 border-amber-500/30 text-amber-300",
    completed:   "bg-emerald-500/15 border-emerald-500/30 text-emerald-300",
    cancelled:   "bg-red-500/15 border-red-500/30 text-red-300",
  };
  return (
    <span className={`inline-flex px-2.5 py-0.5 rounded-full text-xs font-medium border ${styles[status] ?? styles.pending}`}>
      {status.replace("_", " ")}
    </span>
  );
}

export default function DashboardPage() {
  const { profile } = useAuthStore();

  // Route recruiter to their own view
  if (profile?.role === "recruiter") return <RecruiterDashboard />;

  return <CandidateView />;
}

function CandidateView() {
  const navigate   = useNavigate();
  const { user, profile } = useAuthStore();
  const setInterview = useInterviewStore((s) => s.setInterview);

  const [jobRole,      setJobRole]      = useState("");
  const [difficulty,   setDifficulty]   = useState("intermediate");
  const [interviewType, setType]        = useState("technical");
  const [numQuestions, setNumQuestions] = useState(5);
  const [resumeFile,   setResumeFile]   = useState(null);
  const [dragOver,     setDragOver]     = useState(false);
  const [loading,      setLoading]      = useState(false);
  const [loadingStep,  setLoadingStep]  = useState("");
  const [error,        setError]        = useState("");

  // Past & scheduled interviews
  const [myInterviews,    setMyInterviews]    = useState([]);
  const [listLoading,     setListLoading]     = useState(true);
  const [deletingId,      setDeletingId]      = useState(null);
  // per-card resume file for recruiter-scheduled interviews: { [interviewId]: File }
  const [scheduledResumes, setScheduledResumes] = useState({});
  const [startingId,       setStartingId]       = useState(null);

  useEffect(() => {
    listInterviews()
      .then(setMyInterviews)
      .catch(() => {})
      .finally(() => setListLoading(false));
  }, []);

  const scheduledInterviews = myInterviews.filter((i) => i.status === "scheduled");
  const pastInterviews      = myInterviews.filter((i) => i.status === "completed");

  const handleFileDrop = useCallback((e) => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer?.files?.[0] || e.target?.files?.[0];
    if (file && file.type === "application/pdf") setResumeFile(file);
  }, []);

  const handleStartScheduled = async (iv) => {
    const file = scheduledResumes[iv.id];
    if (!file) return;
    setStartingId(iv.id);
    try {
      const resumeContext = await parseResume(file);
      await setInterviewResume(iv.id, resumeContext);
      await startInterview(iv.id);
      setInterview({ ...iv, resume_context: resumeContext });
      navigate(`/interview/${iv.id}`);
    } catch (e) {
      alert(e.message);
      setStartingId(null);
    }
  };

  const handleStart = async () => {
    if (!jobRole.trim()) { setError("Please enter a target role."); return; }
    setError("");
    setLoading(true);
    try {
      let resumeContext = null;
      if (resumeFile) {
        setLoadingStep("parsing");
        resumeContext = await parseResume(resumeFile);
      }
      setLoadingStep("creating");
      const interview = await createInterview({
        user_id:        profile?.id || user?.uid,
        job_role:       jobRole.trim(),
        interview_type: interviewType,
        difficulty,
        num_questions:  numQuestions,
        resume_context: resumeContext,
      });
      await startInterview(interview.id);
      setInterview(interview);
      navigate(`/interview/${interview.id}`);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
      setLoadingStep("");
    }
  };

  const handleDelete = async (id, e) => {
    e.preventDefault();
    if (!window.confirm("Delete this interview report? This cannot be undone.")) return;
    setDeletingId(id);
    try {
      await deleteInterview(id);
      setMyInterviews((prev) => prev.filter((i) => i.id !== id));
    } catch (err) {
      alert(err.message);
    } finally {
      setDeletingId(null);
    }
  };

  const greeting = profile?.display_name?.split(" ")[0] || user?.displayName?.split(" ")[0] || "there";

  return (
    <div className="min-h-screen bg-surface-900">
      <Navbar />

      <div className="pointer-events-none fixed inset-0 overflow-hidden">
        <div className="absolute top-0 right-0 w-[500px] h-[500px] bg-brand-600/8 rounded-full blur-3xl" />
        <div className="absolute bottom-0 left-0 w-[400px] h-[400px] bg-indigo-800/8 rounded-full blur-3xl" />
      </div>

      <main className="relative max-w-5xl mx-auto px-4 sm:px-6 py-10">
        {/* Welcome */}
        <div className="mb-10 animate-slide-up">
          <h1 className="text-3xl font-bold text-white">Hey, {greeting}</h1>
          <p className="text-slate-400 mt-1">Configure your session below and launch your AI interview.</p>
        </div>

        {/* ── Scheduled interviews (from recruiter) ─────────── */}
        {scheduledInterviews.length > 0 && (
          <div className="mb-8 animate-slide-up">
            <h2 className="text-sm font-semibold text-sky-400 uppercase tracking-widest mb-3">
              Scheduled for You
            </h2>
            <div className="space-y-4">
              {scheduledInterviews.map((iv) => {
                const file       = scheduledResumes[iv.id];
                const isStarting = startingId === iv.id;
                const setFile    = (f) => setScheduledResumes((prev) => ({ ...prev, [iv.id]: f }));

                return (
                  <div key={iv.id} className="glass p-5 border border-sky-500/20">
                    {/* Interview meta */}
                    <div className="flex items-start justify-between gap-4 mb-4 flex-wrap">
                      <div>
                        <div className="flex items-center gap-2 flex-wrap mb-1">
                          <span className="text-sm font-semibold text-white">{iv.job_role}</span>
                          <StatusBadge status={iv.status} />
                        </div>
                        <p className="text-xs text-slate-500">
                          {iv.interview_type?.replace("_", " ")} · {iv.difficulty} · {iv.num_questions} questions
                        </p>
                      </div>
                    </div>

                    {/* Mandatory resume upload */}
                    <div className="mb-4">
                      <p className="text-xs font-semibold text-slate-300 uppercase tracking-widest mb-2">
                        Resume <span className="text-red-400 normal-case font-normal">(required to start)</span>
                      </p>
                      <label
                        onDragOver={(e) => e.preventDefault()}
                        onDrop={(e) => {
                          e.preventDefault();
                          const f = e.dataTransfer?.files?.[0];
                          if (f?.type === "application/pdf") setFile(f);
                        }}
                        className={`flex items-center gap-3 w-full px-4 py-3 rounded-xl border-2 border-dashed cursor-pointer transition-all ${
                          file
                            ? "border-sky-500/50 bg-sky-600/5"
                            : "border-white/10 hover:border-sky-500/40 hover:bg-white/5"
                        }`}
                      >
                        <input
                          type="file"
                          accept=".pdf"
                          className="hidden"
                          onChange={(e) => {
                            const f = e.target.files?.[0];
                            if (f?.type === "application/pdf") setFile(f);
                          }}
                        />
                        {file ? (
                          <>
                            <svg className="w-5 h-5 text-sky-400 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                            </svg>
                            <span className="text-sm text-sky-400 font-medium flex-1 truncate">{file.name}</span>
                            <button
                              type="button"
                              onClick={(e) => { e.preventDefault(); setFile(null); }}
                              className="text-xs text-slate-500 hover:text-red-400 transition-colors shrink-0"
                            >
                              Remove
                            </button>
                          </>
                        ) : (
                          <>
                            <svg className="w-5 h-5 text-slate-600 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                            </svg>
                            <span className="text-sm text-slate-400">Drop your PDF here, or <span className="text-sky-400">browse</span></span>
                          </>
                        )}
                      </label>
                    </div>

                    {/* Start button */}
                    <button
                      onClick={() => handleStartScheduled(iv)}
                      disabled={!file || isStarting}
                      className="btn-primary w-full py-2.5 text-sm disabled:opacity-40 disabled:cursor-not-allowed"
                    >
                      {isStarting ? (
                        <span className="flex items-center gap-2">
                          <span className="w-4 h-4 rounded-full border-2 border-white border-t-transparent animate-spin" />
                          Parsing resume…
                        </span>
                      ) : (
                        file ? "Start Interview" : "Upload resume to continue"
                      )}
                    </button>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        <div className="grid lg:grid-cols-5 gap-6">
          {/* ── Left column — config ───────────────────────── */}
          <div className="lg:col-span-3 space-y-5 animate-slide-up" style={{ animationDelay: "60ms" }}>

            {/* Resume upload */}
            <div className="glass p-6">
              <h2 className="text-sm font-semibold text-slate-300 uppercase tracking-widest mb-4">
                Resume (Optional)
              </h2>
              <label
                onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
                onDragLeave={() => setDragOver(false)}
                onDrop={handleFileDrop}
                className={`flex flex-col items-center justify-center gap-3 w-full h-36 rounded-xl border-2 border-dashed cursor-pointer transition-all ${
                  dragOver
                    ? "border-brand-500 bg-brand-600/10"
                    : "border-white/10 hover:border-brand-500/50 hover:bg-white/5"
                }`}
              >
                <input type="file" accept=".pdf" className="hidden" onChange={handleFileDrop} />
                {resumeFile ? (
                  <>
                    <div className="w-10 h-10 rounded-xl bg-brand-600/20 flex items-center justify-center">
                      <svg className="w-5 h-5 text-brand-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                      </svg>
                    </div>
                    <span className="text-sm text-brand-400 font-medium">{resumeFile.name}</span>
                    <button
                      type="button"
                      onClick={(e) => { e.preventDefault(); setResumeFile(null); }}
                      className="text-xs text-slate-500 hover:text-red-400 transition-colors"
                    >
                      Remove
                    </button>
                  </>
                ) : (
                  <>
                    <svg className="w-8 h-8 text-slate-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                    </svg>
                    <div className="text-center">
                      <p className="text-sm text-slate-400">Drop your PDF here, or <span className="text-brand-400">browse</span></p>
                      <p className="text-xs text-slate-600 mt-0.5">PDF up to 5 MB</p>
                    </div>
                  </>
                )}
              </label>
            </div>

            {/* Role + settings */}
            <div className="glass p-6 space-y-5">
              <h2 className="text-sm font-semibold text-slate-300 uppercase tracking-widest">
                Interview Setup
              </h2>

              <div>
                <label className="label">Target Role</label>
                <input
                  type="text"
                  value={jobRole}
                  onChange={(e) => setJobRole(e.target.value)}
                  placeholder="e.g. Data Scientist, Backend Engineer…"
                  className="input-field"
                />
                <div className="flex flex-wrap gap-2 mt-2.5">
                  {ROLE_SUGGESTIONS.map((r) => (
                    <button
                      key={r}
                      type="button"
                      onClick={() => setJobRole(r)}
                      className="text-xs px-3 py-1 rounded-full bg-surface-600 hover:bg-brand-600/20 border border-white/10 hover:border-brand-500/40 text-slate-400 hover:text-brand-300 transition-all"
                    >
                      {r}
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <label className="label">Interview Type</label>
                <div className="grid grid-cols-2 gap-2">
                  {INTERVIEW_TYPES.map((t) => (
                    <button
                      key={t}
                      type="button"
                      onClick={() => setType(t)}
                      className={`py-2.5 rounded-xl text-sm font-medium border transition-all ${
                        interviewType === t
                          ? "bg-brand-600/20 border-brand-500/60 text-brand-300"
                          : "bg-surface-600 border-white/5 text-slate-400 hover:border-white/20"
                      }`}
                    >
                      {t.replace("_", " ").replace(/\b\w/g, (c) => c.toUpperCase())}
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <label className="label">Difficulty Level</label>
                <div className="grid grid-cols-3 gap-2">
                  {DIFFICULTIES.map((d) => {
                    const colors = {
                      beginner:     "bg-emerald-500/20 border-emerald-500/50 text-emerald-300",
                      intermediate: "bg-amber-500/20 border-amber-500/50 text-amber-300",
                      advanced:     "bg-red-500/20 border-red-500/50 text-red-300",
                    };
                    return (
                      <button
                        key={d}
                        type="button"
                        onClick={() => setDifficulty(d)}
                        className={`py-2.5 rounded-xl text-sm font-medium border transition-all ${
                          difficulty === d
                            ? colors[d]
                            : "bg-surface-600 border-white/5 text-slate-400 hover:border-white/20"
                        }`}
                      >
                        {d.charAt(0).toUpperCase() + d.slice(1)}
                      </button>
                    );
                  })}
                </div>
              </div>

              <div>
                <label className="label">
                  Number of Questions
                  <span className="ml-2 text-brand-400 font-semibold">{numQuestions}</span>
                </label>
                <input
                  type="range" min={3} max={10} step={1}
                  value={numQuestions}
                  onChange={(e) => setNumQuestions(Number(e.target.value))}
                  className="w-full accent-brand-500 cursor-pointer"
                />
                <div className="flex justify-between text-xs text-slate-600 mt-1">
                  {QUESTION_COUNTS.map((n) => <span key={n}>{n}</span>)}
                </div>
              </div>
            </div>

            {error && (
              <div className="px-4 py-3 rounded-xl bg-red-500/10 border border-red-500/20 text-red-400 text-sm">
                {error}
              </div>
            )}

            <button
              onClick={() => handleStart()}
              disabled={loading || !jobRole.trim()}
              className="btn-primary w-full py-4 text-base"
            >
              {loading ? (
                <span className="flex items-center gap-2">
                  <span className="w-5 h-5 rounded-full border-2 border-white border-t-transparent animate-spin" />
                  {loadingStep === "parsing" ? "Parsing resume…" : "Generating questions…"}
                </span>
              ) : (
                <>
                  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M5.25 5.653c0-.856.917-1.398 1.667-.986l11.54 6.348a1.125 1.125 0 010 1.971l-11.54 6.347a1.125 1.125 0 01-1.667-.985V5.653z" />
                  </svg>
                  Start Interview
                </>
              )}
            </button>
          </div>

          {/* ── Right column — info cards ──────────────────── */}
          <div className="lg:col-span-2 space-y-4 animate-slide-up" style={{ animationDelay: "120ms" }}>
            <div className="glass p-5">
              <h3 className="text-sm font-semibold text-slate-300 mb-4">How It Works</h3>
              <ol className="space-y-4">
                {[
                  { n: "01", t: "AI asks questions", d: "Groq LLM generates role-specific questions read aloud via TTS." },
                  { n: "02", t: "You answer",        d: "Deepgram streams your speech to text in real time." },
                  { n: "03", t: "Live analysis",     d: "Emotion & speech metrics are captured simultaneously." },
                  { n: "04", t: "Get your report",   d: "A weighted multimodal score with detailed feedback." },
                ].map(({ n, t, d }) => (
                  <li key={n} className="flex items-start gap-3">
                    <span className="flex-shrink-0 w-7 h-7 rounded-lg bg-brand-600/20 border border-brand-500/30 flex items-center justify-center text-xs font-bold text-brand-400">
                      {n}
                    </span>
                    <div>
                      <p className="text-sm font-medium text-white">{t}</p>
                      <p className="text-xs text-slate-500 mt-0.5">{d}</p>
                    </div>
                  </li>
                ))}
              </ol>
            </div>

            <div className="glass p-5 border-amber-500/20">
              <div className="flex items-center gap-2 mb-3">
                <svg className="w-4 h-4 text-amber-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
                </svg>
                <h3 className="text-sm font-semibold text-amber-400">Proctoring Active</h3>
              </div>
              <ul className="text-xs text-slate-400 space-y-1.5">
                <li>• Camera & microphone are monitored throughout</li>
                <li>• Tab switching is detected and logged</li>
                <li>• Window minimise events are recorded</li>
                <li>• Facial emotion is analysed per question</li>
              </ul>
            </div>
          </div>
        </div>

        {/* ── Past interview reports ─────────────────────────── */}
        {(listLoading || pastInterviews.length > 0) && (
          <div className="mt-10 animate-slide-up" style={{ animationDelay: "180ms" }}>
            <h2 className="text-sm font-semibold text-slate-400 uppercase tracking-widest mb-4">
              Past Interviews
            </h2>
            {listLoading ? (
              <div className="flex justify-center py-8">
                <div className="w-7 h-7 rounded-full border-2 border-brand-500 border-t-transparent animate-spin" />
              </div>
            ) : (
              <div className="space-y-3">
                {pastInterviews.map((iv) => (
                  <div key={iv.id} className="glass p-4 flex items-center gap-4 flex-wrap">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap mb-1">
                        <span className="text-sm font-semibold text-white">{iv.job_role}</span>
                        <StatusBadge status={iv.status} />
                        {iv.overall_score != null && (
                          <span className="text-xs font-bold text-brand-400">
                            {iv.overall_score.toFixed(1)} / 10
                          </span>
                        )}
                      </div>
                      <p className="text-xs text-slate-500">
                        {iv.interview_type?.replace("_", " ")} · {iv.difficulty} · {new Date(iv.created_at).toLocaleDateString()}
                      </p>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      <Link
                        to={`/report/${iv.id}`}
                        className="text-xs px-3 py-1.5 rounded-lg bg-brand-600/20 border border-brand-500/30 text-brand-300 hover:bg-brand-600/30 transition-colors"
                      >
                        View Report
                      </Link>
                      <button
                        onClick={(e) => handleDelete(iv.id, e)}
                        disabled={deletingId === iv.id}
                        className="text-xs px-3 py-1.5 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 hover:bg-red-500/20 transition-colors disabled:opacity-50"
                      >
                        {deletingId === iv.id ? "…" : "Delete"}
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </main>
    </div>
  );
}
