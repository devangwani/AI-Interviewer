import { isFirebaseConfigured } from "../services/firebase";

export default function SetupBanner() {
  if (isFirebaseConfigured) return null;

  return (
    <div className="fixed inset-0 z-[9999] bg-surface-900 flex items-center justify-center px-4">
      <div className="max-w-lg w-full glass p-8 border-amber-500/30 shadow-[0_0_40px_4px_rgba(245,158,11,0.15)]">
        <div className="flex items-center gap-3 mb-5">
          <div className="w-10 h-10 rounded-xl bg-amber-500/20 flex items-center justify-center flex-shrink-0">
            <svg className="w-5 h-5 text-amber-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M10.343 3.94c.09-.542.56-.94 1.11-.94h1.093c.55 0 1.02.398 1.11.94l.149.894c.07.424.384.764.78.93.398.164.855.142 1.205-.108l.737-.527a1.125 1.125 0 011.45.12l.773.774c.39.389.44 1.002.12 1.45l-.527.737c-.25.35-.272.806-.107 1.204.165.397.505.71.93.78l.893.15c.543.09.94.56.94 1.109v1.094c0 .55-.397 1.02-.94 1.11l-.893.149c-.425.07-.765.383-.93.78-.165.398-.143.854.107 1.204l.527.738c.32.447.269 1.06-.12 1.45l-.774.773a1.125 1.125 0 01-1.449.12l-.738-.527c-.35-.25-.806-.272-1.203-.107-.397.165-.71.505-.781.929l-.149.894c-.09.542-.56.94-1.11.94h-1.094c-.55 0-1.019-.398-1.11-.94l-.148-.894c-.071-.424-.384-.764-.781-.93-.398-.164-.854-.142-1.204.108l-.738.527c-.447.32-1.06.269-1.45-.12l-.773-.774a1.125 1.125 0 01-.12-1.45l.527-.737c.25-.35.273-.806.108-1.204-.165-.397-.505-.71-.93-.78l-.894-.15c-.542-.09-.94-.56-.94-1.109v-1.094c0-.55.398-1.02.94-1.11l.894-.149c.424-.07.765-.383.93-.78.165-.398.143-.854-.108-1.204l-.526-.738a1.125 1.125 0 01.12-1.45l.773-.773a1.125 1.125 0 011.45-.12l.737.527c.35.25.807.272 1.204.107.397-.165.71-.505.78-.929l.15-.894z" />
              <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
            </svg>
          </div>
          <div>
            <h2 className="text-lg font-bold text-white">Firebase Not Configured</h2>
            <p className="text-sm text-amber-400">Setup required before the app can run</p>
          </div>
        </div>

        <p className="text-sm text-slate-400 mb-5">
          The app is running but Firebase credentials are missing from{" "}
          <code className="px-1.5 py-0.5 rounded bg-surface-600 text-amber-300 text-xs font-mono">
            frontend/.env.local
          </code>
          . Add your Firebase config values to see the full UI.
        </p>

        <div className="bg-surface-800 rounded-xl p-4 font-mono text-xs text-slate-300 space-y-1 border border-white/5">
          <p className="text-slate-500"># frontend/.env.local</p>
          <p><span className="text-brand-400">VITE_API_BASE_URL</span>=http://localhost:8000</p>
          <p><span className="text-brand-400">VITE_WS_BASE_URL</span>=ws://localhost:8000</p>
          <p><span className="text-brand-400">VITE_FIREBASE_API_KEY</span>=<span className="text-amber-300">your-key</span></p>
          <p><span className="text-brand-400">VITE_FIREBASE_AUTH_DOMAIN</span>=<span className="text-amber-300">your-project.firebaseapp.com</span></p>
          <p><span className="text-brand-400">VITE_FIREBASE_PROJECT_ID</span>=<span className="text-amber-300">your-project-id</span></p>
          <p><span className="text-brand-400">VITE_FIREBASE_STORAGE_BUCKET</span>=<span className="text-amber-300">your-project.appspot.com</span></p>
          <p><span className="text-brand-400">VITE_FIREBASE_MESSAGING_SENDER_ID</span>=<span className="text-amber-300">000000000000</span></p>
          <p><span className="text-brand-400">VITE_FIREBASE_APP_ID</span>=<span className="text-amber-300">1:000:web:xxx</span></p>
        </div>

        <p className="text-xs text-slate-500 mt-4">
          After saving the file, restart the dev server with{" "}
          <code className="px-1.5 py-0.5 rounded bg-surface-600 text-slate-300 font-mono">npm run dev</code>.
        </p>
      </div>
    </div>
  );
}
