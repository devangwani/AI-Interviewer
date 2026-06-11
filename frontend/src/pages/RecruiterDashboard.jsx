import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import Navbar from "../components/Navbar";
import useAuthStore from "../store/authStore";
import {
  scheduleInterview,
  getRecruiterInterviews,
  deleteInterview,
} from "../services/api";

const DIFFICULTIES    = ["beginner", "intermediate", "advanced"];
const INTERVIEW_TYPES = ["technical", "behavioural", "system_design", "hr"];
const QUESTION_COUNTS = [3, 5, 7, 10];

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

export default function RecruiterDashboard() {
  const { profile } = useAuthStore();
  const greeting = profile?.display_name?.split(" ")[0] || "there";

  const [interviews,    setInterviews]    = useState([]);
  const [listLoading,   setListLoading]   = useState(true);
  const [deletingId,    setDeletingId]    = useState(null);

  // Schedule form state
  const [candidateName,  setCandidateName]  = useState("");
  const [candidateEmail, setCandidateEmail] = useState("");
  const [jobRole,        setJobRole]        = useState("");
  const [difficulty,     setDifficulty]     = useState("intermediate");
  const [interviewType,  setType]           = useState("technical");
  const [numQuestions,   setNumQuestions]   = useState(5);
  const [scheduling,     setScheduling]     = useState(false);
  const [scheduleError,  setScheduleError]  = useState("");
  const [scheduleOk,     setScheduleOk]     = useState("");

  const loadInterviews = async () => {
    try {
      const data = await getRecruiterInterviews();
      setInterviews(data);
    } catch { /* non-fatal */ }
    finally { setListLoading(false); }
  };

  useEffect(() => { loadInterviews(); }, []);

  const handleSchedule = async (e) => {
    e.preventDefault();
    if (!candidateEmail.trim() || !jobRole.trim()) return;
    setScheduling(true);
    setScheduleError("");
    setScheduleOk("");
    try {
      await scheduleInterview({
        candidate_name:  candidateName.trim(),
        candidate_email: candidateEmail.trim(),
        job_role:        jobRole.trim(),
        interview_type:  interviewType,
        difficulty,
        num_questions:   numQuestions,
      });
      const label = candidateName.trim() || candidateEmail.trim();
      setScheduleOk(`Interview scheduled for ${label}.`);
      setCandidateName("");
      setCandidateEmail("");
      setJobRole("");
      loadInterviews();
    } catch (e) {
      setScheduleError(e.message);
    } finally {
      setScheduling(false);
    }
  };

  const handleDelete = async (id) => {
    if (!window.confirm("Delete this interview and its report? This cannot be undone.")) return;
    setDeletingId(id);
    try {
      await deleteInterview(id);
      setInterviews((prev) => prev.filter((i) => i.id !== id));
    } catch (e) {
      alert(e.message);
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <div className="min-h-screen bg-surface-900">
      <Navbar />

      <div className="pointer-events-none fixed inset-0 overflow-hidden">
        <div className="absolute top-0 right-0 w-[500px] h-[500px] bg-emerald-600/8 rounded-full blur-3xl" />
        <div className="absolute bottom-0 left-0 w-[400px] h-[400px] bg-brand-800/8 rounded-full blur-3xl" />
      </div>

      <main className="relative max-w-5xl mx-auto px-4 sm:px-6 py-10">
        {/* Header */}
        <div className="mb-10 animate-slide-up">
          <div className="flex items-center gap-2 mb-1">
            <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-500/15 border border-emerald-500/30 text-emerald-400">
              Recruiter
            </span>
          </div>
          <h1 className="text-3xl font-bold text-white">Hey, {greeting}</h1>
          <p className="text-slate-400 mt-1">Schedule interviews for candidates and review their results.</p>
        </div>

        <div className="grid lg:grid-cols-5 gap-6">
          {/* ── Schedule form ──────────────────────────────── */}
          <div className="lg:col-span-2 animate-slide-up" style={{ animationDelay: "60ms" }}>
            <form onSubmit={handleSchedule} className="glass p-6 space-y-5">
              <h2 className="text-sm font-semibold text-slate-300 uppercase tracking-widest">
                Schedule Interview
              </h2>

              <div>
                <label className="label">Candidate Name</label>
                <input
                  type="text"
                  value={candidateName}
                  onChange={(e) => setCandidateName(e.target.value)}
                  placeholder="e.g. Rahul Sharma"
                  className="input-field"
                />
              </div>

              <div>
                <label className="label">Candidate Email</label>
                <input
                  type="email"
                  required
                  value={candidateEmail}
                  onChange={(e) => setCandidateEmail(e.target.value)}
                  placeholder="candidate@example.com"
                  className="input-field"
                />
              </div>

              <div>
                <label className="label">Target Role</label>
                <input
                  type="text"
                  required
                  value={jobRole}
                  onChange={(e) => setJobRole(e.target.value)}
                  placeholder="e.g. Backend Engineer"
                  className="input-field"
                />
              </div>

              <div>
                <label className="label">Interview Type</label>
                <div className="grid grid-cols-2 gap-2">
                  {INTERVIEW_TYPES.map((t) => (
                    <button
                      key={t}
                      type="button"
                      onClick={() => setType(t)}
                      className={`py-2 rounded-xl text-xs font-medium border transition-all ${
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
                <label className="label">Difficulty</label>
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
                        className={`py-2 rounded-xl text-xs font-medium border transition-all ${
                          difficulty === d ? colors[d] : "bg-surface-600 border-white/5 text-slate-400 hover:border-white/20"
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
                  Questions
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

              {scheduleError && (
                <div className="px-4 py-3 rounded-xl bg-red-500/10 border border-red-500/20 text-red-400 text-sm">
                  {scheduleError}
                </div>
              )}
              {scheduleOk && (
                <div className="px-4 py-3 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-sm">
                  {scheduleOk}
                </div>
              )}

              <button
                type="submit"
                disabled={scheduling || !candidateEmail.trim() || !jobRole.trim()}
                className="btn-primary w-full py-3"
              >
                {scheduling ? (
                  <span className="flex items-center gap-2">
                    <span className="w-4 h-4 rounded-full border-2 border-white border-t-transparent animate-spin" />
                    Scheduling…
                  </span>
                ) : "Schedule Interview"}
              </button>
            </form>
          </div>

          {/* ── Scheduled / completed list ──────────────────── */}
          <div className="lg:col-span-3 animate-slide-up" style={{ animationDelay: "120ms" }}>
            <div className="glass p-6">
              <h2 className="text-sm font-semibold text-slate-300 uppercase tracking-widest mb-5">
                Your Interviews
              </h2>

              {listLoading ? (
                <div className="flex justify-center py-10">
                  <div className="w-8 h-8 rounded-full border-2 border-brand-500 border-t-transparent animate-spin" />
                </div>
              ) : interviews.length === 0 ? (
                <div className="text-center py-12 text-slate-500 text-sm">
                  No interviews scheduled yet.
                </div>
              ) : (
                <div className="space-y-3">
                  {interviews.map((iv) => (
                    <div key={iv.id} className="bg-surface-700/60 rounded-xl p-4 border border-white/5 flex items-start gap-4">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap mb-1">
                          <span className="text-sm font-semibold text-white truncate">{iv.job_role}</span>
                          <StatusBadge status={iv.status} />
                        </div>
                        {iv.candidate_name && (
                          <p className="text-xs text-slate-300 font-medium mb-0.5">{iv.candidate_name}</p>
                        )}
                        <p className="text-xs text-slate-500">
                          {iv.interview_type?.replace("_", " ")} · {iv.difficulty} · {iv.num_questions} questions
                        </p>
                        <p className="text-xs text-slate-600 mt-0.5">
                          {new Date(iv.created_at).toLocaleDateString()}
                        </p>
                      </div>

                      <div className="flex items-center gap-2 shrink-0">
                        {iv.status === "completed" && (
                          <Link
                            to={`/report/${iv.id}`}
                            className="text-xs px-3 py-1.5 rounded-lg bg-brand-600/20 border border-brand-500/30 text-brand-300 hover:bg-brand-600/30 transition-colors"
                          >
                            View Report
                          </Link>
                        )}
                        <button
                          onClick={() => handleDelete(iv.id)}
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
          </div>
        </div>
      </main>
    </div>
  );
}
