"use client";

import { useEffect, useRef, useState } from "react";

import Button from "@/components/Button";
import Card from "@/components/Card";
import {
  evaluatePronunciation,
  getVoiceDiagnosticPrompts,
  requestTTS,
  type PronunciationResult,
} from "@/lib/api";

type RecorderState = "idle" | "recording" | "recorded";

export default function VoiceDiagnosticPage() {
  const [targetSentence, setTargetSentence] = useState("");
  const [recorderState, setRecorderState] = useState<RecorderState>("idle");
  const [audioBlob, setAudioBlob] = useState<Blob | null>(null);
  const [result, setResult] = useState<PronunciationResult | null>(null);
  const [error, setError] = useState("");
  const [loadingPrompt, setLoadingPrompt] = useState(true);
  const [playing, setPlaying] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<BlobPart[]>([]);

  useEffect(() => {
    let active = true;
    getVoiceDiagnosticPrompts()
      .then((data) => {
        if (active) {
          setTargetSentence(data.pronunciation.target_sentence);
        }
      })
      .catch((err: unknown) => {
        if (active) {
          setError(err instanceof Error ? err.message : "Unable to load voice diagnostic prompt.");
        }
      })
      .finally(() => {
        if (active) {
          setLoadingPrompt(false);
        }
      });

    return () => {
      active = false;
      streamRef.current?.getTracks().forEach((track) => track.stop());
    };
  }, []);

  async function playSentence() {
    if (!targetSentence) {
      return;
    }
    setError("");
    setPlaying(true);
    try {
      const audio = await requestTTS(targetSentence);
      const audioUrl = URL.createObjectURL(audio);
      const player = new Audio(audioUrl);
      player.onended = () => URL.revokeObjectURL(audioUrl);
      await player.play();
    } catch (err) {
      setError(err instanceof Error ? err.message : "TTS is not configured yet.");
    } finally {
      setPlaying(false);
    }
  }

  async function startRecording() {
    if (!navigator.mediaDevices || typeof MediaRecorder === "undefined") {
      setError("Voice recording is not supported in this browser.");
      return;
    }

    setError("");
    setResult(null);
    setAudioBlob(null);
    chunksRef.current = [];

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      const recorder = new MediaRecorder(stream);
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          chunksRef.current.push(event.data);
        }
      };
      recorder.onstop = () => {
        const recordedBlob = new Blob(chunksRef.current, {
          type: recorder.mimeType || "audio/webm",
        });
        setAudioBlob(recordedBlob);
        setRecorderState("recorded");
        stream.getTracks().forEach((track) => track.stop());
      };
      mediaRecorderRef.current = recorder;
      recorder.start();
      setRecorderState("recording");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start recording.");
      setRecorderState("idle");
    }
  }

  function stopRecording() {
    const recorder = mediaRecorderRef.current;
    if (recorder && recorder.state !== "inactive") {
      recorder.stop();
    }
  }

  async function submitRecording() {
    if (!audioBlob || !targetSentence) {
      setError("Record your voice before submitting.");
      return;
    }

    setError("");
    setSubmitting(true);
    try {
      const data = await evaluatePronunciation(audioBlob, targetSentence);
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Pronunciation evaluation failed.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="page-shell">
      <p className="eyebrow">Voice assessment</p>
      <h1 className="page-title">Voice Diagnostic</h1>
      <p className="page-copy">
        Listen to the sentence, record yourself repeating it, and submit the recording for
        pronunciation clarity scoring.
      </p>

      {error ? <div className="error-box">{error}</div> : null}

      <Card className="mt-8 max-w-4xl">
        <div className="flex flex-col gap-5">
          <div>
            <p className="eyebrow">Pronunciation Test</p>
            <h2 className="mt-2 text-2xl font-black text-[#14213d]">Target sentence</h2>
            <p className="mt-3 rounded-2xl border border-[#dce4ef] bg-[#f8fafc] p-4 text-lg leading-8 text-[#14213d]">
              {loadingPrompt ? "Loading target sentence..." : targetSentence}
            </p>
          </div>

          <div className="flex flex-wrap gap-3">
            <Button disabled={!targetSentence || playing} onClick={playSentence} type="button">
              {playing ? "Playing..." : "Play sentence"}
            </Button>
            <Button
              disabled={recorderState === "recording"}
              onClick={startRecording}
              type="button"
              variant="secondary"
            >
              Start recording
            </Button>
            <Button
              disabled={recorderState !== "recording"}
              onClick={stopRecording}
              type="button"
              variant="secondary"
            >
              Stop recording
            </Button>
            <Button disabled={!audioBlob || submitting} onClick={submitRecording} type="button">
              {submitting ? "Submitting..." : "Submit recording"}
            </Button>
          </div>

          <div className="note-box">
            Recording status:{" "}
            {recorderState === "recording"
              ? "Recording"
              : recorderState === "recorded"
                ? "Recording ready"
                : "Not started"}
          </div>
        </div>
      </Card>

      {result ? (
        <section className="mt-8 grid gap-4 lg:grid-cols-[1fr_1fr]">
          <Card>
            <p className="eyebrow">Result</p>
            <h2 className="mt-2 text-2xl font-black text-[#14213d]">{result.score}%</h2>
            <p className="mt-2 font-semibold text-[#60708a]">{result.status}</p>
            <p className="mt-4 leading-7 text-[#42536b]">{result.feedback}</p>
          </Card>

          <Card>
            <p className="eyebrow">Transcript</p>
            <p className="mt-3 leading-7 text-[#14213d]">{result.transcript}</p>
            <p className="mt-4 text-sm font-bold text-[#60708a]">
              Word accuracy: {result.word_accuracy}%
            </p>
          </Card>

          <Card>
            <p className="eyebrow">Missing words</p>
            <p className="mt-3 text-[#14213d]">
              {result.missing_words.length ? result.missing_words.join(", ") : "None"}
            </p>
          </Card>

          <Card>
            <p className="eyebrow">Extra words</p>
            <p className="mt-3 text-[#14213d]">
              {result.extra_words.length ? result.extra_words.join(", ") : "None"}
            </p>
          </Card>
        </section>
      ) : null}
    </main>
  );
}
