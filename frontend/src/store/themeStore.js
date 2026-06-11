import { create } from "zustand";
import { persist } from "zustand/middleware";

const applyTheme = (theme) => {
  document.documentElement.dataset.theme = theme;
};

const useThemeStore = create(
  persist(
    (set) => ({
      theme: "dark",
      setTheme: (theme) => {
        applyTheme(theme);
        set({ theme });
      },
    }),
    {
      name: "ai-interviewer-theme",
      onRehydrateStorage: () => (state) => {
        // Apply persisted theme immediately on page load before first render.
        if (state?.theme) applyTheme(state.theme);
      },
    }
  )
);

// Fallback: ensure data-theme is set even before React mounts.
applyTheme(useThemeStore.getState().theme);

export default useThemeStore;
