import useInterviewStore from "../store/interviewStore";

export default function TabSwitchWarning() {
  const { warningVisible, tabSwitchCount, dismissWarning } = useInterviewStore();

  if (!warningVisible) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm animate-fade-in">
      <div className="glass max-w-md w-full mx-4 p-6 border-red-500/40 shadow-[0_0_40px_4px_rgba(239,68,68,0.3)]">
        <div className="flex items-start gap-4">
          <div className="flex-shrink-0 w-12 h-12 rounded-xl bg-red-500/20 flex items-center justify-center">
            <svg className="w-6 h-6 text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
            </svg>
          </div>
          <div className="flex-1">
            <h3 className="text-lg font-semibold text-red-400 mb-1">Proctoring Alert</h3>
            <p className="text-sm text-slate-300 mb-1">
              You navigated away from the interview window.
            </p>
            <p className="text-xs text-slate-500">
              Tab switch count: <span className="text-red-400 font-semibold">{tabSwitchCount}</span>
              {tabSwitchCount >= 3 && (
                <span className="ml-2 badge bg-red-500/20 text-red-400">
                  ⚠ Multiple violations
                </span>
              )}
            </p>
            <p className="text-xs text-slate-500 mt-2">
              All violations are logged and sent to your interviewer.
            </p>
          </div>
        </div>
        <button
          onClick={dismissWarning}
          className="mt-5 w-full py-2.5 rounded-xl bg-red-500/20 hover:bg-red-500/30 border border-red-500/30 text-red-300 text-sm font-medium transition-all"
        >
          I understand — return to interview
        </button>
      </div>
    </div>
  );
}
