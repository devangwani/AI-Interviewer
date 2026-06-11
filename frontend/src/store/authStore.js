import { create } from "zustand";
import { persist } from "zustand/middleware";
import { onAuthChange, logout as firebaseLogout } from "../services/firebase";
import { loginOrRegister } from "../services/api";

const useAuthStore = create(
  persist(
    (set, get) => ({
      user: null,          // Firebase user object
      profile: null,       // MongoDB profile from our backend
      loading: true,

      initAuth: () => {
        const unsubscribe = onAuthChange(async (firebaseUser) => {
          if (firebaseUser) {
            set({ user: firebaseUser, loading: false });
            try {
              const profile = await loginOrRegister();
              set({ profile });
            } catch {
              // profile fetch failing shouldn't block the app
            }
          } else {
            set({ user: null, profile: null, loading: false });
          }
        });
        return unsubscribe;
      },

      setUser: (user) => set({ user }),
      setProfile: (profile) => set({ profile }),

      logout: async () => {
        await firebaseLogout();
        set({ user: null, profile: null });
      },
    }),
    {
      name: "auth-storage",
      partialize: (state) => ({ profile: state.profile }),
    }
  )
);

export default useAuthStore;
