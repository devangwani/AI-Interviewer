import { create } from "zustand";

const useInterviewStore = create((set, get) => ({
  // current interview session
  interview: null,
  currentQuestionIndex: 0,
  transcript: "",
  partialTranscript: "",   // live interim text while candidate is mid-utterance
  isListening: false,
  isSpeaking: false,

  // proctoring
  tabSwitchCount: 0,
  warningVisible: false,

  // results
  report: null,

  setInterview: (interview) => set({ interview, currentQuestionIndex: 0 }),

  currentQuestion: () => {
    const { interview, currentQuestionIndex } = get();
    return interview?.questions_answers?.[currentQuestionIndex] ?? null;
  },

  nextQuestion: () =>
    set((s) => ({ currentQuestionIndex: s.currentQuestionIndex + 1, transcript: "" })),

  // Clearing the transcript (new question) also wipes any in-flight partial
  setTranscript: (transcript) => set({ transcript, partialTranscript: "" }),
  appendTranscript: (chunk) =>
    set((s) => ({
      transcript: s.transcript + (s.transcript ? " " : "") + chunk,
      partialTranscript: "",   // confirmed final replaces the partial
    })),
  setPartialTranscript: (partialTranscript) => set({ partialTranscript }),

  setListening: (isListening) => set({ isListening }),
  setSpeaking: (isSpeaking) => set({ isSpeaking }),

  incrementTabSwitch: () =>
    set((s) => ({
      tabSwitchCount: s.tabSwitchCount + 1,
      warningVisible: true,
    })),

  dismissWarning: () => set({ warningVisible: false }),

  setReport: (report) => set({ report }),

  reset: () =>
    set({
      interview: null,
      currentQuestionIndex: 0,
      transcript: "",
      partialTranscript: "",
      isListening: false,
      isSpeaking: false,
      tabSwitchCount: 0,
      warningVisible: false,
      report: null,
    }),
}));

export default useInterviewStore;
