import axios from "axios";
import { getIdToken } from "./firebase";

// Empty string → requests go to /api/v1/... → Vite proxy forwards to localhost:8000
// In production set VITE_API_BASE_URL to the deployed backend URL
const BASE_URL = import.meta.env.VITE_API_BASE_URL || "";

const api = axios.create({
  baseURL: `${BASE_URL}/api/v1`,
  timeout: 30000,
});

api.interceptors.request.use(async (config) => {
  try {
    const token = await getIdToken();
    config.headers.Authorization = `Bearer ${token}`;
  } catch {
    // unauthenticated request — let it pass; server will 401 if protected
  }
  return config;
});

api.interceptors.response.use(
  (response) => response.data,
  (error) => {
    const message =
      error.response?.data?.detail ||
      error.response?.data?.message ||
      error.message ||
      "An unexpected error occurred";
    return Promise.reject(new Error(message));
  }
);

// ── Auth ──────────────────────────────────────────────────
export const loginOrRegister = () => api.post("/auth/login");
export const getMe = () => api.get("/auth/me");
export const updateRole = (role) => api.patch("/auth/me/role", { role });
export const switchRole = (role) => api.post("/auth/me/switch-role", { role });
export const getUserByEmail = (email) => api.get(`/auth/user-by-email?email=${encodeURIComponent(email)}`);

// ── Interviews ────────────────────────────────────────────
export const parseResume = (file) => {
  const form = new FormData();
  form.append("file", file, file.name);
  return api.post("/interviews/parse-resume", form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
};

export const createInterview = (payload) => api.post("/interviews/", payload);
export const scheduleInterview = (payload) => api.post("/interviews/schedule", payload);
export const listInterviews = () => api.get("/interviews/");
export const getRecruiterInterviews = () => api.get("/interviews/recruiter");
export const getInterview = (id) => api.get(`/interviews/${id}`);
export const startInterview = (id) => api.post(`/interviews/${id}/start`);
export const setInterviewResume = (id, resumeContext) =>
  api.patch(`/interviews/${id}/resume-context`, resumeContext);
export const deleteInterview = (id) => api.delete(`/interviews/${id}`);
export const submitAnswer = (id, questionId, transcript) =>
  api.post(`/interviews/${id}/submit-answer`, { question_id: questionId, transcript });
export const completeInterview = (id) => api.post(`/interviews/${id}/complete`);

// ── Analysis ──────────────────────────────────────────────
export const sendEmotionFrame = (interviewId, questionId, frameBlob) => {
  const form = new FormData();
  form.append("frame", frameBlob, "frame.jpg");
  return api.post("/analysis/emotion-frame", form, {
    params: { interview_id: interviewId, question_id: questionId },
    headers: { "Content-Type": "multipart/form-data" },
  });
};

export const sendAudioClip = (interviewId, questionId, audioBlob) => {
  const form = new FormData();
  form.append("audio", audioBlob, "audio.wav");
  return api.post("/analysis/speech-metrics", form, {
    params: { interview_id: interviewId, question_id: questionId },
    headers: { "Content-Type": "multipart/form-data" },
  });
};

export const getAnalysisReport = (interviewId) =>
  api.get(`/analysis/${interviewId}/report`);

export default api;
