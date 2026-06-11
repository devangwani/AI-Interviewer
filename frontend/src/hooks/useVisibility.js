import { useEffect, useRef } from "react";
import useInterviewStore from "../store/interviewStore";

export default function useVisibility({ enabled = true } = {}) {
  const incrementTabSwitch = useInterviewStore((s) => s.incrementTabSwitch);
  const guardRef = useRef(enabled);
  guardRef.current = enabled;

  useEffect(() => {
    const handleVisibilityChange = () => {
      if (!guardRef.current) return;
      if (document.visibilityState === "hidden") {
        incrementTabSwitch();
      }
    };

    const handleBlur = () => {
      if (!guardRef.current) return;
      // window blur fires when the user alt-tabs or minimises
      incrementTabSwitch();
    };

    document.addEventListener("visibilitychange", handleVisibilityChange);
    window.addEventListener("blur", handleBlur);

    return () => {
      document.removeEventListener("visibilitychange", handleVisibilityChange);
      window.removeEventListener("blur", handleBlur);
    };
  }, [incrementTabSwitch]);
}
