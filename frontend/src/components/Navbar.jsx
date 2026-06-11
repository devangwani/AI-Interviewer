import { useState, useRef, useEffect } from "react";
import { Link, useNavigate } from "react-router-dom";
import useAuthStore from "../store/authStore";
import useThemeStore from "../store/themeStore";
import { switchRole } from "../services/api";

export default function Navbar() {
  const { user, profile, logout, setProfile } = useAuthStore();
  const { theme, setTheme } = useThemeStore();
  const navigate = useNavigate();

  const [menuOpen,    setMenuOpen]    = useState(false);
  const [switching,   setSwitching]   = useState(false);  // confirm step visible
  const [saving,      setSaving]      = useState(false);
  const [switchError, setSwitchError] = useState("");
  const menuRef = useRef(null);

  // Close menu on outside click
  useEffect(() => {
    const handler = (e) => {
      if (menuRef.current && !menuRef.current.contains(e.target)) {
        setMenuOpen(false);
        setSwitching(false);
        setSwitchError("");
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const handleLogout = async () => {
    await logout();
    navigate("/login");
  };

  const targetRole = profile?.role === "recruiter" ? "candidate" : "recruiter";
  const canSwitch  = profile?.role && (profile?.role_switch_count ?? 0) < 1;

  const handleConfirmSwitch = async () => {
    setSaving(true);
    setSwitchError("");
    try {
      const updated = await switchRole(targetRole);
      setProfile(updated);
      setMenuOpen(false);
      setSwitching(false);
      navigate("/dashboard");
    } catch (e) {
      setSwitchError(e.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <header className="sticky top-0 z-50 border-b border-white/5 bg-surface-900/80 backdrop-blur-xl">
      <nav className="max-w-7xl mx-auto px-4 sm:px-6 h-16 flex items-center justify-between">
        {/* Logo */}
        <Link to="/dashboard" className="flex items-center gap-2.5 group">
          <div className="w-8 h-8 rounded-lg bg-brand-600 flex items-center justify-center shadow-glow-sm group-hover:shadow-glow transition-all">
            <svg className="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
            </svg>
          </div>
          <span className="font-semibold text-white text-base tracking-tight">AI Interviewer</span>
        </Link>

        {/* ── Theme switcher ─────────────────────────────── */}
        <div className="flex items-center gap-1 px-1.5 py-1 rounded-xl bg-surface-700 border border-white/5">
          {[
            {
              id: "dark",
              label: "Dark",
              icon: (
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M21.752 15.002A9.718 9.718 0 0118 15.75c-5.385 0-9.75-4.365-9.75-9.75 0-1.33.266-2.597.748-3.752A9.753 9.753 0 003 11.25C3 16.635 7.365 21 12.75 21a9.753 9.753 0 009.002-5.998z" />
                </svg>
              ),
            },
            {
              id: "light",
              label: "Light",
              icon: (
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 3v2.25m6.364.386l-1.591 1.591M21 12h-2.25m-.386 6.364l-1.591-1.591M12 18.75V21m-4.773-4.227l-1.591 1.591M5.25 12H3m4.227-4.773L5.636 5.636M15.75 12a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0z" />
                </svg>
              ),
            },
            {
              id: "aesthetic",
              label: "Aesthetic",
              icon: (
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M9.53 16.122a3 3 0 00-5.78 1.128 2.25 2.25 0 01-2.4 2.245 4.5 4.5 0 008.4-2.245c0-.399-.078-.78-.22-1.128zm0 0a15.998 15.998 0 003.388-1.62m-5.043-.025a15.994 15.994 0 011.622-3.395m3.42 3.42a15.995 15.995 0 004.764-4.648l3.876-5.814a1.151 1.151 0 00-1.597-1.597L14.146 6.32a15.996 15.996 0 00-4.649 4.763m3.42 3.42a6.776 6.776 0 00-3.42-3.42" />
                </svg>
              ),
            },
          ].map(({ id, label, icon }) => (
            <button
              key={id}
              onClick={() => setTheme(id)}
              title={`${label} mode`}
              className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-medium transition-all ${
                theme === id
                  ? id === "aesthetic"
                    ? "bg-[#850E35] text-[#FCF5EE] shadow-sm"
                    : "bg-brand-600 text-white shadow-sm"
                  : "text-slate-400 hover:text-white hover:bg-white/5"
              }`}
            >
              {icon}
              <span className="hidden sm:inline">{label}</span>
            </button>
          ))}
        </div>

        {/* Right side */}
        {user && (
          <div className="flex items-center gap-3">
            {/* User chip + dropdown trigger */}
            <div className="relative" ref={menuRef}>
              <button
                onClick={() => { setMenuOpen((o) => !o); setSwitching(false); setSwitchError(""); }}
                className="hidden sm:flex items-center gap-2 px-3 py-1.5 rounded-xl bg-surface-700 border border-white/5 hover:border-white/15 transition-colors"
              >
                {user.photoURL ? (
                  <img src={user.photoURL} alt="avatar" className="w-6 h-6 rounded-full" />
                ) : (
                  <div className="w-6 h-6 rounded-full bg-brand-600 flex items-center justify-center text-xs font-bold text-white">
                    {(profile?.display_name || user.email || "U")[0].toUpperCase()}
                  </div>
                )}
                <span className="text-sm text-slate-300 max-w-[140px] truncate">
                  {profile?.display_name || user.displayName || user.email}
                </span>
                {profile?.role && (
                  <span className={`text-xs font-semibold px-1.5 py-0.5 rounded-md ${
                    profile.role === "recruiter"
                      ? "bg-emerald-500/20 text-emerald-400"
                      : "bg-brand-500/20 text-brand-400"
                  }`}>
                    {profile.role}
                  </span>
                )}
                <svg className={`w-3.5 h-3.5 text-slate-500 transition-transform ${menuOpen ? "rotate-180" : ""}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
                </svg>
              </button>

              {/* Dropdown */}
              {menuOpen && (
                <div className="absolute right-0 top-full mt-2 w-72 rounded-2xl bg-surface-800 border border-white/10 shadow-2xl overflow-hidden z-50">
                  {!switching ? (
                    <div className="p-2 space-y-1">
                      {canSwitch && (
                        <button
                          onClick={() => setSwitching(true)}
                          className="w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm text-slate-300 hover:bg-white/5 transition-colors text-left"
                        >
                          <svg className="w-4 h-4 text-amber-400 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M7.5 21L3 16.5m0 0L7.5 12M3 16.5h13.5m0-13.5L21 7.5m0 0L16.5 3M21 7.5H7.5" />
                          </svg>
                          Switch to {targetRole.charAt(0).toUpperCase() + targetRole.slice(1)}
                        </button>
                      )}
                      <button
                        onClick={handleLogout}
                        className="w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm text-slate-300 hover:bg-white/5 transition-colors text-left"
                      >
                        <svg className="w-4 h-4 text-slate-500 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 9V5.25A2.25 2.25 0 0013.5 3h-6a2.25 2.25 0 00-2.25 2.25v13.5A2.25 2.25 0 007.5 21h6a2.25 2.25 0 002.25-2.25V15M12 9l-3 3m0 0l3 3m-3-3h12.75" />
                        </svg>
                        Sign out
                      </button>
                    </div>
                  ) : (
                    /* ── Switch confirmation panel ── */
                    <div className="p-4">
                      {/* Warning */}
                      <div className="flex items-start gap-2.5 mb-4 p-3 rounded-xl bg-amber-500/10 border border-amber-500/25">
                        <svg className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
                        </svg>
                        <div>
                          <p className="text-xs font-semibold text-amber-400 mb-0.5">One-time switch only</p>
                          <p className="text-xs text-slate-400 leading-relaxed">
                            You can switch roles <strong className="text-white">once</strong> to correct a mistake. After this, your role will be permanent. Please choose carefully.
                          </p>
                        </div>
                      </div>

                      <p className="text-sm text-slate-300 mb-4">
                        Switch from <span className="font-semibold text-white">{profile?.role}</span> to{" "}
                        <span className="font-semibold text-white">{targetRole}</span>?
                      </p>

                      {switchError && (
                        <p className="text-xs text-red-400 mb-3">{switchError}</p>
                      )}

                      <div className="flex gap-2">
                        <button
                          onClick={handleConfirmSwitch}
                          disabled={saving}
                          className="flex-1 py-2 rounded-xl text-sm font-semibold bg-amber-500/20 border border-amber-500/40 text-amber-300 hover:bg-amber-500/30 transition-colors disabled:opacity-50"
                        >
                          {saving ? "Switching…" : "Yes, switch role"}
                        </button>
                        <button
                          onClick={() => { setSwitching(false); setSwitchError(""); }}
                          disabled={saving}
                          className="flex-1 py-2 rounded-xl text-sm font-medium bg-surface-700 border border-white/10 text-slate-400 hover:bg-surface-600 transition-colors disabled:opacity-50"
                        >
                          Cancel
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* Mobile sign-out */}
            <button onClick={handleLogout} className="sm:hidden btn-ghost text-xs py-2 px-4">
              Sign out
            </button>
          </div>
        )}
      </nav>
    </header>
  );
}
