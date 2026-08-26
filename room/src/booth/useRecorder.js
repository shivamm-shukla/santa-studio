import { useCallback, useEffect, useRef, useState } from "react";

/* The microphone, and what it is hearing right now.

   Two separate things come off one stream and both are needed. MediaRecorder
   produces the file that gets uploaded; an AnalyserNode produces a level, many
   times a second, that the 3D reads so the mic in front of you responds to
   your voice. Without the second one you are looking at a picture of a booth
   while you talk, which is the thing this exists not to be.

   The level is kept in a ref rather than in state on purpose: it changes every
   frame, and putting that through React would re-render the page sixty times a
   second to move one object. */

export const MIN_SECONDS = 8;

export function useRecorder() {
  const [status, setStatus] = useState("idle"); // idle | ready | recording | recorded | denied
  const [seconds, setSeconds] = useState(0);
  const [clip, setClip] = useState(null); // { blob, url }
  const [error, setError] = useState("");

  const level = useRef(0);
  const stream = useRef(null);
  const recorder = useRef(null);
  const chunks = useRef([]);
  const audio = useRef({ context: null, analyser: null, data: null });
  const raf = useRef(null);
  const startedAt = useRef(0);

  const listen = useCallback(() => {
    const { analyser, data } = audio.current;
    if (!analyser) return;

    analyser.getByteTimeDomainData(data);
    let sum = 0;
    for (let i = 0; i < data.length; i++) {
      const v = (data[i] - 128) / 128;
      sum += v * v;
    }
    // Eased downward so the mic settles rather than flickering between words.
    const rms = Math.sqrt(sum / data.length);
    level.current = Math.max(rms, level.current * 0.86);

    raf.current = requestAnimationFrame(listen);
  }, []);

  const connect = useCallback(async () => {
    setError("");
    try {
      const media = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: false },
      });
      stream.current = media;

      const context = new (window.AudioContext || window.webkitAudioContext)();
      const analyser = context.createAnalyser();
      analyser.fftSize = 1024;
      context.createMediaStreamSource(media).connect(analyser);

      audio.current = { context, analyser, data: new Uint8Array(analyser.fftSize) };
      raf.current = requestAnimationFrame(listen);
      setStatus("ready");
    } catch (e) {
      setStatus("denied");
      setError(
        e && e.name === "NotAllowedError"
          ? "The browser blocked the microphone. Allow it and press again."
          : "No microphone was available."
      );
    }
  }, [listen]);

  const start = useCallback(() => {
    if (!stream.current) return;
    chunks.current = [];

    const mime = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4"].find(
      (type) => window.MediaRecorder && MediaRecorder.isTypeSupported(type)
    );
    const media = new MediaRecorder(stream.current, mime ? { mimeType: mime } : undefined);

    media.ondataavailable = (event) => {
      if (event.data.size) chunks.current.push(event.data);
    };
    media.onstop = () => {
      const blob = new Blob(chunks.current, { type: media.mimeType || "audio/webm" });
      setClip({ blob, url: URL.createObjectURL(blob) });
      setStatus("recorded");
    };

    media.start();
    recorder.current = media;
    startedAt.current = performance.now();
    setSeconds(0);
    setClip(null);
    setStatus("recording");
  }, []);

  const stop = useCallback(() => {
    if (recorder.current && recorder.current.state !== "inactive") recorder.current.stop();
  }, []);

  const again = useCallback(() => {
    setClip((current) => {
      if (current) URL.revokeObjectURL(current.url);
      return null;
    });
    setSeconds(0);
    setStatus(stream.current ? "ready" : "idle");
  }, []);

  // The clock, while recording. There is a floor and deliberately no ceiling.
  useEffect(() => {
    if (status !== "recording") return;
    const timer = setInterval(
      () => setSeconds((performance.now() - startedAt.current) / 1000),
      100
    );
    return () => clearInterval(timer);
  }, [status]);

  useEffect(() => {
    return () => {
      if (raf.current) cancelAnimationFrame(raf.current);
      if (stream.current) stream.current.getTracks().forEach((t) => t.stop());
      if (audio.current.context) audio.current.context.close().catch(() => {});
    };
  }, []);

  return { status, seconds, clip, error, level, connect, start, stop, again, enough: seconds >= MIN_SECONDS };
}
