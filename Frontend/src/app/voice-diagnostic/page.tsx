"use client";

import { useEffect, useRef, useState } from "react";

import Button from "@/components/Button";
import Card from "@/components/Card";
import {
  evaluateListening,
  evaluatePronunciation,
  getVoiceDiagnosticPrompts,
  requestTTS,
  type ListeningResult,
  type PronunciationResult,
} from "@/lib/api";

type RecorderState = "idle" | "recording" | "recorded";
type ListeningPrompt = {
  passage: string;
  question: string;
  expected_answer: string;
};

export default function VoiceDiagnosticPage() {
  const [targetSentence, setTargetSentence] = useState("");
  const [listeningPrompt, setListeningPrompt] = useState<ListeningPrompt | null>(null);
  const [listeningAnswer, setListeningAnswer] = useState("");
  const [recorderState, setRecorderState] = useState<RecorderState>("idle");
  const [audioBlob, setAudioBlob] = useState<Blob | null>(null);
  const [pronunciationResult, setPronunciationResult] = useState<PronunciationResult | null>(null);
  const [listeningResult, setListeningResult] = useState<ListeningResult | null>(null);
  const [error, setError] = useState("");
  const [loadingPrompt, setLoadingPrompt] = useState(true);
  const [playingAudio, setPlayingAudio] = useState<"pronunciation" | "listening" | null>(null);
  const [submittingPronunciation, setSubmittingPronunciation] = useState(false);
  const [submittingListening, setSubmittingListening] = useState(false);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<BlobPart[]>([]);

  useEffect(() => {
    let active = true;
    getVoiceDiagnosticPrompts()
      .then((data) => {
        if (active) {
          setTargetSentence(data.pronunciation.target_sentence);
          setListeningPrompt(data.listening);
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
    setPlayingAudio("pronunciation");
    try {
      const audio = await requestTTS(targetSentence);
      const audioUrl = URL.createObjectURL(audio);
      const player = new Audio(audioUrl);
      player.onended = () => URL.revokeObjectURL(audioUrl);
      await player.play();
    } catch (err) {
      setError(err instanceof Error ? err.message : "TTS is not configured yet.");
    } finally {
      setPlayingAudio(null);
    }
  }

  async function playListeningPassage() {
    if (!listeningPrompt) {
      return;
    }
    setError("");
    setPlayingAudio("listening");
    try {
      const audio = await requestTTS(listeningPrompt.passage);
      const audioUrl = URL.createObjectURL(audio);
      const player = new Audio(audioUrl);
      player.onended = () => URL.revokeObjectURL(audioUrl);
      await player.play();
    } catch (err) {
      setError(err instanceof Error ? err.message : "TTS is not configured yet.");
    } finally {
      setPlayingAudio(null);
    }
  }

  async function startRecording() {
    if (!navigator.mediaDevices || typeof MediaRecorder === "undefined") {
      setError("Voice recording is not supported in this browser.");
      return;
    }

    setError("");
    setPronunciationResult(null);
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
    setSubmittingPronunciation(true);
    try {
      const data = await evaluatePronunciation(audioBlob, targetSentence);
      setPronunciationResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Pronunciation evaluation failed.");
    } finally {
      setSubmittingPronunciation(false);
    }
  }

  async function submitListeningAnswer() {
    if (!listeningPrompt) {
      setError("Listening prompt is still loading.");
      return;
    }
    if (!listeningAnswer.trim()) {
      setError("Write your answer before submitting.");
      return;
    }

    setError("");
    setSubmittingListening(true);
    try {
      const data = await evaluateListening(
        listeningPrompt.question,
        listeningPrompt.expected_answer,
        listeningAnswer,
      );
      setListeningResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Listening evaluation failed.");
    } finally {
      setSubmittingListening(false);
    }
  }

  return (
    <main className="page-shell">
      <p className="eyebrow">Voice assessment</p>
      <h1 className="page-title">Voice Diagnostic</h1>
      <p className="page-copy">
        Complete voice-based checks for pronunciation clarity and listening comprehension.
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
            <Button
              disabled={!targetSentence || playingAudio === "pronunciation"}
              onClick={playSentence}
              type="button"
            >
              {playingAudio === "pronunciation" ? "Playing..." : "Play sentence"}
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
            <Button
              disabled={!audioBlob || submittingPronunciation}
              onClick={submitRecording}
              type="button"
            >
              {submittingPronunciation ? "Submitting..." : "Submit recording"}
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

      {pronunciationResult ? (
        <section className="mt-8 grid gap-4 lg:grid-cols-[1fr_1fr]">
          <Card>
            <p className="eyebrow">Result</p>
            <h2 className="mt-2 text-2xl font-black text-[#14213d]">{pronunciationResult.score}%</h2>
            <p className="mt-2 font-semibold text-[#60708a]">{pronunciationResult.status}</p>
            <p className="mt-4 leading-7 text-[#42536b]">{pronunciationResult.feedback}</p>
          </Card>

          <Card>
            <p className="eyebrow">Transcript</p>
            <p className="mt-3 leading-7 text-[#14213d]">{pronunciationResult.transcript}</p>
            <p className="mt-4 text-sm font-bold text-[#60708a]">
              Word accuracy: {pronunciationResult.word_accuracy}%
            </p>
          </Card>

          <Card>
            <p className="eyebrow">Missing words</p>
            <p className="mt-3 text-[#14213d]">
              {pronunciationResult.missing_words.length ? pronunciationResult.missing_words.join(", ") : "None"}
            </p>
          </Card>

          <Card>
            <p className="eyebrow">Extra words</p>
            <p className="mt-3 text-[#14213d]">
              {pronunciationResult.extra_words.length ? pronunciationResult.extra_words.join(", ") : "None"}
            </p>
          </Card>
        </section>
      ) : null}

      <Card className="mt-8 max-w-4xl">
        <div className="flex flex-col gap-5">
          <div>
            <p className="eyebrow">Listening Test</p>
            <h2 className="mt-2 text-2xl font-black text-[#14213d]">Comprehension question</h2>
            <p className="mt-3 text-[#60708a]">
              Listen to the short passage, then answer the question from what you heard.
            </p>
            <p className="mt-4 rounded-2xl border border-[#dce4ef] bg-[#f8fafc] p-4 text-lg leading-8 text-[#14213d]">
              {loadingPrompt ? "Loading listening question..." : listeningPrompt?.question}
            </p>
          </div>

          <div className="flex flex-wrap gap-3">
            <Button
              disabled={!listeningPrompt || playingAudio === "listening"}
              onClick={playListeningPassage}
              type="button"
            >
              {playingAudio === "listening" ? "Playing..." : "Play passage"}
            </Button>
          </div>

          <label>
            <span className="field-label">Your answer</span>
            <textarea
              className="text-area"
              onChange={(event) => setListeningAnswer(event.target.value)}
              placeholder="Type the answer you understood from the audio."
              value={listeningAnswer}
            />
          </label>

          <div>
            <Button
              disabled={!listeningPrompt || submittingListening}
              onClick={submitListeningAnswer}
              type="button"
            >
              {submittingListening ? "Submitting..." : "Submit Listening Answer"}
            </Button>
          </div>
        </div>
      </Card>

      {listeningResult ? (
        <section className="mt-8 grid gap-4 lg:grid-cols-[1fr_1fr]">
          <Card>
            <p className="eyebrow">Listening score</p>
            <h2 className="mt-2 text-2xl font-black text-[#14213d]">{listeningResult.score}%</h2>
            <p className="mt-2 font-semibold text-[#60708a]">{listeningResult.status}</p>
            <p className="mt-4 leading-7 text-[#42536b]">{listeningResult.feedback}</p>
          </Card>

          <Card>
            <p className="eyebrow">Your answer</p>
            <p className="mt-3 leading-7 text-[#14213d]">{listeningResult.user_answer}</p>
            <p className="mt-4 text-sm font-bold text-[#60708a]">
              Expected answer: {listeningResult.expected_answer}
            </p>
          </Card>
        </section>
      ) : null}
    </main>
  );
}
