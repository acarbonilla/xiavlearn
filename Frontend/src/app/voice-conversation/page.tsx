"use client";

import { useEffect, useRef, useState, type ChangeEvent } from "react";

import Button from "@/components/Button";
import Card from "@/components/Card";
import {
  createVoiceConversationTurn,
  endVoiceConversationSession,
  getVoiceConversationSession,
  getVoiceConversationSessions,
  resolveApiAssetUrl,
  startVoiceConversationSession,
  type VoiceConversationSessionDetail,
  type VoiceConversationSessionSummary,
  type VoiceConversationTargetSkill,
} from "@/lib/api";

type RecorderState = "idle" | "recording" | "recorded";

type PendingAudio = {
  blob: Blob;
  filename: string;
  source: "upload" | "recording";
};

const targetSkillOptions: Array<{
  value: VoiceConversationTargetSkill;
  label: string;
  description: string;
}> = [
  {
    value: "speaking",
    label: "Speaking",
    description: "Open-ended response practice with teacher follow-up.",
  },
  {
    value: "listening",
    label: "Listening",
    description: "Focus on short, clear answers around listening comprehension.",
  },
  {
    value: "pronunciation",
    label: "Pronunciation",
    description: "Keep responses short and easy to repeat aloud.",
  },
  {
    value: "general",
    label: "General",
    description: "Balanced conversation practice without a narrow skill focus.",
  },
];

function formatDate(dateString: string) {
  try {
    return new Intl.DateTimeFormat(undefined, {
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
    }).format(new Date(dateString));
  } catch {
    return dateString;
  }
}

function getRecorderStatusLabel(state: RecorderState) {
  if (state === "recording") {
    return "Recording in progress";
  }
  if (state === "recorded") {
    return "Recording ready to send";
  }
  return "No recording yet";
}

function getSessionTitle(session: VoiceConversationSessionSummary) {
  return session.title || `${session.target_skill} practice`;
}

export default function VoiceConversationPage() {
  const [sessions, setSessions] = useState<VoiceConversationSessionSummary[]>([]);
  const [selectedSession, setSelectedSession] =
    useState<VoiceConversationSessionDetail | null>(null);
  const [loadingSessions, setLoadingSessions] = useState(true);
  const [loadingSessionDetail, setLoadingSessionDetail] = useState(false);
  const [startingSession, setStartingSession] = useState(false);
  const [submittingTurn, setSubmittingTurn] = useState(false);
  const [endingSession, setEndingSession] = useState(false);
  const [error, setError] = useState("");
  const [title, setTitle] = useState("Voice Conversation Practice");
  const [cefrLevel, setCefrLevel] = useState("");
  const [targetSkill, setTargetSkill] =
    useState<VoiceConversationTargetSkill>("speaking");
  const [transcript, setTranscript] = useState("");
  const [pendingAudio, setPendingAudio] = useState<PendingAudio | null>(null);
  const [recorderState, setRecorderState] = useState<RecorderState>("idle");
  const [playingTurnId, setPlayingTurnId] = useState<number | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const recordedChunksRef = useRef<BlobPart[]>([]);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    let active = true;

    getVoiceConversationSessions()
      .then(async (data) => {
        if (!active) {
          return;
        }

        setSessions(data);
        if (data.length) {
          setLoadingSessionDetail(true);
          try {
            const detail = await getVoiceConversationSession(data[0].id);
            if (active) {
              setSelectedSession(detail);
            }
          } catch (requestError) {
            if (active) {
              setError(
                requestError instanceof Error
                  ? requestError.message
                  : "Unable to load the latest conversation session.",
              );
            }
          } finally {
            if (active) {
              setLoadingSessionDetail(false);
            }
          }
        }
      })
      .catch((requestError) => {
        if (active) {
          setError(
            requestError instanceof Error
              ? requestError.message
              : "Unable to load voice conversation sessions.",
          );
        }
      })
      .finally(() => {
        if (active) {
          setLoadingSessions(false);
        }
      });

    return () => {
      active = false;
      streamRef.current?.getTracks().forEach((track) => track.stop());
    };
  }, []);

  async function refreshSessions(preferredSessionId?: number) {
    const nextSessions = await getVoiceConversationSessions();
    setSessions(nextSessions);

    const selectedId = preferredSessionId ?? selectedSession?.id ?? nextSessions[0]?.id;
    if (!selectedId) {
      setSelectedSession(null);
      return;
    }

    const detail = await getVoiceConversationSession(selectedId);
    setSelectedSession(detail);
  }

  async function handleSelectSession(sessionId: number) {
    setError("");
    setLoadingSessionDetail(true);
    try {
      const detail = await getVoiceConversationSession(sessionId);
      setSelectedSession(detail);
      setTranscript("");
      setPendingAudio(null);
      setRecorderState("idle");
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Unable to load this conversation session.",
      );
    } finally {
      setLoadingSessionDetail(false);
    }
  }

  async function handleStartSession() {
    setError("");
    setStartingSession(true);
    try {
      const startedSession = await startVoiceConversationSession({
        title: title.trim() || undefined,
        cefr_level: cefrLevel.trim() || undefined,
        target_skill: targetSkill,
      });
      await refreshSessions(startedSession.id);
      setTranscript("");
      setPendingAudio(null);
      setRecorderState("idle");
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Unable to start a new voice conversation session.",
      );
    } finally {
      setStartingSession(false);
    }
  }

  async function handleEndSession() {
    if (!selectedSession) {
      return;
    }

    setError("");
    setEndingSession(true);
    try {
      await endVoiceConversationSession(selectedSession.id);
      await refreshSessions(selectedSession.id);
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Unable to end this voice conversation session.",
      );
    } finally {
      setEndingSession(false);
    }
  }

  async function startRecording() {
    if (!navigator.mediaDevices || typeof MediaRecorder === "undefined") {
      setError("Voice recording is not supported in this browser. Use transcript or file upload instead.");
      return;
    }

    setError("");
    setPendingAudio(null);
    recordedChunksRef.current = [];

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      const recorder = new MediaRecorder(stream);
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          recordedChunksRef.current.push(event.data);
        }
      };
      recorder.onstop = () => {
        const blob = new Blob(recordedChunksRef.current, {
          type: recorder.mimeType || "audio/webm",
        });
        setPendingAudio({
          blob,
          filename: "voice-conversation-recording.webm",
          source: "recording",
        });
        setRecorderState("recorded");
        stream.getTracks().forEach((track) => track.stop());
      };

      mediaRecorderRef.current = recorder;
      recorder.start();
      setRecorderState("recording");
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Could not start recording.",
      );
      setRecorderState("idle");
    }
  }

  function stopRecording() {
    const recorder = mediaRecorderRef.current;
    if (recorder && recorder.state !== "inactive") {
      recorder.stop();
    }
  }

  function handleAudioFileChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0] ?? null;
    if (!file) {
      setPendingAudio(null);
      return;
    }

    setPendingAudio({
      blob: file,
      filename: file.name,
      source: "upload",
    });
    setRecorderState("idle");
  }

  async function handleSubmitTurn() {
    if (!selectedSession) {
      return;
    }
    if (selectedSession.status !== "active") {
      setError("Start a new session before sending another turn.");
      return;
    }

    const trimmedTranscript = transcript.trim();
    if (trimmedTranscript && pendingAudio) {
      setError("Use either transcript or audio for a turn, not both.");
      return;
    }
    if (!trimmedTranscript && !pendingAudio) {
      setError("Add a transcript or attach audio before sending.");
      return;
    }

    setError("");
    setSubmittingTurn(true);
    try {
      const payload = trimmedTranscript
        ? {
            user_transcript: trimmedTranscript,
            transcript_source: "manual" as const,
          }
        : (() => {
            const formData = new FormData();
            formData.append("audio_file", pendingAudio!.blob, pendingAudio!.filename);
            return formData;
          })();

      await createVoiceConversationTurn(selectedSession.id, payload);
      await refreshSessions(selectedSession.id);
      setTranscript("");
      setPendingAudio(null);
      setRecorderState("idle");
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Unable to send this conversation turn.",
      );
    } finally {
      setSubmittingTurn(false);
    }
  }

  async function playAiAudio(turnId: number, audioPath: string | null) {
    const audioUrl = resolveApiAssetUrl(audioPath);
    if (!audioUrl) {
      return;
    }

    setError("");
    setPlayingTurnId(turnId);
    try {
      const player = new Audio(audioUrl);
      player.onended = () => setPlayingTurnId(null);
      await player.play();
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Unable to play AI audio for this turn.",
      );
      setPlayingTurnId(null);
    }
  }

  const activeSkill = targetSkillOptions.find(
    (option) => option.value === targetSkill,
  );
  const canSendTurn =
    !!selectedSession &&
    selectedSession.status === "active" &&
    !submittingTurn &&
    !!(transcript.trim() || pendingAudio);

  return (
    <main className="page-shell">
      <p className="eyebrow">Turn-based voice practice</p>
      <h1 className="page-title">Voice Conversation Teacher</h1>
      <p className="page-copy">
        Start a practice-only conversation session, send transcript or audio
        one turn at a time, and review the AI teacher response with optional
        playback when audio is available.
      </p>

      {error ? <div className="error-box">{error}</div> : null}

      <section className="mt-8 grid gap-5 lg:grid-cols-[320px_1fr]">
        <Card className="flex flex-col gap-5">
          <div>
            <p className="text-sm font-bold uppercase tracking-wider text-[#335cff]">
              Session Library
            </p>
            <h2 className="mt-2 text-2xl font-black text-[#14213d]">
              Recent practice
            </h2>
            <p className="mt-3 text-sm leading-6 text-[#60708a]">
              Reload previous voice conversation sessions and continue active
              ones from the same page.
            </p>
          </div>

          {loadingSessions ? (
            <p className="text-sm text-[#60708a]">Loading sessions...</p>
          ) : sessions.length ? (
            <div className="grid gap-3">
              {sessions.map((session) => {
                const isSelected = selectedSession?.id === session.id;
                return (
                  <button
                    className={`rounded-2xl border p-4 text-left transition ${
                      isSelected
                        ? "border-[#335cff] bg-[#eef3ff]"
                        : "border-[#dce4ef] bg-[#f8fafc] hover:border-[#9cb2ff]"
                    }`}
                    key={session.id}
                    onClick={() => handleSelectSession(session.id)}
                    type="button"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="font-bold text-[#14213d]">
                          {getSessionTitle(session)}
                        </p>
                        <p className="mt-1 text-xs uppercase tracking-[0.12em] text-[#60708a]">
                          {session.target_skill} | {session.status}
                        </p>
                      </div>
                      <span className="text-xs font-semibold text-[#60708a]">
                        {formatDate(session.started_at)}
                      </span>
                    </div>
                  </button>
                );
              })}
            </div>
          ) : (
            <div className="note-box">
              No voice conversation sessions yet. Start one from the panel on the right.
            </div>
          )}
        </Card>

        <div className="grid gap-5">
          <Card>
            <div className="flex flex-wrap items-start justify-between gap-5">
              <div className="max-w-2xl">
                <p className="text-sm font-bold uppercase tracking-wider text-[#335cff]">
                  Start Session
                </p>
                <h2 className="mt-2 text-2xl font-black text-[#14213d]">
                  New voice conversation practice
                </h2>
                <p className="mt-3 leading-7 text-[#60708a]">
                  Choose a practice direction, set an optional level tag, and
                  start a turn-based session. This page never updates official
                  mastery.
                </p>
              </div>
              <Button
                disabled={startingSession}
                onClick={handleStartSession}
                type="button"
              >
                {startingSession ? "Starting..." : "Start Voice Session"}
              </Button>
            </div>

            <div className="mt-6 grid gap-4 md:grid-cols-[1.2fr_0.8fr]">
              <label>
                <span className="field-label">Session title</span>
                <input
                  className="text-input"
                  onChange={(event) => setTitle(event.target.value)}
                  placeholder="Voice Conversation Practice"
                  value={title}
                />
              </label>

              <label>
                <span className="field-label">CEFR level tag</span>
                <input
                  className="text-input"
                  maxLength={10}
                  onChange={(event) => setCefrLevel(event.target.value.toUpperCase())}
                  placeholder="A2"
                  value={cefrLevel}
                />
              </label>
            </div>

            <div className="mt-6 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
              {targetSkillOptions.map((option) => (
                <button
                  className={`rounded-2xl border p-4 text-left transition ${
                    targetSkill === option.value
                      ? "border-[#335cff] bg-[#eef3ff]"
                      : "border-[#dce4ef] bg-[#f8fafc] hover:border-[#9cb2ff]"
                  }`}
                  key={option.value}
                  onClick={() => setTargetSkill(option.value)}
                  type="button"
                >
                  <p className="font-bold text-[#14213d]">{option.label}</p>
                  <p className="mt-2 text-sm leading-6 text-[#60708a]">
                    {option.description}
                  </p>
                </button>
              ))}
            </div>

            <p className="mt-4 text-sm leading-6 text-[#60708a]">
              Current focus: <strong className="text-[#14213d]">{activeSkill?.label}</strong>.
            </p>
          </Card>

          <Card>
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <p className="text-sm font-bold uppercase tracking-wider text-[#335cff]">
                  Conversation Workspace
                </p>
                <h2 className="mt-2 text-2xl font-black text-[#14213d]">
                  {selectedSession
                    ? getSessionTitle(selectedSession)
                    : "Select or start a session"}
                </h2>
                <p className="mt-3 text-sm leading-6 text-[#60708a]">
                  {selectedSession
                    ? `Status: ${selectedSession.status} | Started ${formatDate(
                        selectedSession.started_at,
                      )}`
                    : "Start a new session to open the chat interface."}
                </p>
              </div>

              {selectedSession?.status === "active" ? (
                <Button
                  disabled={endingSession}
                  onClick={handleEndSession}
                  type="button"
                  variant="secondary"
                >
                  {endingSession ? "Ending..." : "End Session"}
                </Button>
              ) : null}
            </div>

            {loadingSessionDetail ? (
              <p className="mt-6 text-sm text-[#60708a]">Loading conversation detail...</p>
            ) : selectedSession ? (
              <>
                <div className="mt-6 grid gap-4 rounded-[1.5rem] border border-[#dce4ef] bg-[#f8fafc] p-4 md:grid-cols-3">
                  <div>
                    <p className="text-xs font-bold uppercase tracking-[0.14em] text-[#60708a]">
                      Target skill
                    </p>
                    <p className="mt-2 font-bold text-[#14213d]">
                      {selectedSession.target_skill}
                    </p>
                  </div>
                  <div>
                    <p className="text-xs font-bold uppercase tracking-[0.14em] text-[#60708a]">
                      CEFR tag
                    </p>
                    <p className="mt-2 font-bold text-[#14213d]">
                      {selectedSession.cefr_level || "Not set"}
                    </p>
                  </div>
                  <div>
                    <p className="text-xs font-bold uppercase tracking-[0.14em] text-[#60708a]">
                      Turns saved
                    </p>
                    <p className="mt-2 font-bold text-[#14213d]">
                      {selectedSession.turns.length}
                    </p>
                  </div>
                </div>

                <div className="mt-6 grid gap-4">
                  {selectedSession.turns.length ? (
                    selectedSession.turns.map((turn) => {
                      const aiAudioUrl = resolveApiAssetUrl(turn.ai_audio);
                      const userAudioUrl = resolveApiAssetUrl(turn.user_audio);
                      return (
                        <div className="grid gap-3" key={turn.id}>
                          <div className="ml-auto w-full max-w-3xl rounded-[1.6rem] border border-[#bfd7ff] bg-[#eef4ff] p-5">
                            <div className="flex items-center justify-between gap-3">
                              <p className="text-sm font-bold uppercase tracking-[0.14em] text-[#335cff]">
                                Learner Turn {turn.turn_number}
                              </p>
                              <span className="text-xs font-semibold text-[#60708a]">
                                {turn.transcript_source}
                              </span>
                            </div>
                            <p className="mt-3 leading-7 text-[#14213d]">
                              {turn.user_transcript}
                            </p>
                            {userAudioUrl ? (
                              <audio
                                className="mt-4 w-full"
                                controls
                                preload="none"
                                src={userAudioUrl}
                              />
                            ) : null}
                          </div>

                          <div className="w-full max-w-3xl rounded-[1.6rem] border border-[#dce4ef] bg-white p-5 shadow-[0_14px_32px_rgba(20,33,61,0.06)]">
                            <div className="flex flex-wrap items-center justify-between gap-3">
                              <p className="text-sm font-bold uppercase tracking-[0.14em] text-[#20b486]">
                                AI Teacher
                              </p>
                              <div className="flex flex-wrap gap-2">
                                {turn.ai_audio ? (
                                  <Button
                                    disabled={playingTurnId === turn.id}
                                    onClick={() => playAiAudio(turn.id, turn.ai_audio)}
                                    type="button"
                                    variant="secondary"
                                  >
                                    {playingTurnId === turn.id ? "Playing..." : "Play AI Audio"}
                                  </Button>
                                ) : null}
                              </div>
                            </div>
                            <p className="mt-3 leading-7 text-[#14213d]">
                              {turn.ai_response_text}
                            </p>
                            {aiAudioUrl ? (
                              <audio
                                className="mt-4 w-full"
                                controls
                                preload="none"
                                src={aiAudioUrl}
                              />
                            ) : null}
                          </div>
                        </div>
                      );
                    })
                  ) : (
                    <div className="note-box">
                      No turns yet. Send your first transcript or audio turn below.
                    </div>
                  )}
                </div>

                {selectedSession.status === "active" ? (
                  <div className="mt-6 rounded-[1.8rem] border border-[#dce4ef] bg-[linear-gradient(135deg,#ffffff_0%,#f7faff_100%)] p-5">
                    <div className="flex flex-wrap items-start justify-between gap-4">
                      <div>
                        <p className="text-sm font-bold uppercase tracking-[0.14em] text-[#335cff]">
                          Send Next Turn
                        </p>
                        <h3 className="mt-2 text-xl font-black text-[#14213d]">
                          Transcript or audio
                        </h3>
                        <p className="mt-2 max-w-2xl text-sm leading-6 text-[#60708a]">
                          Use one input per turn. Manual transcript is the safest
                          option. Audio upload and recording rely on backend STT.
                        </p>
                      </div>
                      <span className="rounded-full bg-[#eef3ff] px-3 py-1 text-sm font-bold text-[#335cff]">
                        Practice only
                      </span>
                    </div>

                    <div className="mt-5 grid gap-5 lg:grid-cols-[1.2fr_0.8fr]">
                      <div>
                        <label className="field-label" htmlFor="voice-conversation-transcript">
                          Manual transcript
                        </label>
                        <textarea
                          className="text-area"
                          id="voice-conversation-transcript"
                          onChange={(event) => setTranscript(event.target.value)}
                          placeholder="Type what you want to say to the teacher."
                          value={transcript}
                        />
                      </div>

                      <div className="grid gap-4">
                        <div className="rounded-2xl border border-[#dce4ef] bg-white p-4">
                          <p className="text-sm font-bold uppercase tracking-[0.14em] text-[#60708a]">
                            Upload audio
                          </p>
                          <input
                            accept="audio/*"
                            className="mt-4 block w-full text-sm text-[#42536b]"
                            onChange={handleAudioFileChange}
                            ref={fileInputRef}
                            type="file"
                          />
                          <p className="mt-3 text-sm leading-6 text-[#60708a]">
                            {pendingAudio?.source === "upload"
                              ? `Selected file: ${pendingAudio.filename}`
                              : "Choose an audio file if you want backend transcription."}
                          </p>
                        </div>

                        <div className="rounded-2xl border border-[#dce4ef] bg-white p-4">
                          <p className="text-sm font-bold uppercase tracking-[0.14em] text-[#60708a]">
                            Record audio
                          </p>
                          <div className="mt-4 flex flex-wrap gap-3">
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
                          </div>
                          <p className="mt-3 text-sm leading-6 text-[#60708a]">
                            {getRecorderStatusLabel(recorderState)}
                          </p>
                          {pendingAudio?.source === "recording" ? (
                            <p className="mt-2 text-sm font-semibold text-[#14213d]">
                              Recorded file ready: {pendingAudio.filename}
                            </p>
                          ) : null}
                        </div>
                      </div>
                    </div>

                    <div className="mt-5 flex flex-wrap gap-3">
                      <Button
                        disabled={!canSendTurn}
                        onClick={handleSubmitTurn}
                        type="button"
                      >
                        {submittingTurn ? "Sending..." : "Send Turn"}
                      </Button>
                      <Button
                        onClick={() => {
                          setTranscript("");
                          setPendingAudio(null);
                          setRecorderState("idle");
                          if (fileInputRef.current) {
                            fileInputRef.current.value = "";
                          }
                        }}
                        type="button"
                        variant="secondary"
                      >
                        Clear Draft
                      </Button>
                    </div>
                  </div>
                ) : (
                  <div className="note-box mt-6">
                    This session is read-only because it is already {selectedSession.status}.
                    Start a new session to continue practicing.
                  </div>
                )}
              </>
            ) : (
              <div className="note-box mt-6">
                No session selected yet. Start a session or choose one from the recent list.
              </div>
            )}
          </Card>
        </div>
      </section>
    </main>
  );
}
