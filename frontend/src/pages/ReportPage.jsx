import { useEffect, useState } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import Navbar from "../components/Navbar";
import useInterviewStore from "../store/interviewStore";
import { getAnalysisReport, deleteInterview } from "../services/api";

// ── Small reusable components ─────────────────────────────────────────────────

function ScoreRing({ score, label, size = 110 }) {
  const pct  = Math.min((score ?? 0) / 10, 1);
  const r    = (size - 16) / 2;
  const circ = 2 * Math.PI * r;
  const color =
    pct >= 0.75 ? "#22c55e" : pct >= 0.5 ? "#f59e0b" : "#ef4444";

  return (
    <div className="flex flex-col items-center gap-2">
      <div className="relative flex items-center justify-center" style={{ width: size, height: size }}>
        <svg width={size} height={size} style={{ transform: "rotate(-90deg)" }}>
          <circle cx={size/2} cy={size/2} r={r} fill="none" stroke="#1f1f35" strokeWidth={8} />
          <circle
            cx={size/2} cy={size/2} r={r}
            fill="none" stroke={color} strokeWidth={8}
            strokeDasharray={`${circ * pct} ${circ * (1 - pct)}`}
            strokeLinecap="round"
            style={{ transition: "stroke-dasharray 1.2s ease" }}
          />
        </svg>
        <div className="absolute flex flex-col items-center">
          <span className="text-xl font-bold text-white">{score != null ? score.toFixed(1) : "–"}</span>
          <span className="text-xs text-slate-500">/ 10</span>
        </div>
      </div>
      <p className="text-xs text-slate-400 text-center">{label}</p>
    </div>
  );
}

function MetricBar({ label, value, max = 10 }) {
  const pct   = Math.min((value ?? 0) / max, 1) * 100;
  const color = pct >= 75 ? "bg-emerald-500" : pct >= 50 ? "bg-amber-500" : "bg-red-500";
  return (
    <div>
      <div className="flex justify-between mb-1">
        <span className="text-xs text-slate-400">{label}</span>
        <span className="text-xs font-medium text-white">{value != null ? value.toFixed(1) : "–"}</span>
      </div>
      <div className="h-1.5 bg-surface-600 rounded-full overflow-hidden">
        <div className={`h-full ${color} rounded-full transition-all duration-700`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

function Tag({ children, color = "slate" }) {
  const palette = {
    green:  "bg-emerald-500/15 border-emerald-500/30 text-emerald-300",
    red:    "bg-red-500/15 border-red-500/30 text-red-300",
    amber:  "bg-amber-500/15 border-amber-500/30 text-amber-300",
    brand:  "bg-brand-500/15 border-brand-500/30 text-brand-300",
    slate:  "bg-surface-600 border-white/10 text-slate-400",
  };
  return (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium border ${palette[color] ?? palette.slate}`}>
      {children}
    </span>
  );
}

function ScoreBreakdown({ label, score, items, accentColor = "brand" }) {
  if (!items || items.length === 0) return null;

  const accent = {
    brand:   { border: "border-brand-500/20",   header: "text-brand-400",   dot: "bg-brand-400"   },
    emerald: { border: "border-emerald-500/20", header: "text-emerald-400", dot: "bg-emerald-400" },
    sky:     { border: "border-sky-500/20",     header: "text-sky-400",     dot: "bg-sky-400"     },
    violet:  { border: "border-violet-500/20",  header: "text-violet-400",  dot: "bg-violet-400"  },
  }[accentColor] ?? { border: "border-white/10", header: "text-slate-300", dot: "bg-slate-400" };

  return (
    <div className={`glass p-5 border ${accent.border}`}>
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <p className={`text-xs font-semibold uppercase tracking-widest ${accent.header}`}>
          {label}
        </p>
        <span className="text-lg font-bold text-white">
          {score != null ? score.toFixed(1) : "–"}
          <span className="text-xs text-slate-500 font-normal"> / 10</span>
        </span>
      </div>

      {/* Criteria rows */}
      <div className="space-y-3">
        {items.map((item, i) => (
          <div key={i} className="flex items-start gap-3">
            {/* Met / not met icon */}
            <div className={`mt-0.5 shrink-0 w-5 h-5 rounded-full flex items-center justify-center text-xs font-bold ${
              item.met
                ? "bg-emerald-500/20 text-emerald-400"
                : "bg-red-500/20 text-red-400"
            }`}>
              {item.met ? "✓" : "✗"}
            </div>

            <div className="flex-1 min-w-0">
              <div className="flex items-center justify-between gap-2">
                <span className={`text-xs font-medium ${item.met ? "text-slate-200" : "text-slate-400"}`}>
                  {item.criterion}
                </span>
                {/* Point impact badge */}
                <span className={`shrink-0 text-xs font-bold px-1.5 py-0.5 rounded ${
                  item.met
                    ? "text-emerald-400 bg-emerald-500/10"
                    : "text-red-400 bg-red-500/10"
                }`}>
                  {item.impact}
                </span>
              </div>
              {item.note && (
                <p className="text-xs text-slate-500 mt-0.5 leading-relaxed">{item.note}</p>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function ReportPage() {
  const { id: interviewId } = useParams();
  const navigate = useNavigate();
  const { report: storedReport, reset } = useInterviewStore();
  const [report,    setReport]    = useState(storedReport);
  const [loading,   setLoading]   = useState(!storedReport);
  const [deleting,  setDeleting]  = useState(false);

  useEffect(() => {
    if (!storedReport) {
      getAnalysisReport(interviewId)
        .then(setReport)
        .catch(() => navigate("/dashboard"))
        .finally(() => setLoading(false));
    }
  }, [interviewId, storedReport, navigate]);

  if (loading) {
    return (
      <div className="min-h-screen bg-surface-900 flex flex-col">
        <Navbar />
        <div className="flex-1 flex items-center justify-center">
          <div className="flex flex-col items-center gap-4">
            <div className="w-10 h-10 rounded-full border-2 border-brand-500 border-t-transparent animate-spin" />
            <p className="text-slate-400 text-sm">Loading report…</p>
          </div>
        </div>
      </div>
    );
  }

  if (!report) return null;

  const handleDelete = async () => {
    if (!window.confirm("Delete this report permanently? This cannot be undone.")) return;
    setDeleting(true);
    try {
      await deleteInterview(interviewId);
      reset();
      navigate("/dashboard");
    } catch (e) {
      alert(e.message);
      setDeleting(false);
    }
  };

  const handleDownload = () => window.print();

  const {
    overall_score,
    communication_score,    communication_breakdown     = [],
    technical_score,        technical_breakdown         = [],
    confidence_score,       confidence_breakdown        = [],
    visual_confidence_score, visual_confidence_breakdown = [],
    verdict,
    summary,
    visual_insight,
    strengths        = [],
    improvements     = [],
    emotion_summary,
    emotion_stats    = {},
    per_question     = [],
    job_role,
    candidate_name,
    presence_rate,
    absence_warning,
  } = report;

  // presence_rate is 0–100 (percentage of frames where face was detected).
  // null / undefined means legacy report with no presence data.
  const hasPresenceData   = presence_rate != null;
  const lowPresence       = hasPresenceData && presence_rate < 70;
  const criticalAbsence   = hasPresenceData && presence_rate < 40;

  // ── Verdict badge styling ─────────────────────────────────
  const verdictStyle = {
    "Strong Hire": "bg-emerald-500/10 border-emerald-500/30 text-emerald-400",
    "Hire":        "bg-green-500/10  border-green-500/30  text-green-400",
    "Maybe":       "bg-amber-500/10  border-amber-500/30  text-amber-400",
    "No Hire":     "bg-red-500/10    border-red-500/30    text-red-400",
  }[verdict] ?? "bg-surface-600 border-white/10 text-slate-400";

  // ── Emotion stats bar chart data ──────────────────────────
  const emotionTotal  = Object.values(emotion_stats).reduce((a, b) => a + b, 0);
  const emotionBars   = Object.entries(emotion_stats)
    .sort((a, b) => b[1] - a[1])
    .map(([label, count]) => ({
      label,
      pct: emotionTotal ? Math.round((count / emotionTotal) * 100) : 0,
    }));

  const emotionColor = (label) => ({
    Happiness: "bg-emerald-500",
    Neutral:   "bg-sky-500",
    Surprise:  "bg-violet-500",
    Fear:      "bg-red-400",
    Sadness:   "bg-blue-400",
    Disgust:   "bg-orange-400",
    Anger:     "bg-rose-600",
  }[label] ?? "bg-slate-500");

  return (
    <div className="min-h-screen bg-surface-900">
      <Navbar />

      {/* Ambient glow */}
      <div className="pointer-events-none fixed inset-0 overflow-hidden">
        <div className="absolute top-0 right-0 w-[500px] h-[500px] bg-brand-600/6 rounded-full blur-3xl" />
      </div>

      <main className="relative max-w-5xl mx-auto px-4 sm:px-6 py-10 space-y-6">

        {/* ── Hero ───────────────────────────────────────────── */}
        <div className="text-center animate-fade-in">
          <div className={`inline-flex items-center gap-2 px-4 py-1.5 rounded-full border text-sm font-semibold mb-3 ${verdictStyle}`}>
            {verdict ?? "Interview Complete"}
          </div>
          <h1 className="text-3xl font-bold text-white">Interview Report</h1>
          {candidate_name && (
            <p className="text-white font-semibold mt-1">{candidate_name}</p>
          )}
          {job_role && (
            <p className="text-slate-400 mt-0.5 text-sm">{job_role}</p>
          )}
        </div>

        {/* ── Absence warning banner ─────────────────────────── */}
        {lowPresence && (
          <div className={`rounded-xl border px-5 py-4 animate-fade-in ${
            criticalAbsence
              ? "bg-red-500/10 border-red-500/30"
              : "bg-amber-500/10 border-amber-500/30"
          }`}>
            <div className="flex items-start gap-3">
              <svg className={`w-5 h-5 mt-0.5 shrink-0 ${criticalAbsence ? "text-red-400" : "text-amber-400"}`}
                fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round"
                  d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
              </svg>
              <div>
                <p className={`text-sm font-semibold mb-1 ${criticalAbsence ? "text-red-300" : "text-amber-300"}`}>
                  {criticalAbsence ? "Critical: Low Camera Presence" : "Low Camera Presence Detected"}
                </p>
                <p className={`text-xs leading-relaxed ${criticalAbsence ? "text-red-200/80" : "text-amber-200/80"}`}>
                  {absence_warning
                    ? absence_warning
                    : `The candidate's face was detected in only ${presence_rate.toFixed(1)}% of video frames. Visual confidence scores may not reflect the candidate's true demeanour.`}
                </p>
              </div>
            </div>
          </div>
        )}

        {/* ── Score rings ────────────────────────────────────── */}
        <div className="glass p-6 animate-slide-up">
          <p className="text-xs font-semibold text-slate-400 uppercase tracking-widest mb-6">
            Performance Scores
          </p>
          <div className="grid grid-cols-2 sm:grid-cols-5 gap-6 justify-items-center">
            <ScoreRing score={overall_score}           label="Overall"          size={120} />
            <ScoreRing score={communication_score}     label="Communication"    />
            <ScoreRing score={technical_score}         label="Technical"        />
            <ScoreRing score={confidence_score}        label="Confidence"       />
            <ScoreRing score={visual_confidence_score} label="Visual Confidence"/>
          </div>
        </div>

        {/* ── Explainable Score Breakdowns ───────────────────── */}
        {(communication_breakdown.length > 0 || technical_breakdown.length > 0 ||
          confidence_breakdown.length > 0 || visual_confidence_breakdown.length > 0) && (
          <div className="animate-slide-up" style={{ animationDelay: "80ms" }}>
            <p className="text-xs font-semibold text-slate-400 uppercase tracking-widest mb-3 px-1">
              Score Breakdown — Where Points Were Gained & Lost
            </p>
            <div className="grid sm:grid-cols-2 gap-4">
              <ScoreBreakdown
                label="Communication"
                score={communication_score}
                items={communication_breakdown}
                accentColor="emerald"
              />
              <ScoreBreakdown
                label="Technical"
                score={technical_score}
                items={technical_breakdown}
                accentColor="brand"
              />
              <ScoreBreakdown
                label="Confidence"
                score={confidence_score}
                items={confidence_breakdown}
                accentColor="sky"
              />
              <ScoreBreakdown
                label="Visual Confidence"
                score={visual_confidence_score}
                items={visual_confidence_breakdown}
                accentColor="violet"
              />
            </div>
          </div>
        )}

        {/* ── AI Summary + Visual Insight ────────────────────── */}
        <div className="grid sm:grid-cols-2 gap-4 animate-slide-up" style={{ animationDelay: "60ms" }}>

          {summary && (
            <div className="glass p-5">
              <p className="text-xs font-semibold text-slate-400 uppercase tracking-widest mb-3">
                AI Assessment
              </p>
              <p className="text-sm text-slate-300 leading-relaxed">{summary}</p>
            </div>
          )}

          {visual_insight && (
            <div className="glass p-5 border border-brand-500/20">
              <p className="text-xs font-semibold text-brand-400 uppercase tracking-widest mb-3">
                Visual Confidence Insight
              </p>
              <p className="text-sm text-slate-300 leading-relaxed">{visual_insight}</p>
            </div>
          )}
        </div>

        {/* ── Emotion distribution (CNN data) ────────────────── */}
        {(emotionBars.length > 0 || hasPresenceData) && (
          <div className="glass p-5 animate-slide-up" style={{ animationDelay: "100ms" }}>
            <div className="flex items-center justify-between mb-4">
              <p className="text-xs font-semibold text-slate-400 uppercase tracking-widest">
                Facial Emotion Distribution
              </p>
              <span className="text-xs text-slate-500">{emotionTotal} face-frames analysed</span>
            </div>

            {/* Presence rate bar */}
            {hasPresenceData && (
              <div className="mb-4 pb-4 border-b border-white/5">
                <div className="flex items-center justify-between mb-1.5">
                  <span className="text-xs text-slate-400">Camera Presence</span>
                  <span className={`text-xs font-semibold ${
                    criticalAbsence ? "text-red-400" : lowPresence ? "text-amber-400" : "text-emerald-400"
                  }`}>
                    {presence_rate.toFixed(1)}% of frames
                  </span>
                </div>
                <div className="h-2 bg-surface-600 rounded-full overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all duration-700 ${
                      criticalAbsence ? "bg-red-500" : lowPresence ? "bg-amber-500" : "bg-emerald-500"
                    }`}
                    style={{ width: `${Math.min(presence_rate, 100)}%` }}
                  />
                </div>
                <p className="text-xs text-slate-500 mt-1">
                  {criticalAbsence
                    ? "Very low — visual analysis is unreliable for this session."
                    : lowPresence
                    ? "Below recommended threshold (70%). Visual scores are partial."
                    : "Good — candidate was consistently on camera."}
                </p>
              </div>
            )}

            {emotionBars.length > 0 ? (
              <div className="space-y-2.5">
                {emotionBars.map(({ label, pct }) => (
                  <div key={label} className="flex items-center gap-3">
                    <span className="w-20 text-xs text-slate-400 shrink-0">{label}</span>
                    <div className="flex-1 h-2 bg-surface-600 rounded-full overflow-hidden">
                      <div
                        className={`h-full rounded-full transition-all duration-700 ${emotionColor(label)}`}
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                    <span className="w-8 text-xs text-slate-400 text-right">{pct}%</span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-xs text-slate-500 italic">
                No emotion data — no face was detected in any video frame.
              </p>
            )}

            {/* Emotion summary from LLM */}
            {emotion_summary && (
              <div className="mt-4 pt-4 border-t border-white/5 flex flex-wrap gap-3 items-start">
                <div className="flex gap-2 flex-wrap">
                  {emotion_summary.dominant_emotion && (
                    <Tag color="brand">Dominant: {emotion_summary.dominant_emotion}</Tag>
                  )}
                  {emotion_summary.positive_frames_pct != null && (
                    <Tag color="green">Positive {emotion_summary.positive_frames_pct.toFixed(0)}%</Tag>
                  )}
                  {emotion_summary.stress_frames_pct != null && (
                    <Tag color="red">Stress {emotion_summary.stress_frames_pct.toFixed(0)}%</Tag>
                  )}
                </div>
                {emotion_summary.interpretation && (
                  <p className="w-full text-xs text-slate-400 italic mt-1">
                    {emotion_summary.interpretation}
                  </p>
                )}
              </div>
            )}
          </div>
        )}

        {/* ── Strengths & Improvements ───────────────────────── */}
        {(strengths.length > 0 || improvements.length > 0) && (
          <div className="grid sm:grid-cols-2 gap-4 animate-slide-up" style={{ animationDelay: "140ms" }}>

            {strengths.length > 0 && (
              <div className="glass p-5">
                <p className="text-xs font-semibold text-emerald-400 uppercase tracking-widest mb-3">
                  Strengths
                </p>
                <ul className="space-y-2">
                  {strengths.map((s, i) => (
                    <li key={i} className="flex items-start gap-2 text-sm text-slate-300">
                      <span className="mt-1 w-1.5 h-1.5 rounded-full bg-emerald-400 shrink-0" />
                      {s}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {improvements.length > 0 && (
              <div className="glass p-5">
                <p className="text-xs font-semibold text-amber-400 uppercase tracking-widest mb-3">
                  Areas to Improve
                </p>
                <ul className="space-y-2">
                  {improvements.map((s, i) => (
                    <li key={i} className="flex items-start gap-2 text-sm text-slate-300">
                      <span className="mt-1 w-1.5 h-1.5 rounded-full bg-amber-400 shrink-0" />
                      {s}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}

        {/* ── Per-question breakdown ─────────────────────────── */}
        {per_question.length > 0 && (
          <div className="glass p-6 animate-slide-up" style={{ animationDelay: "180ms" }}>
            <p className="text-xs font-semibold text-slate-400 uppercase tracking-widest mb-5">
              Question-by-Question Breakdown
            </p>
            <div className="space-y-4">
              {per_question.map((qa, i) => {
                const score = qa.score ?? qa.llm_score;
                const scoreColor =
                  score >= 7.5 ? "text-emerald-400 bg-emerald-500/10 border-emerald-500/30"
                  : score >= 5  ? "text-amber-400 bg-amber-500/10 border-amber-500/30"
                  :               "text-red-400 bg-red-500/10 border-red-500/30";

                return (
                  <div key={i} className="bg-surface-700/50 rounded-xl p-5 border border-white/5">
                    <div className="flex items-start justify-between gap-4 mb-3">
                      <div className="flex items-start gap-3 flex-1">
                        <span className="shrink-0 w-6 h-6 rounded-md bg-brand-600/20 border border-brand-500/30 flex items-center justify-center text-xs font-bold text-brand-400 mt-0.5">
                          {i + 1}
                        </span>
                        <p className="text-sm text-slate-200 leading-relaxed">
                          {qa.question ?? qa.question_text}
                        </p>
                      </div>
                      {score != null && (
                        <span className={`shrink-0 px-2.5 py-0.5 rounded-full text-xs font-bold border ${scoreColor}`}>
                          {score.toFixed(1)} / 10
                        </span>
                      )}
                    </div>

                    {(qa.feedback ?? qa.llm_feedback) && (
                      <div className="ml-9 bg-surface-800 rounded-lg p-3 border border-white/5">
                        <p className="text-xs text-slate-400 whitespace-pre-wrap leading-relaxed">
                          {qa.feedback ?? qa.llm_feedback}
                        </p>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* ── CTA ────────────────────────────────────────────── */}
        <div className="flex flex-col sm:flex-row gap-3 justify-center pt-2 print:hidden">
          <button
            onClick={() => { reset(); navigate("/dashboard"); }}
            className="btn-primary px-8 py-3"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0l3.181 3.183a8.25 8.25 0 0013.803-3.7M4.031 9.865a8.25 8.25 0 0113.803-3.7l3.181 3.182m0-4.991v4.99" />
            </svg>
            Start New Interview
          </button>
          <button
            onClick={handleDownload}
            className="btn-ghost px-8 py-3 flex items-center gap-2"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5M16.5 12L12 16.5m0 0L7.5 12m4.5 4.5V3" />
            </svg>
            Download PDF
          </button>
          <button
            onClick={handleDelete}
            disabled={deleting}
            className="px-8 py-3 rounded-xl text-sm font-medium border border-red-500/30 text-red-400 hover:bg-red-500/10 transition-all disabled:opacity-50 flex items-center gap-2"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M14.74 9l-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 01-2.244 2.077H8.084a2.25 2.25 0 01-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 00-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 013.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 00-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 00-7.5 0" />
            </svg>
            {deleting ? "Deleting…" : "Delete Report"}
          </button>
          <Link to="/dashboard" className="btn-ghost px-8 py-3">
            Back to Dashboard
          </Link>
        </div>

      </main>
    </div>
  );
}
