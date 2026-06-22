"use client";

import { useEffect, useRef, useState } from "react";

import Button from "@/components/Button";
import Card from "@/components/Card";
import {
  evaluateListeningPreview,
  evaluatePronunciationPreview,
  evaluateSpeakingPreview,
  getVoiceDiagnosticPrompts,
  getVoiceDiagnosticReport,
  requestTTS,
  startVoiceDiagnosticSession,
  submitListeningDiagnosticBatch,
  submitPronunciationDiagnosticBatch,
  submitSpeakingDiagnosticBatch,
  type ListeningBatchResult,
  type ListeningResult,
  type PronunciationBatchResult,
  type PronunciationResult,
  type SpeakingBatchResult,
  type SpeakingResult,
  type VoiceDiagnosticSessionState,
  type VoiceDiagnosticPrompts,
  type VoiceDiagnosticReport,
} from "@/lib/api";

type RecorderState = "idle" | "recording" | "recorded";
type VoiceSkill = "pronunciation" | "listening" | "speaking";
type VoiceDiagnosticStep = "intro" | VoiceSkill | "results";

type VoiceDiagnosticProgress = {
  pronunciation: PronunciationBatchResult | null;
  listening: ListeningBatchResult | null;
  speaking: SpeakingBatchResult | null;
};

const assessmentSteps: Array<{
  key: Exclude<VoiceDiagnosticStep, "intro">;
  label: string;
}> = [
  { key: "pronunciation", label: "Pronunciation" },
  { key: "listening", label: "Listening" },
  { key: "speaking", label: "Speaking" },
  { key: "results", label: "Results" },
];

const teacherSessionRoutes: Record<VoiceSkill, string> = {
  pronunciation: "/pronunciation-teacher",
  listening: "/listening-teacher",
  speaking: "/speaking-teacher",
};

const voiceSkillLabels: Record<VoiceSkill, string> = {
  pronunciation: "Pronunciation",
  listening: "Listening",
  speaking: "Speaking",
};

function getRecorderLabel(state: RecorderState) {
  if (state === "recording") {
    return "Recording";
  }
  if (state === "recorded") {
    return "Recording ready";
  }
  return "Not started";
}

function getRecommendedFocus(progress: VoiceDiagnosticProgress): VoiceSkill | null {
  const scoredSkills = (Object.entries(progress) as Array<[VoiceSkill, VoiceDiagnosticProgress[VoiceSkill]]>)
    .map(([skill, result]) => ({
      skill,
      score: result?.final_score,
    }))
    .filter((entry): entry is { skill: VoiceSkill; score: number } => typeof entry.score === "number");

  if (!scoredSkills.length) {
    return null;
  }

  scoredSkills.sort((left, right) => left.score - right.score);
  return scoredSkills[0].skill;
}

function updateIndex<T>(items: T[], index: number, value: T) {
  const nextItems = [...items];
  nextItems[index] = value;
  return nextItems;
}

function itemScoreSummary(items: Array<{ score: number }>) {
  return items.map((item) => item.score).join(" / ");
}

function ConsistencyNote({
  adjustment,
}: {
  adjustment: number;
}) {
  if (adjustment >= 0) {
    return null;
  }

  return (
    <p className="mt-3 text-sm font-semibold text-[#8a5a00]">
      Your score was adjusted slightly because item performance was inconsistent.
    </p>
  );
}

function Stepper({
  currentStep,
  progress,
}: {
  currentStep: VoiceDiagnosticStep;
  progress: VoiceDiagnosticProgress;
}) {
  const activeIndex = assessmentSteps.findIndex((step) => step.key === currentStep);

  return (
    <Card className="mt-8">
      <div className="flex flex-col gap-5">
        <div>
          <p className="eyebrow">Voice Assessment Progress</p>
          <h2 className="mt-2 text-2xl font-black text-[#14213d]">Structured official assessment flow</h2>
          <p className="mt-3 text-[#60708a]">
            Complete three items per skill before the official mastery update is finalized.
          </p>
        </div>
        <div className="grid gap-3 md:grid-cols-4">
          {assessmentSteps.map((step, index) => {
            const isActive = activeIndex === index;
            const isCompleted =
              step.key === "results" ? currentStep === "results" : Boolean(progress[step.key as VoiceSkill]);

            return (
              <div
                className={`rounded-2xl border px-4 py-4 ${
                  isActive
                    ? "border-[#335cff] bg-[#eef3ff]"
                    : isCompleted
                      ? "border-[#9edfc9] bg-[#eefbf6]"
                      : "border-[#dce4ef] bg-[#f8fafc]"
                }`}
                key={step.key}
              >
                <div className="flex items-center gap-3">
                  <div
                    className={`flex h-9 w-9 items-center justify-center rounded-full text-sm font-black ${
                      isActive
                        ? "bg-[#335cff] text-white"
                        : isCompleted
                          ? "bg-[#20b486] text-white"
                          : "bg-white text-[#60708a]"
                    }`}
                  >
                    {index + 1}
                  </div>
                  <div>
                    <p className="text-sm font-bold text-[#14213d]">{step.label}</p>
                    <p className="text-xs text-[#60708a]">
                      {isCompleted ? "Completed" : isActive ? "Current step" : "Upcoming"}
                    </p>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </Card>
  );
}

function FinalSkillCard({
  title,
  result,
  fallbackBreakdown,
}: {
  title: string;
  result: PronunciationBatchResult | ListeningBatchResult | SpeakingBatchResult | null;
  fallbackBreakdown?: {
    final_score: number | null;
    item_scores: number[];
  } | null;
}) {
  const finalScore = result?.final_score ?? fallbackBreakdown?.final_score ?? null;
  const itemScores = result
    ? itemScoreSummary(result.items)
    : fallbackBreakdown?.item_scores.length
      ? fallbackBreakdown.item_scores.join(" / ")
      : null;

  return (
    <Card>
      <p className="eyebrow">{title}</p>
      {result || finalScore !== null ? (
        <>
          <h3 className="mt-2 text-2xl font-black text-[#14213d]">Final Score: {finalScore}%</h3>
          {result ? (
            <>
              <p className="mt-2 font-semibold text-[#60708a]">
                Status: {result.status} | Level: {result.level_code}
              </p>
              <p className="mt-3 text-sm font-bold text-[#60708a]">Item Scores: {itemScores}</p>
              <p className="mt-4 leading-7 text-[#42536b]">{result.feedback_summary || "No summary available."}</p>
              <ConsistencyNote adjustment={result.aggregation.consistency_adjustment} />
            </>
          ) : itemScores ? (
            <p className="mt-3 text-sm font-bold text-[#60708a]">Item Scores: {itemScores}</p>
          ) : null}
        </>
      ) : (
        <>
          <h3 className="mt-2 text-2xl font-black text-[#14213d]">Not completed yet</h3>
          <p className="mt-4 leading-7 text-[#42536b]">Complete this skill assessment to see the final score.</p>
        </>
      )}
    </Card>
  );
}

export default function VoiceDiagnosticPage() {
  const [step, setStep] = useState<VoiceDiagnosticStep>("intro");
  const [prompts, setPrompts] = useState<VoiceDiagnosticPrompts | null>(null);
  const [pronunciationItemIndex, setPronunciationItemIndex] = useState(0);
  const [listeningItemIndex, setListeningItemIndex] = useState(0);
  const [speakingItemIndex, setSpeakingItemIndex] = useState(0);
  const [pronunciationItemResults, setPronunciationItemResults] = useState<Array<PronunciationResult | null>>([]);
  const [listeningItemResults, setListeningItemResults] = useState<Array<ListeningResult | null>>([]);
  const [speakingItemResults, setSpeakingItemResults] = useState<Array<SpeakingResult | null>>([]);
  const [listeningAnswers, setListeningAnswers] = useState<string[]>([]);
  const [pronunciationResult, setPronunciationResult] = useState<PronunciationBatchResult | null>(null);
  const [listeningResult, setListeningResult] = useState<ListeningBatchResult | null>(null);
  const [speakingResult, setSpeakingResult] = useState<SpeakingBatchResult | null>(null);
  const [voiceReport, setVoiceReport] = useState<VoiceDiagnosticReport | null>(null);
  const [diagnosticSessionId, setDiagnosticSessionId] = useState<number | null>(null);
  const [diagnosticSessionState, setDiagnosticSessionState] = useState<VoiceDiagnosticSessionState | null>(null);
  const [recorderState, setRecorderState] = useState<RecorderState>("idle");
  const [speakingRecorderState, setSpeakingRecorderState] = useState<RecorderState>("idle");
  const [audioBlob, setAudioBlob] = useState<Blob | null>(null);
  const [speakingAudioBlob, setSpeakingAudioBlob] = useState<Blob | null>(null);
  const [error, setError] = useState("");
  const [loadingPrompt, setLoadingPrompt] = useState(true);
  const [startingSession, setStartingSession] = useState(false);
  const [playingAudio, setPlayingAudio] = useState<"pronunciation" | "listening" | "speaking" | null>(null);
  const [submittingPronunciation, setSubmittingPronunciation] = useState(false);
  const [submittingListening, setSubmittingListening] = useState(false);
  const [submittingSpeaking, setSubmittingSpeaking] = useState(false);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const speakingMediaRecorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const speakingStreamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<BlobPart[]>([]);
  const speakingChunksRef = useRef<BlobPart[]>([]);

  useEffect(() => {
    let active = true;
    getVoiceDiagnosticPrompts()
      .then((data) => {
        if (!active) {
          return;
        }

        setPrompts(data);
        setPronunciationItemResults(Array.from({ length: data.pronunciation.items.length }, () => null));
        setListeningItemResults(Array.from({ length: data.listening.items.length }, () => null));
        setSpeakingItemResults(Array.from({ length: data.speaking.items.length }, () => null));
        setListeningAnswers(Array.from({ length: data.listening.items.length }, () => ""));
      })
      .catch((err: unknown) => {
        if (active) {
          setError(err instanceof Error ? err.message : "Unable to load voice diagnostic prompts.");
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
      speakingStreamRef.current?.getTracks().forEach((track) => track.stop());
    };
  }, []);

  useEffect(() => {
    if (
      !diagnosticSessionId ||
      diagnosticSessionState?.session_status !== "completed"
    ) {
      return;
    }

    let active = true;
    getVoiceDiagnosticReport(diagnosticSessionId)
      .then((report) => {
        if (active) {
          setVoiceReport(report);
        }
      })
      .catch((err: unknown) => {
        if (active) {
          setError(
            err instanceof Error
              ? err.message
              : "Unable to load the final voice diagnostic report.",
          );
        }
      });

    return () => {
      active = false;
    };
  }, [diagnosticSessionId, diagnosticSessionState?.session_status]);

  const progress: VoiceDiagnosticProgress = {
    pronunciation: pronunciationResult,
    listening: listeningResult,
    speaking: speakingResult,
  };

  const recommendedFocus = getRecommendedFocus(progress);
  const reportRecommendedFocus = voiceReport?.recommended_focus ?? null;
  const persistedRecommendedFocus =
    diagnosticSessionState?.recommended_focus &&
    ["Pronunciation", "Listening", "Speaking"].includes(diagnosticSessionState.recommended_focus)
      ? diagnosticSessionState.recommended_focus
      : null;
  const recommendedTeacherRoute =
    voiceReport?.next_teacher_session?.href ??
    (recommendedFocus ? teacherSessionRoutes[recommendedFocus] : null);
  const pronunciationItems = prompts?.pronunciation.items ?? [];
  const listeningItems = prompts?.listening.items ?? [];
  const speakingItems = prompts?.speaking.items ?? [];
  const currentPronunciationPrompt = pronunciationItems[pronunciationItemIndex] ?? null;
  const currentListeningPrompt = listeningItems[listeningItemIndex] ?? null;
  const currentSpeakingPrompt = speakingItems[speakingItemIndex] ?? null;
  const currentPronunciationResult = pronunciationItemResults[pronunciationItemIndex] ?? null;
  const currentListeningResult = listeningItemResults[listeningItemIndex] ?? null;
  const currentSpeakingResult = speakingItemResults[speakingItemIndex] ?? null;
  const readyToStart =
    pronunciationItems.length === 3 && listeningItems.length === 3 && speakingItems.length === 3;
  const reportBreakdown = voiceReport?.skill_breakdown ?? [];
  const pronunciationBreakdown =
    reportBreakdown.find((entry) => entry.skill === "Pronunciation") ?? null;
  const listeningBreakdown =
    reportBreakdown.find((entry) => entry.skill === "Listening") ?? null;
  const speakingBreakdown =
    reportBreakdown.find((entry) => entry.skill === "Speaking") ?? null;
  const loadingReport =
    diagnosticSessionState?.session_status === "completed" &&
    voiceReport === null &&
    !error;

  async function playAudio(kind: "pronunciation" | "listening" | "speaking", text: string) {
    if (!text) {
      return;
    }

    setError("");
    setPlayingAudio(kind);

    try {
      const audio = await requestTTS(text);
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
    setAudioBlob(null);
    setPronunciationResult(null);
    setPronunciationItemResults((current) => updateIndex(current, pronunciationItemIndex, null));
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

  async function startSpeakingRecording() {
    if (!navigator.mediaDevices || typeof MediaRecorder === "undefined") {
      setError("Voice recording is not supported in this browser.");
      return;
    }

    setError("");
    setSpeakingAudioBlob(null);
    setSpeakingResult(null);
    setSpeakingItemResults((current) => updateIndex(current, speakingItemIndex, null));
    speakingChunksRef.current = [];

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      speakingStreamRef.current = stream;
      const recorder = new MediaRecorder(stream);
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          speakingChunksRef.current.push(event.data);
        }
      };
      recorder.onstop = () => {
        const recordedBlob = new Blob(speakingChunksRef.current, {
          type: recorder.mimeType || "audio/webm",
        });
        setSpeakingAudioBlob(recordedBlob);
        setSpeakingRecorderState("recorded");
        stream.getTracks().forEach((track) => track.stop());
      };
      speakingMediaRecorderRef.current = recorder;
      recorder.start();
      setSpeakingRecorderState("recording");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start recording.");
      setSpeakingRecorderState("idle");
    }
  }

  function stopSpeakingRecording() {
    const recorder = speakingMediaRecorderRef.current;
    if (recorder && recorder.state !== "inactive") {
      recorder.stop();
    }
  }

  async function submitPronunciationItem() {
    if (!audioBlob || !currentPronunciationPrompt) {
      setError("Record your voice before submitting this item.");
      return;
    }

    setError("");
    setSubmittingPronunciation(true);

    try {
      const itemResult = await evaluatePronunciationPreview(
        audioBlob,
        currentPronunciationPrompt.target_sentence,
      );
      const nextResults = updateIndex(pronunciationItemResults, pronunciationItemIndex, itemResult);
      setPronunciationItemResults(nextResults);

      if (pronunciationItemIndex === pronunciationItems.length - 1) {
        const completedItems = nextResults.filter((item): item is PronunciationResult => item !== null);
        if (completedItems.length === pronunciationItems.length) {
          const finalResult = await submitPronunciationDiagnosticBatch({
            sessionId: diagnosticSessionId ?? undefined,
            items: completedItems.map((item, index) => ({
              target_sentence: pronunciationItems[index].target_sentence,
              transcript: item.transcript,
            })),
          });
          setPronunciationResult(finalResult);
          setDiagnosticSessionId(finalResult.session_id);
          setDiagnosticSessionState(finalResult);
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Pronunciation evaluation failed.");
    } finally {
      setSubmittingPronunciation(false);
    }
  }

  async function submitListeningItem() {
    if (!currentListeningPrompt) {
      setError("Listening prompt is still loading.");
      return;
    }

    const answer = listeningAnswers[listeningItemIndex]?.trim() ?? "";
    if (!answer) {
      setError("Write your answer before submitting this item.");
      return;
    }

    setError("");
    setSubmittingListening(true);

    try {
      const itemResult = await evaluateListeningPreview(
        currentListeningPrompt.question,
        currentListeningPrompt.expected_answer,
        answer,
      );
      const nextResults = updateIndex(listeningItemResults, listeningItemIndex, itemResult);
      setListeningItemResults(nextResults);

      if (listeningItemIndex === listeningItems.length - 1) {
        const completedItems = nextResults.filter((item): item is ListeningResult => item !== null);
        if (completedItems.length === listeningItems.length) {
          const finalResult = await submitListeningDiagnosticBatch({
            sessionId: diagnosticSessionId ?? undefined,
            items: completedItems.map((item, index) => ({
              passage: listeningItems[index].passage,
              question: listeningItems[index].question,
              expected_answer: listeningItems[index].expected_answer,
              answer: item.user_answer,
            })),
          });
          setListeningResult(finalResult);
          setDiagnosticSessionId(finalResult.session_id);
          setDiagnosticSessionState(finalResult);
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Listening evaluation failed.");
    } finally {
      setSubmittingListening(false);
    }
  }

  async function submitSpeakingItem() {
    if (!speakingAudioBlob || !currentSpeakingPrompt) {
      setError("Record your speaking answer before submitting this item.");
      return;
    }

    setError("");
    setSubmittingSpeaking(true);

    try {
      const itemResult = await evaluateSpeakingPreview(speakingAudioBlob, currentSpeakingPrompt.question);
      const nextResults = updateIndex(speakingItemResults, speakingItemIndex, itemResult);
      setSpeakingItemResults(nextResults);

      if (speakingItemIndex === speakingItems.length - 1) {
        const completedItems = nextResults.filter((item): item is SpeakingResult => item !== null);
        if (completedItems.length === speakingItems.length) {
          const finalResult = await submitSpeakingDiagnosticBatch({
            sessionId: diagnosticSessionId ?? undefined,
            items: completedItems.map((item, index) => ({
              question: speakingItems[index].question,
              transcript: item.transcript,
            })),
          });
          setSpeakingResult(finalResult);
          setDiagnosticSessionId(finalResult.session_id);
          setDiagnosticSessionState(finalResult);
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Speaking evaluation failed.");
    } finally {
      setSubmittingSpeaking(false);
    }
  }

  function goToNextPronunciationItem() {
    setError("");
    setPronunciationItemIndex((current) => current + 1);
    setRecorderState("idle");
    setAudioBlob(null);
  }

  function goToNextListeningItem() {
    setError("");
    setListeningItemIndex((current) => current + 1);
  }

  function goToNextSpeakingItem() {
    setError("");
    setSpeakingItemIndex((current) => current + 1);
    setSpeakingRecorderState("idle");
    setSpeakingAudioBlob(null);
  }

  async function beginVoiceDiagnostic() {
    setError("");
    setStartingSession(true);
    setVoiceReport(null);

    try {
      const session = await startVoiceDiagnosticSession();
      setDiagnosticSessionId(session.session_id);
      setDiagnosticSessionState({
        session_id: session.session_id,
        session_status: session.status,
        recommended_focus: "",
        summary: "",
        started_at: session.started_at,
        completed_at: null,
      });
      setStep("pronunciation");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to start the voice diagnostic session.");
    } finally {
      setStartingSession(false);
    }
  }

  return (
    <main className="page-shell">
      <p className="eyebrow">Official voice assessment</p>
      <h1 className="page-title">Voice Diagnostic</h1>
      <p className="page-copy">
        Complete three official items each for pronunciation, listening, and
        speaking to update your saved voice mastery and unlock the final report.
      </p>

      {error ? <div className="error-box">{error}</div> : null}

      <Stepper currentStep={step} progress={progress} />

      {step === "intro" ? (
        <Card className="mt-8 max-w-4xl">
          <div className="grid gap-6 lg:grid-cols-[1.2fr_0.8fr]">
            <div>
              <p className="eyebrow">Assessment overview</p>
              <h2 className="mt-2 text-3xl font-black text-[#14213d]">Official Voice Assessment</h2>
              <p className="mt-4 leading-7 text-[#42536b]">
                Complete three items per skill. Only the final aggregate score for each voice skill updates
                official mastery. Teacher sessions remain practice-only.
              </p>
              <ul className="mt-6 grid gap-3 text-[#14213d]">
                <li className="rounded-2xl border border-[#dce4ef] bg-[#f8fafc] px-4 py-3">
                  Pronunciation clarity across 3 target sentences
                </li>
                <li className="rounded-2xl border border-[#dce4ef] bg-[#f8fafc] px-4 py-3">
                  Listening comprehension across 3 audio questions
                </li>
                <li className="rounded-2xl border border-[#dce4ef] bg-[#f8fafc] px-4 py-3">
                  Spoken communication across 3 speaking prompts
                </li>
              </ul>
            </div>

            <div className="rounded-[1.75rem] border border-[#dce4ef] bg-[#f7f9ff] p-6">
              <p className="eyebrow">Flow</p>
              <div className="mt-4 grid gap-3 text-sm font-semibold text-[#42536b]">
                <div className="rounded-2xl bg-white px-4 py-3">1. Pronunciation items 1 to 3</div>
                <div className="rounded-2xl bg-white px-4 py-3">2. Listening items 1 to 3</div>
                <div className="rounded-2xl bg-white px-4 py-3">3. Speaking items 1 to 3</div>
                <div className="rounded-2xl bg-white px-4 py-3">4. Voice diagnostic results</div>
              </div>
              <div className="note-box mt-5">
                {loadingPrompt
                  ? "Loading official assessment prompts..."
                  : readyToStart
                    ? `Prompts are ready at level ${prompts?.level_code}.`
                    : "Some assessment prompts are unavailable right now. Retry after the page finishes loading."}
              </div>
              <div className="mt-5">
                <Button
                  disabled={!readyToStart || loadingPrompt || startingSession}
                  onClick={beginVoiceDiagnostic}
                  type="button"
                >
                  {startingSession ? "Starting session..." : "Start Voice Diagnostic"}
                </Button>
                <Button className="mt-3" href="/voice-diagnostic/history" variant="secondary">
                  View Voice Diagnostic History
                </Button>
              </div>
            </div>
          </div>
        </Card>
      ) : null}

      {step === "pronunciation" ? (
        <>
          <Card className="mt-8 max-w-4xl">
            <div className="flex flex-col gap-5">
              <div>
                <p className="eyebrow">Step 1 of 3</p>
                <h2 className="mt-2 text-3xl font-black text-[#14213d]">Pronunciation Assessment</h2>
                <p className="mt-3 text-[#60708a]">
                  Item {pronunciationItemIndex + 1} of {pronunciationItems.length || 3}
                </p>
                <p className="mt-4 rounded-2xl border border-[#dce4ef] bg-[#f8fafc] p-4 text-lg leading-8 text-[#14213d]">
                  {currentPronunciationPrompt?.target_sentence || "Loading target sentence..."}
                </p>
                <p className="mt-4 text-sm font-bold text-[#60708a]">
                  Completed item scores:{" "}
                  {pronunciationItemResults.filter((item): item is PronunciationResult => item !== null).length
                    ? pronunciationItemResults
                        .filter((item): item is PronunciationResult => item !== null)
                        .map((item) => item.score)
                        .join(" / ")
                    : "None yet"}
                </p>
              </div>

              <div className="flex flex-wrap gap-3">
                <Button
                  disabled={!currentPronunciationPrompt || playingAudio === "pronunciation"}
                  onClick={() => playAudio("pronunciation", currentPronunciationPrompt?.target_sentence ?? "")}
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
                  onClick={submitPronunciationItem}
                  type="button"
                >
                  {submittingPronunciation ? "Evaluating..." : "Submit Item"}
                </Button>
              </div>

              <div className="note-box">Recording status: {getRecorderLabel(recorderState)}</div>
            </div>
          </Card>

          {currentPronunciationResult ? (
            <>
              <section className="mt-8 grid gap-4 lg:grid-cols-[1fr_1fr]">
                <Card>
                  <p className="eyebrow">Item result</p>
                  <h3 className="mt-2 text-2xl font-black text-[#14213d]">Score: {currentPronunciationResult.score}%</h3>
                  <p className="mt-2 font-semibold text-[#60708a]">{currentPronunciationResult.feedback}</p>
                </Card>

                <Card>
                  <p className="eyebrow">Transcript</p>
                  <p className="mt-3 leading-7 text-[#14213d]">{currentPronunciationResult.transcript}</p>
                  <p className="mt-4 text-sm font-bold text-[#60708a]">
                    Word accuracy: {currentPronunciationResult.word_accuracy}%
                  </p>
                  <p className="mt-2 text-sm text-[#60708a]">
                    Target completion: {currentPronunciationResult.breakdown.target_completion}%
                  </p>
                </Card>

                <Card>
                  <p className="eyebrow">Missing words</p>
                  <p className="mt-3 text-[#14213d]">
                    {currentPronunciationResult.missing_words.length
                      ? currentPronunciationResult.missing_words.join(", ")
                      : "None"}
                  </p>
                </Card>

                <Card>
                  <p className="eyebrow">Substitutions and extras</p>
                  <p className="mt-3 text-[#14213d]">
                    Extra words:{" "}
                    {currentPronunciationResult.extra_words.length
                      ? currentPronunciationResult.extra_words.join(", ")
                      : "None"}
                  </p>
                  <p className="mt-4 text-sm text-[#60708a]">
                    Substituted words:{" "}
                    {currentPronunciationResult.substituted_words?.length
                      ? currentPronunciationResult.substituted_words
                          .map((item) => `${item.expected} -> ${item.heard}`)
                          .join(", ")
                      : "None"}
                  </p>
                  <p className="mt-4 text-sm text-[#60708a]">
                    Sequence accuracy: {currentPronunciationResult.breakdown.sequence_accuracy}%
                  </p>
                </Card>
              </section>

              {pronunciationItemIndex < pronunciationItems.length - 1 ? (
                <div className="mt-6 flex flex-wrap gap-3">
                  <Button onClick={goToNextPronunciationItem} type="button">
                    Continue to Pronunciation Item {pronunciationItemIndex + 2}
                  </Button>
                </div>
              ) : null}
            </>
          ) : null}

          {pronunciationResult ? (
            <Card className="mt-8 max-w-4xl">
              <p className="eyebrow">Pronunciation assessment complete</p>
              <h3 className="mt-2 text-2xl font-black text-[#14213d]">
                Final Pronunciation Score: {pronunciationResult.final_score}%
              </h3>
              <p className="mt-3 text-[#60708a]">{pronunciationResult.feedback_summary}</p>
              <ConsistencyNote adjustment={pronunciationResult.aggregation.consistency_adjustment} />
              <div className="mt-6 flex flex-wrap gap-3">
                <Button
                  onClick={() => {
                    setError("");
                    setStep("listening");
                  }}
                  type="button"
                >
                  Continue to Listening
                </Button>
              </div>
            </Card>
          ) : null}
        </>
      ) : null}

      {step === "listening" ? (
        <>
          <Card className="mt-8 max-w-4xl">
            <div className="flex flex-col gap-5">
              <div>
                <p className="eyebrow">Step 2 of 3</p>
                <h2 className="mt-2 text-3xl font-black text-[#14213d]">Listening Assessment</h2>
                <p className="mt-3 text-[#60708a]">
                  Item {listeningItemIndex + 1} of {listeningItems.length || 3}
                </p>
                <div className="mt-4 rounded-2xl border border-[#dce4ef] bg-[#f8fafc] p-4">
                  <p className="text-sm font-bold uppercase tracking-[0.12em] text-[#60708a]">Question</p>
                  <p className="mt-3 text-lg leading-8 text-[#14213d]">
                    {currentListeningPrompt?.question || "Loading listening question..."}
                  </p>
                </div>
                <p className="mt-4 text-sm font-bold text-[#60708a]">
                  Completed item scores:{" "}
                  {listeningItemResults.filter((item): item is ListeningResult => item !== null).length
                    ? listeningItemResults
                        .filter((item): item is ListeningResult => item !== null)
                        .map((item) => item.score)
                        .join(" / ")
                    : "None yet"}
                </p>
              </div>

              <div className="flex flex-wrap gap-3">
                <Button
                  disabled={!currentListeningPrompt || playingAudio === "listening"}
                  onClick={() => playAudio("listening", currentListeningPrompt?.passage ?? "")}
                  type="button"
                >
                  {playingAudio === "listening" ? "Playing..." : "Play passage"}
                </Button>
              </div>

              <label>
                <span className="field-label">Your answer</span>
                <textarea
                  className="text-area"
                  onChange={(event) =>
                    setListeningAnswers((current) =>
                      updateIndex(current, listeningItemIndex, event.target.value),
                    )
                  }
                  placeholder="Type the answer you understood from the audio."
                  value={listeningAnswers[listeningItemIndex] ?? ""}
                />
              </label>

              <div>
                <Button
                  disabled={!currentListeningPrompt || submittingListening}
                  onClick={submitListeningItem}
                  type="button"
                >
                  {submittingListening ? "Evaluating..." : "Submit Item"}
                </Button>
              </div>
            </div>
          </Card>

          {currentListeningResult ? (
            <>
              <section className="mt-8 grid gap-4 lg:grid-cols-[1fr_1fr]">
                <Card>
                  <p className="eyebrow">Item result</p>
                  <h3 className="mt-2 text-2xl font-black text-[#14213d]">Score: {currentListeningResult.score}%</h3>
                  <p className="mt-2 font-semibold text-[#60708a]">{currentListeningResult.feedback}</p>
                </Card>

                <Card>
                  <p className="eyebrow">Keyword match</p>
                  <p className="mt-3 text-[#14213d]">
                    Correct detail: {currentListeningResult.breakdown.correct_detail}%
                  </p>
                  <p className="mt-4 text-[#14213d]">
                    Matched keywords:{" "}
                    {currentListeningResult.matched_keywords?.length
                      ? currentListeningResult.matched_keywords.join(", ")
                      : "None"}
                  </p>
                  <p className="mt-4 text-sm text-[#60708a]">
                    Missing keywords:{" "}
                    {currentListeningResult.missing_keywords?.length
                      ? currentListeningResult.missing_keywords.join(", ")
                      : "None"}
                  </p>
                  <p className="mt-4 text-sm text-[#60708a]">
                    Answer match: {currentListeningResult.answer_match ?? "Not available"}
                  </p>
                </Card>
              </section>

              {listeningItemIndex < listeningItems.length - 1 ? (
                <div className="mt-6 flex flex-wrap gap-3">
                  <Button onClick={goToNextListeningItem} type="button">
                    Continue to Listening Item {listeningItemIndex + 2}
                  </Button>
                </div>
              ) : null}
            </>
          ) : null}

          {listeningResult ? (
            <Card className="mt-8 max-w-4xl">
              <p className="eyebrow">Listening assessment complete</p>
              <h3 className="mt-2 text-2xl font-black text-[#14213d]">
                Final Listening Score: {listeningResult.final_score}%
              </h3>
              <p className="mt-3 text-[#60708a]">{listeningResult.feedback_summary}</p>
              <ConsistencyNote adjustment={listeningResult.aggregation.consistency_adjustment} />
              <div className="mt-6 flex flex-wrap gap-3">
                <Button
                  onClick={() => {
                    setError("");
                    setStep("speaking");
                  }}
                  type="button"
                >
                  Continue to Speaking
                </Button>
              </div>
            </Card>
          ) : null}
        </>
      ) : null}

      {step === "speaking" ? (
        <>
          <Card className="mt-8 max-w-4xl">
            <div className="flex flex-col gap-5">
              <div>
                <p className="eyebrow">Step 3 of 3</p>
                <h2 className="mt-2 text-3xl font-black text-[#14213d]">Speaking Assessment</h2>
                <p className="mt-3 text-[#60708a]">
                  Item {speakingItemIndex + 1} of {speakingItems.length || 3}
                </p>
                <p className="mt-4 rounded-2xl border border-[#dce4ef] bg-[#f8fafc] p-4 text-lg leading-8 text-[#14213d]">
                  {currentSpeakingPrompt?.question || "Loading speaking question..."}
                </p>
                <p className="mt-4 text-sm font-bold text-[#60708a]">
                  Completed item scores:{" "}
                  {speakingItemResults.filter((item): item is SpeakingResult => item !== null).length
                    ? speakingItemResults
                        .filter((item): item is SpeakingResult => item !== null)
                        .map((item) => item.score)
                        .join(" / ")
                    : "None yet"}
                </p>
              </div>

              <div className="flex flex-wrap gap-3">
                <Button
                  disabled={!currentSpeakingPrompt || playingAudio === "speaking"}
                  onClick={() => playAudio("speaking", currentSpeakingPrompt?.question ?? "")}
                  type="button"
                >
                  {playingAudio === "speaking" ? "Playing..." : "Play question"}
                </Button>
                <Button
                  disabled={speakingRecorderState === "recording"}
                  onClick={startSpeakingRecording}
                  type="button"
                  variant="secondary"
                >
                  Start recording
                </Button>
                <Button
                  disabled={speakingRecorderState !== "recording"}
                  onClick={stopSpeakingRecording}
                  type="button"
                  variant="secondary"
                >
                  Stop recording
                </Button>
                <Button
                  disabled={!speakingAudioBlob || submittingSpeaking}
                  onClick={submitSpeakingItem}
                  type="button"
                >
                  {submittingSpeaking ? "Evaluating..." : "Submit Item"}
                </Button>
              </div>

              <div className="note-box">Recording status: {getRecorderLabel(speakingRecorderState)}</div>
            </div>
          </Card>

          {currentSpeakingResult ? (
            <>
              <section className="mt-8 grid gap-4 lg:grid-cols-[1fr_1fr]">
                <Card>
                  <p className="eyebrow">Item result</p>
                  <h3 className="mt-2 text-2xl font-black text-[#14213d]">Score: {currentSpeakingResult.score}%</h3>
                  <p className="mt-2 font-semibold text-[#60708a]">{currentSpeakingResult.feedback}</p>
                </Card>

                <Card>
                  <p className="eyebrow">Transcript</p>
                  <p className="mt-3 leading-7 text-[#14213d]">{currentSpeakingResult.transcript}</p>
                  <p className="mt-4 text-sm text-[#60708a]">
                    Task relevance: {currentSpeakingResult.breakdown.task_relevance}%
                  </p>
                </Card>

                <Card>
                  <p className="eyebrow">Rubric summary</p>
                  <p className="mt-3 text-[#14213d]">
                    Completeness: {currentSpeakingResult.breakdown.completeness}%
                  </p>
                  <p className="mt-2 text-[#14213d]">Clarity: {currentSpeakingResult.breakdown.clarity}%</p>
                  <p className="mt-2 text-[#14213d]">
                    Grammar control: {currentSpeakingResult.breakdown.grammar_control}%
                  </p>
                  <p className="mt-2 text-[#14213d]">
                    Vocabulary range: {currentSpeakingResult.breakdown.vocabulary_range}%
                  </p>
                </Card>

                <Card>
                  <p className="eyebrow">Strengths</p>
                  <ul className="mt-3 grid gap-2 text-[#14213d]">
                    {currentSpeakingResult.strengths.length ? (
                      currentSpeakingResult.strengths.map((strength) => <li key={strength}>{strength}</li>)
                    ) : (
                      <li>No strengths returned.</li>
                    )}
                  </ul>
                </Card>

                <Card>
                  <p className="eyebrow">Improvement areas</p>
                  <ul className="mt-3 grid gap-2 text-[#14213d]">
                    {currentSpeakingResult.improvement_areas.length ? (
                      currentSpeakingResult.improvement_areas.map((area) => <li key={area}>{area}</li>)
                    ) : (
                      <li>No improvement areas returned.</li>
                    )}
                  </ul>
                </Card>
              </section>

              {speakingItemIndex < speakingItems.length - 1 ? (
                <div className="mt-6 flex flex-wrap gap-3">
                  <Button onClick={goToNextSpeakingItem} type="button">
                    Continue to Speaking Item {speakingItemIndex + 2}
                  </Button>
                </div>
              ) : null}
            </>
          ) : null}

          {speakingResult ? (
            <Card className="mt-8 max-w-4xl">
              <p className="eyebrow">Speaking assessment complete</p>
              <h3 className="mt-2 text-2xl font-black text-[#14213d]">
                Final Speaking Score: {speakingResult.final_score}%
              </h3>
              <p className="mt-3 text-[#60708a]">{speakingResult.feedback_summary}</p>
              <ConsistencyNote adjustment={speakingResult.aggregation.consistency_adjustment} />
              <div className="mt-6 flex flex-wrap gap-3">
                <Button
                  onClick={() => {
                    setError("");
                    setStep("results");
                  }}
                  type="button"
                >
                  View Voice Diagnostic Results
                </Button>
              </div>
            </Card>
          ) : null}
        </>
      ) : null}

      {step === "results" ? (
        <>
          <Card className="mt-8">
            <div className="grid gap-6 lg:grid-cols-[1.15fr_0.85fr]">
              <div>
                <p className="eyebrow">Voice Diagnostic Report</p>
                <h2 className="mt-2 text-3xl font-black text-[#14213d]">
                  Official Mastery Updated
                </h2>
                <p className="mt-4 leading-7 text-[#42536b]">
                  Your official voice mastery scores have been saved from this
                  completed assessment.
                </p>
                <div className="mt-6 rounded-2xl border border-[#9edfc9] bg-[#eefbf6] p-4">
                  <p className="text-sm font-black uppercase tracking-[0.12em] text-[#127a5a]">
                    Voice Diagnostic Saved
                  </p>
                  <p className="mt-2 text-[#1f4d3e]">
                    Your official voice assessment has been saved to your history.
                  </p>
                  <div className="mt-4 flex flex-wrap gap-3">
                    <Button href={voiceReport?.history_href ?? "/voice-diagnostic/history"}>
                      View Voice Diagnostic History
                    </Button>
                  </div>
                </div>
                <div className="mt-6 rounded-2xl border border-[#dce4ef] bg-[#f8fafc] p-5">
                  <p className="text-sm font-bold uppercase tracking-[0.12em] text-[#60708a]">
                    Voice Skill Scores
                  </p>
                  <div className="mt-4 grid gap-3">
                    <div className="flex items-center justify-between gap-4 border-b border-[#dce4ef] pb-3">
                      <span className="font-semibold text-[#42536b]">Pronunciation</span>
                      <span className="font-black text-[#14213d]">
                        {voiceReport?.scores?.Pronunciation ?? pronunciationResult?.final_score ?? "--"}%
                      </span>
                    </div>
                    <div className="flex items-center justify-between gap-4 border-b border-[#dce4ef] pb-3">
                      <span className="font-semibold text-[#42536b]">Listening</span>
                      <span className="font-black text-[#14213d]">
                        {voiceReport?.scores?.Listening ?? listeningResult?.final_score ?? "--"}%
                      </span>
                    </div>
                    <div className="flex items-center justify-between gap-4">
                      <span className="font-semibold text-[#42536b]">Speaking</span>
                      <span className="font-black text-[#14213d]">
                        {voiceReport?.scores?.Speaking ?? speakingResult?.final_score ?? "--"}%
                      </span>
                    </div>
                  </div>
                </div>
              </div>

              <div className="rounded-[1.75rem] border border-[#dce4ef] bg-[#f7f9ff] p-6">
                <p className="eyebrow">Recommended Focus</p>
                <h3 className="mt-2 text-2xl font-black text-[#14213d]">
                  {reportRecommendedFocus
                    ? reportRecommendedFocus
                    : persistedRecommendedFocus
                    ? persistedRecommendedFocus
                    : recommendedFocus
                      ? voiceSkillLabels[recommendedFocus]
                    : "Complete the assessment"}
                </h3>
                <p className="mt-3 text-sm font-bold uppercase tracking-[0.12em] text-[#60708a]">
                  Why this focus?
                </p>
                <p className="mt-3 leading-7 text-[#42536b]">
                  {voiceReport?.recommended_focus_reason
                    ? voiceReport.recommended_focus_reason
                    : diagnosticSessionState?.summary
                    ? diagnosticSessionState.summary
                    : recommendedFocus
                      ? "This is the lowest final voice skill score from the official assessment."
                    : "Complete the assessment to see your recommended focus."}
                </p>
                <p className="mt-4 leading-7 text-[#60708a]">
                  {voiceReport?.summary ??
                    "Practice in the matching teacher session, then return to the voice diagnostic later for another official check."}
                </p>
              </div>
            </div>
          </Card>

          <section className="mt-8 grid gap-4 lg:grid-cols-3">
            <FinalSkillCard
              fallbackBreakdown={pronunciationBreakdown}
              result={pronunciationResult}
              title="Pronunciation"
            />
            <FinalSkillCard
              fallbackBreakdown={listeningBreakdown}
              result={listeningResult}
              title="Listening"
            />
            <FinalSkillCard
              fallbackBreakdown={speakingBreakdown}
              result={speakingResult}
              title="Speaking"
            />
          </section>

          <Card className="mt-8">
            <p className="eyebrow">Recommended Next Step</p>
            <h3 className="mt-2 text-2xl font-black text-[#14213d]">
              Continue learning from your latest official voice mastery
            </h3>
            <p className="mt-3 text-[#60708a]">
              Teacher sessions remain practice-only. They help you improve without changing official mastery.
            </p>
            {loadingReport ? (
              <p className="mt-4 text-sm font-semibold text-[#60708a]">
                Loading final report guidance...
              </p>
            ) : null}

            <div className="mt-6 flex flex-wrap gap-3">
              {recommendedTeacherRoute ? (
                <Button href={recommendedTeacherRoute}>
                  {voiceReport?.next_teacher_session?.label ?? "Start matching Teacher Session"}
                </Button>
              ) : (
                <div className="note-box">
                  Complete the official assessment to unlock a recommended teacher session.
                </div>
              )}
              <Button href={voiceReport?.study_plan_href ?? "/study-plan?refresh=1"} variant="secondary">
                View Study Plan
              </Button>
              <Button href={voiceReport?.recommendation_href ?? "/recommendation"} variant="secondary">
                View Recommendation
              </Button>
              <Button href={voiceReport?.history_href ?? "/voice-diagnostic/history"} variant="secondary">
                View Voice Diagnostic History
              </Button>
              <Button href={voiceReport?.dashboard_href ?? "/dashboard"} variant="secondary">
                Return to Dashboard
              </Button>
            </div>
          </Card>
        </>
      ) : null}
    </main>
  );
}
