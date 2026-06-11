import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import ErrorBoundary from "./components/ErrorBoundary";
import SetupBanner from "./components/SetupBanner";
import "./store/themeStore";   // side-effect: applies saved theme to <html> before paint
import "./index.css";

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <ErrorBoundary>
      <SetupBanner />
      <App />
    </ErrorBoundary>
  </React.StrictMode>
);
