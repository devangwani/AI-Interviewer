import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { updateRole } from "../services/api";
import useAuthStore from "../store/authStore";

export default function RoleSelectPage() {
  const navigate    = useNavigate();
  const setProfile  = useAuthStore((s) => s.setProfile);
  const profile     = useAuthStore((s) => s.profile);
  const [loading, setLoading] = useState(false);
  const [error,   setError]   = useState("");

  // Already has a role — shouldn't be here
  if (profile?.role) {
    navigate("/dashboard", { replace: true });
    return null;
  }

  const handleSelect = async (role) => {
    setLoading(true);
    setError("");
    try {
      const updated = await updateRole(role);
      setProfile(updated);
      navigate("/dashboard", { replace: true });
    } catch (e) {
      setError(e.message);
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-surface-900 px-4">
      <div className="pointer-events-none fixed inset-0 overflow-hidden">
        <div className="absolute top-1/4 left-1/2 -translate-x-1/2 w-[600px] h-[600px] bg-brand-600/10 rounded-full blur-3xl" />
      </div>

      <div className="relative w-full max-w-lg animate-slide-up">
        <div className="text-center mb-10">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-brand-600 shadow-glow mb-4">
            <svg className="w-8 h-8 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M15 19.128a9.38 9.38 0 002.625.372 9.337 9.337 0 004.121-.952 4.125 4.125 0 00-7.533-2.493M15 19.128v-.003c0-1.113-.285-2.16-.786-3.07M15 19.128v.106A12.318 12.318 0 018.624 21c-2.331 0-4.512-.645-6.374-1.766l-.001-.109a6.375 6.375 0 0111.964-3.07M12 6.375a3.375 3.375 0 11-6.75 0 3.375 3.375 0 016.75 0zm8.25 2.25a2.625 2.625 0 11-5.25 0 2.625 2.625 0 015.25 0z" />
            </svg>
          </div>
          <h1 className="text-2xl font-bold text-white">Welcome to AI Interviewer</h1>
          <p className="text-slate-400 text-sm mt-2">How will you be using this platform?</p>
        </div>

        <div className="grid sm:grid-cols-2 gap-4">
          {/* Candidate card */}
          <button
            onClick={() => handleSelect("candidate")}
            disabled={loading}
            className="glass p-6 text-left rounded-2xl border-2 border-white/5 hover:border-brand-500/50 hover:bg-brand-600/5 transition-all group disabled:opacity-50"
          >
            <div className="w-12 h-12 rounded-xl bg-brand-600/20 border border-brand-500/30 flex items-center justify-center mb-4 group-hover:bg-brand-600/30 transition-colors">
              <svg className="w-6 h-6 text-brand-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
              </svg>
            </div>
            <h2 className="text-lg font-bold text-white mb-1">I'm a Candidate</h2>
            <p className="text-sm text-slate-400 leading-relaxed">
              Practice interviews, get AI feedback, and track your performance over time.
            </p>
          </button>

          {/* Recruiter card */}
          <button
            onClick={() => handleSelect("recruiter")}
            disabled={loading}
            className="glass p-6 text-left rounded-2xl border-2 border-white/5 hover:border-emerald-500/50 hover:bg-emerald-600/5 transition-all group disabled:opacity-50"
          >
            <div className="w-12 h-12 rounded-xl bg-emerald-600/20 border border-emerald-500/30 flex items-center justify-center mb-4 group-hover:bg-emerald-600/30 transition-colors">
              <svg className="w-6 h-6 text-emerald-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" />
              </svg>
            </div>
            <h2 className="text-lg font-bold text-white mb-1">I'm a Recruiter</h2>
            <p className="text-sm text-slate-400 leading-relaxed">
              Schedule AI interviews for candidates and review their multimodal report cards.
            </p>
          </button>
        </div>

        {loading && (
          <div className="flex justify-center mt-6">
            <div className="w-6 h-6 rounded-full border-2 border-brand-500 border-t-transparent animate-spin" />
          </div>
        )}
        {error && (
          <div className="mt-4 px-4 py-3 rounded-xl bg-red-500/10 border border-red-500/20 text-red-400 text-sm text-center">
            {error}
          </div>
        )}
      </div>
    </div>
  );
}
