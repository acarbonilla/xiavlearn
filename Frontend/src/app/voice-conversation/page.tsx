"use client";

import { useEffect, useRef, useState, type ChangeEvent, type MouseEvent } from "react";

import Button from "@/components/Button";
import Card from "@/components/Card";
import {
  createVoiceConversationTurn,
  deleteVoiceConversationSession,
  endVoiceConversationSession,
  getVoiceConversationRealtimeUrl,
  getVoiceConversationSession,
  getVoiceConversationSessions,
  resolveApiAssetUrl,
  startVoiceConversationSession,
  type VoiceConversationSessionDetail,
  type VoiceConversationSessionSummary,
  type VoiceConversationTargetSkill,
} from "@/lib/api";

type RecorderState = "idle" | "recording" | "recorded";
type InputMode = "transcript" | "upload" | "record";

type PendingAudio = {
  blob: Blob;
  filename: string;
  source: "upload" | "recording";
};

type RealtimeConnectionStatus = "idle" | "connecting" | "connected" | "error" | "stopped";
type RealtimeRecordingStatus =
  | "idle"
  | "requesting_permission"
  | "recording"
  | "stopping"
  | "stopped";

type RealtimeAiResponse = {
  responseId: string;
  responseSource: string;
  responseText: string;
  audioUrl: string | null;
  audioContentType: string | null;
  wasInterrupted: boolean;
};

type RealtimeServerEvent =
  | {
      type: "connected";
      protocol_version: string;
      realtime_stage: string;
      transport: string;
      session_id: number;
      message: string;
    }
  | {
      type: "session_status";
      protocol_version: string;
      session: {
        id: number;
        status: string;
        target_skill: string;
        cefr_level: string;
        turn_count: number;
        practice_only: boolean;
        realtime_stage: string;
      };
    }
  | {
      type: "pong";
      protocol_version: string;
      session_id: number;
      event_id?: string;
      client_ts?: string;
      server_ts: string;
    }
  | {
      type: "client_status_ack";
      protocol_version: string;
      session_id: number;
      event_id?: string;
      accepted: boolean;
      accepted_fields: string[];
      server_ts: string;
    }
  | {
      type: "audio_chunk_ack";
      protocol_version: string;
      session_id: number;
      event_id?: string;
      chunk_id: string;
      sequence: number;
      size_bytes: number;
      accepted: boolean;
      ingest_stage: string;
      server_ts: string;
    }
  | {
      type: "stt_status";
      protocol_version: string;
      session_id: number;
      provider: string;
      state: string;
      message: string;
      server_ts: string;
    }
  | {
      type: "transcript_partial" | "transcript_final";
      protocol_version: string;
      session_id: number;
      provider: string;
      transcript: string;
      is_final: boolean;
      speech_final: boolean;
      provider_event_type: string;
      server_ts: string;
    }
  | {
      type: "ai_response_start";
      protocol_version: string;
      session_id: number;
      response_id: string;
      practice_only: boolean;
      transcript: string;
      server_ts: string;
    }
  | {
      type: "ai_response_delta";
      protocol_version: string;
      session_id: number;
      response_id: string;
      sequence: number;
      delta_text: string;
      accumulated_text: string;
      server_ts: string;
    }
  | {
      type: "ai_response_final";
      protocol_version: string;
      session_id: number;
      response_id: string;
      practice_only: boolean;
      response_text: string;
      response_source: string;
      chunk_count: number;
      server_ts: string;
    }
  | {
      type: "ai_response_error";
      protocol_version: string;
      session_id: number;
      response_id: string;
      code: string;
      message: string;
      server_ts: string;
    }
  | {
      type: "tts_audio_start";
      protocol_version: string;
      session_id: number;
      response_id: string;
      provider: string;
      content_type: string;
      total_size_bytes: number;
      chunk_count: number;
      practice_only: boolean;
      server_ts: string;
    }
  | {
      type: "tts_audio_chunk";
      protocol_version: string;
      session_id: number;
      response_id: string;
      sequence: number;
      audio_base64: string;
      size_bytes: number;
      is_final: boolean;
      server_ts: string;
    }
  | {
      type: "tts_audio_complete";
      protocol_version: string;
      session_id: number;
      response_id: string;
      provider: string;
      content_type: string;
      total_size_bytes: number;
      chunk_count: number;
      practice_only: boolean;
      server_ts: string;
    }
  | {
      type: "tts_audio_error";
      protocol_version: string;
      session_id: number;
      response_id: string;
      code: string;
      message: string;
      server_ts: string;
    }
  | {
      type: "assistant_interrupted";
      protocol_version: string;
      session_id: number;
      response_id: string | null;
      trigger: string;
      reason: string;
      previous_state: string;
      had_active_response: boolean;
      stop_playback: boolean;
      practice_only: boolean;
      server_ts: string;
    }
  | {
      type: "realtime_turn_persisted" | "realtime_turn_interrupted";
      protocol_version: string;
      session_id: number;
      response_id: string;
      turn: VoiceConversationSessionDetail["turns"][number];
      practice_only: boolean;
      server_ts: string;
    }
  | {
      type: "error";
      protocol_version: string;
      code: string;
      message: string;
      event_id?: string;
      for_type?: string;
    };

const REALTIME_CHUNK_TIMESLICE_MS = 1000;

const inputModeOptions: Array<{
  value: InputMode;
  label: string;
  description: string;
}> = [
  {
    value: "transcript",
    label: "Type Transcript",
    description: "Type your answer or paste what you said.",
  },
  {
    value: "upload",
    label: "Upload Audio",
    description: "Upload a file and let the backend transcribe it.",
  },
  {
    value: "record",
    label: "Record Audio",
    description: "Use your microphone only when you choose to record.",
  },
];

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

function getPreferredSessionId(
  sessionList: VoiceConversationSessionSummary[],
  preferredSessionId?: number,
) {
  if (preferredSessionId && sessionList.some((session) => session.id === preferredSessionId)) {
    return preferredSessionId;
  }
  return (
    sessionList.find((session) => session.status === "active")?.id ??
    sessionList[0]?.id ??
    null
  );
}

function getRecordingErrorMessage(error: unknown) {
  if (error instanceof DOMException) {
    if (["NotFoundError", "DevicesNotFoundError", "NotAllowedError"].includes(error.name)) {
      return "Microphone is not available. You can type a transcript or upload an audio file instead.";
    }
  }
  if (error instanceof Error) {
    if (
      /NotFoundError|DevicesNotFoundError|NotAllowedError|Requested device not found/i.test(
        `${error.name} ${error.message}`,
      )
    ) {
      return "Microphone is not available. You can type a transcript or upload an audio file instead.";
    }
    return error.message;
  }
  return "Microphone is not available. You can type a transcript or upload an audio file instead.";
}

function getRealtimeStatusTone(
  status: RealtimeConnectionStatus | RealtimeRecordingStatus,
) {
  if (status === "connected" || status === "recording") {
    return "border-[#b7ebd6] bg-[#effcf6] text-[#157347]";
  }
  if (status === "connecting" || status === "requesting_permission" || status === "stopping") {
    return "border-[#cfe0ff] bg-[#eef3ff] text-[#335cff]";
  }
  if (status === "error") {
    return "border-[#f5c2c7] bg-[#fff1f2] text-[#b42318]";
  }
  return "border-[#dce4ef] bg-white text-[#60708a]";
}

function getRealtimeConnectionLabel(status: RealtimeConnectionStatus) {
  if (status === "connecting") {
    return "Connecting";
  }
  if (status === "connected") {
    return "Connected";
  }
  if (status === "error") {
    return "Failed";
  }
  if (status === "stopped") {
    return "Stopped";
  }
  return "Idle";
}

function getRealtimeRecordingLabel(status: RealtimeRecordingStatus) {
  if (status === "requesting_permission") {
    return "Waiting for mic permission";
  }
  if (status === "recording") {
    return "Recording";
  }
  if (status === "stopping") {
    return "Stopping";
  }
  if (status === "stopped") {
    return "Stopped";
  }
  return "Idle";
}

function getPreferredRealtimeMimeType() {
  if (typeof MediaRecorder === "undefined" || !MediaRecorder.isTypeSupported) {
    return "";
  }

  const candidates = [
    "audio/webm;codecs=opus",
    "audio/webm",
    "audio/mp4",
  ];
  return candidates.find((candidate) => MediaRecorder.isTypeSupported(candidate)) ?? "";
}

function blobToBase64(blob: Blob) {
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onloadend = () => {
      if (typeof reader.result !== "string") {
        reject(new Error("Unable to read the recorded audio chunk."));
        return;
      }

      const encoded = reader.result.split(",")[1];
      if (!encoded) {
        reject(new Error("Unable to encode the recorded audio chunk."));
        return;
      }
      resolve(encoded);
    };
    reader.onerror = () => reject(new Error("Unable to read the recorded audio chunk."));
    reader.readAsDataURL(blob);
  });
}

function base64ToUint8Array(encoded: string) {
  const binary = window.atob(encoded);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }
  return bytes;
}

function parseRealtimeServerEvent(rawData: string): RealtimeServerEvent {
  const parsed = JSON.parse(rawData) as RealtimeServerEvent;
  if (!parsed || typeof parsed !== "object" || !("type" in parsed)) {
    throw new Error("Unexpected realtime message.");
  }
  return parsed;
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
  const [isSessionModalOpen, setIsSessionModalOpen] = useState(false);
  const [deletingSessionId, setDeletingSessionId] = useState<number | null>(null);
  const [pageError, setPageError] = useState("");
  const [pageNotice, setPageNotice] = useState("");
  const [sessionModalError, setSessionModalError] = useState("");
  const [recordingError, setRecordingError] = useState("");
  const [title, setTitle] = useState("Voice Conversation Practice");
  const [cefrLevel, setCefrLevel] = useState("");
  const [targetSkill, setTargetSkill] =
    useState<VoiceConversationTargetSkill>("speaking");
  const [inputMode, setInputMode] = useState<InputMode>("transcript");
  const [transcript, setTranscript] = useState("");
  const [pendingAudio, setPendingAudio] = useState<PendingAudio | null>(null);
  const [recorderState, setRecorderState] = useState<RecorderState>("idle");
  const [playingTurnId, setPlayingTurnId] = useState<number | null>(null);
  const [realtimeConnectionStatus, setRealtimeConnectionStatus] =
    useState<RealtimeConnectionStatus>("idle");
  const [realtimeRecordingStatus, setRealtimeRecordingStatus] =
    useState<RealtimeRecordingStatus>("idle");
  const [realtimeError, setRealtimeError] = useState("");
  const [realtimeNotice, setRealtimeNotice] = useState("");
  const [realtimeEventMessage, setRealtimeEventMessage] = useState(
    "Connect the realtime socket first, then start speaking when you are ready.",
  );
  const [realtimeChunkCount, setRealtimeChunkCount] = useState(0);
  const [realtimeAckCount, setRealtimeAckCount] = useState(0);
  const [realtimeLastAckSequence, setRealtimeLastAckSequence] = useState<number | null>(null);
  const [realtimeProtocolVersion, setRealtimeProtocolVersion] = useState("");
  const [realtimeTransport, setRealtimeTransport] = useState("");
  const [realtimeSessionStatus, setRealtimeSessionStatus] = useState("");
  const [realtimeSttState, setRealtimeSttState] = useState("Idle");
  const [realtimeAiState, setRealtimeAiState] = useState("Idle");
  const [realtimeTtsState, setRealtimeTtsState] = useState("Idle");
  const [realtimeTtsChunkCount, setRealtimeTtsChunkCount] = useState(0);
  const [realtimePartialTranscript, setRealtimePartialTranscript] = useState("");
  const [realtimeFinalTranscripts, setRealtimeFinalTranscripts] = useState<string[]>([]);
  const [realtimeAiStreamingText, setRealtimeAiStreamingText] = useState("");
  const [realtimeAiResponses, setRealtimeAiResponses] = useState<RealtimeAiResponse[]>([]);
  const [realtimePlayingResponseId, setRealtimePlayingResponseId] = useState<string | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const recordedChunksRef = useRef<BlobPart[]>([]);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const recordingPreviewRef = useRef<HTMLAudioElement | null>(null);
  const realtimeSocketRef = useRef<WebSocket | null>(null);
  const realtimeRecorderRef = useRef<MediaRecorder | null>(null);
  const realtimeStreamRef = useRef<MediaStream | null>(null);
  const realtimeChunkSequenceRef = useRef(0);
  const realtimeStatusEventRef = useRef(0);
  const realtimeStopRequestedRef = useRef(false);
  const realtimeDisconnectRequestedRef = useRef(false);
  const realtimeEndTurnRequestedRef = useRef(false);
  const realtimeActiveAiResponseIdRef = useRef<string | null>(null);
  const realtimeInterruptedResponseIdsRef = useRef<Set<string>>(new Set());
  const realtimeLastChunkSendRef = useRef<Promise<void> | null>(null);
  const realtimeTtsBuffersRef = useRef<
    Record<string, { contentType: string; chunks: string[] }>
  >({});
  const realtimeAudioUrlsRef = useRef<string[]>([]);
  const realtimePlayerRef = useRef<HTMLAudioElement | null>(null);

  function stopStream() {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
  }

  function discardActiveRecording() {
    const recorder = mediaRecorderRef.current;
    if (recorder && recorder.state !== "inactive") {
      recorder.ondataavailable = null;
      recorder.onstop = null;
      stopStream();
      recorder.stop();
    } else {
      stopStream();
    }
    mediaRecorderRef.current = null;
    recordedChunksRef.current = [];
  }

  function stopRealtimeTracks() {
    realtimeStreamRef.current?.getTracks().forEach((track) => track.stop());
    realtimeStreamRef.current = null;
  }

  function discardRealtimeCapture() {
    const recorder = realtimeRecorderRef.current;
    if (recorder && recorder.state !== "inactive") {
      recorder.ondataavailable = null;
      recorder.onstop = null;
      recorder.stop();
    }
    realtimeRecorderRef.current = null;
    stopRealtimeTracks();
  }

  function closeRealtimeSocket() {
    const socket = realtimeSocketRef.current;
    if (!socket) {
      return;
    }
    socket.onopen = null;
    socket.onmessage = null;
    socket.onerror = null;
    socket.onclose = null;
    if (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING) {
      socket.close(1000, "client_stop");
    }
    realtimeSocketRef.current = null;
  }

  function stopRealtimeGeneratedAudio() {
    const player = realtimePlayerRef.current;
    if (player) {
      player.pause();
      player.src = "";
      realtimePlayerRef.current = null;
    }
    setRealtimePlayingResponseId(null);
  }

  function revokeRealtimeAudioUrls() {
    realtimeAudioUrlsRef.current.forEach((url) => URL.revokeObjectURL(url));
    realtimeAudioUrlsRef.current = [];
  }

  function resetRealtimeAudioBuffers() {
    realtimeTtsBuffersRef.current = {};
    setRealtimeTtsChunkCount(0);
  }

  function clearRealtimeGeneratedAudioArtifacts() {
    stopRealtimeGeneratedAudio();
    revokeRealtimeAudioUrls();
    resetRealtimeAudioBuffers();
  }

  async function playRealtimeAiResponse(
    responseId: string,
    audioUrl: string | null,
    failureMessage: string,
  ) {
    if (!audioUrl) {
      return;
    }

    stopRealtimeGeneratedAudio();
    setRealtimeError("");
    setRealtimeNotice("");
    setRealtimePlayingResponseId(responseId);

    try {
      const player = new Audio(audioUrl);
      realtimePlayerRef.current = player;
      player.onended = () => {
        if (realtimePlayerRef.current === player) {
          realtimePlayerRef.current = null;
        }
        setRealtimePlayingResponseId(null);
        setRealtimeTtsState("Ready to play");
        sendAssistantPlaybackComplete(responseId);
      };
      player.onerror = () => {
        if (realtimePlayerRef.current === player) {
          realtimePlayerRef.current = null;
        }
        setRealtimePlayingResponseId(null);
        setRealtimeNotice(failureMessage);
        setRealtimeTtsState("Playback error");
      };
      await player.play();
      setRealtimeTtsState("Playing");
    } catch (requestError) {
      if (realtimePlayerRef.current) {
        realtimePlayerRef.current.pause();
        realtimePlayerRef.current.src = "";
        realtimePlayerRef.current = null;
      }
      setRealtimePlayingResponseId(null);
      setRealtimeNotice(
        requestError instanceof Error ? requestError.message : failureMessage,
      );
      setRealtimeTtsState("Ready to play");
    }
  }

  function hasInterruptibleAssistantOutput() {
    return (
      realtimeActiveAiResponseIdRef.current !== null ||
      realtimePlayingResponseId !== null ||
      realtimeAiResponses.some((response) => !response.wasInterrupted && !!response.audioUrl)
    );
  }

  function sendRealtimeClientStatus(status: Record<string, boolean | number | string | null>) {
    const socket = realtimeSocketRef.current;
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      return;
    }

    realtimeStatusEventRef.current += 1;

    socket.send(
      JSON.stringify({
        type: "client_status",
        event_id: `status-${realtimeStatusEventRef.current}`,
        status,
      }),
    );
  }

  function sendRealtimeInterrupt(source: string, reason: string) {
    const socket = realtimeSocketRef.current;
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      return false;
    }

    realtimeStatusEventRef.current += 1;
    socket.send(
      JSON.stringify({
        type: "interrupt",
        event_id: `interrupt-${realtimeStatusEventRef.current}`,
        source,
        reason,
      }),
    );
    return true;
  }

  function sendAssistantPlaybackComplete(responseId: string) {
    const socket = realtimeSocketRef.current;
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      return;
    }

    realtimeStatusEventRef.current += 1;
    socket.send(
      JSON.stringify({
        type: "assistant_playback_complete",
        event_id: `playback-${realtimeStatusEventRef.current}`,
        response_id: responseId,
      }),
    );
  }

  function sendRealtimeEndTurn() {
    const socket = realtimeSocketRef.current;
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      return false;
    }

    realtimeStatusEventRef.current += 1;
    socket.send(
      JSON.stringify({
        type: "end_turn",
        event_id: `end-turn-${realtimeStatusEventRef.current}`,
      }),
    );
    console.info("FRONTEND_END_TURN_SENT");
    return true;
  }

  function interruptAssistantOutputLocally(reason: string) {
    const activeResponseId = realtimeActiveAiResponseIdRef.current;
    const playingResponseId = realtimePlayingResponseId;
    if (activeResponseId) {
      realtimeInterruptedResponseIdsRef.current.add(activeResponseId);
    }
    if (playingResponseId) {
      realtimeInterruptedResponseIdsRef.current.add(playingResponseId);
    }
    stopRealtimeGeneratedAudio();
    realtimeActiveAiResponseIdRef.current = null;
    setRealtimeAiState("Interrupted");
    setRealtimeTtsState("Interrupted");
    setRealtimeEventMessage(reason);
    setRealtimeAiResponses((current) =>
      current.map((response) =>
        realtimeInterruptedResponseIdsRef.current.has(response.responseId)
          ? {
              ...response,
              wasInterrupted: true,
            }
          : response,
      ),
    );
  }

  function finalizeRealtimeStop(notice: string) {
    discardRealtimeCapture();
    closeRealtimeSocket();
    realtimeDisconnectRequestedRef.current = false;
    realtimeStopRequestedRef.current = false;
    realtimeActiveAiResponseIdRef.current = null;
    realtimeInterruptedResponseIdsRef.current.clear();
    setRealtimeConnectionStatus("stopped");
    setRealtimeRecordingStatus("stopped");
    setRealtimeSttState("Idle");
    setRealtimeAiState("Idle");
    setRealtimeTtsState("Idle");
    setRealtimeEventMessage("Realtime experiment stopped.");
    setRealtimeNotice(notice);
  }

  function handleRealtimeSttFailure(message: string, state: "error" | "unavailable") {
    realtimeStopRequestedRef.current = true;
    discardRealtimeCapture();
    setRealtimeConnectionStatus("connected");
    setRealtimeRecordingStatus("stopped");
    setRealtimeSttState(state === "unavailable" ? "Unavailable" : "Error");
    setRealtimeAiState("Idle");
    setRealtimeTtsState("Idle");
    setRealtimeError(message);
    setRealtimeEventMessage("Realtime speech capture stopped.");
    setRealtimeNotice(
      "The realtime socket is still connected, but speech capture is unavailable for this session. Disconnect or continue with the turn-based transcript/audio flow below.",
    );
  }

  function failRealtimeExperiment(message: string) {
    realtimeDisconnectRequestedRef.current = false;
    realtimeActiveAiResponseIdRef.current = null;
    realtimeInterruptedResponseIdsRef.current.clear();
    stopRealtimeGeneratedAudio();
    resetRealtimeAudioBuffers();
    discardRealtimeCapture();
    closeRealtimeSocket();
    setRealtimeConnectionStatus("error");
    setRealtimeRecordingStatus("stopped");
    setRealtimeSttState("Error");
    setRealtimeAiState("Error");
    setRealtimeTtsState("Error");
    setRealtimeError(message);
    setRealtimeEventMessage("Realtime experiment failed.");
    setRealtimeNotice(
      "Realtime is optional. Continue with the turn-based transcript or audio flow below.",
    );
  }

  async function finalizeRealtimeTurnAfterRecorderStop() {
    const lastChunkSend = realtimeLastChunkSendRef.current;
    if (lastChunkSend) {
      await lastChunkSend.catch(() => undefined);
    }

    if (realtimeDisconnectRequestedRef.current) {
      return;
    }

    setRealtimeSttState("Finalizing");
    setRealtimeEventMessage("Waiting for final transcript.");
    sendRealtimeClientStatus({
      capture_state: "finalizing_turn",
      chunk_sequence: realtimeChunkSequenceRef.current,
      input_mode: "realtime_test",
      mic_available: true,
    });
    if (sendRealtimeEndTurn()) {
      realtimeEndTurnRequestedRef.current = false;
    }
  }

  async function sendRealtimeAudioChunk(blob: Blob, mimeType: string, isFinal: boolean) {
    const socket = realtimeSocketRef.current;
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      return;
    }

    const sequence = realtimeChunkSequenceRef.current + 1;
    realtimeChunkSequenceRef.current = sequence;
    const audioBase64 = await blobToBase64(blob);
    const activeSocket = realtimeSocketRef.current;
    if (!activeSocket || activeSocket.readyState !== WebSocket.OPEN) {
      return;
    }

    activeSocket.send(
      JSON.stringify({
        type: "audio_chunk",
        event_id: `chunk-${sequence}`,
        chunk_id: `chunk-${sequence}`,
        sequence,
        mime_type: mimeType,
        size_bytes: blob.size,
        duration_ms: REALTIME_CHUNK_TIMESLICE_MS,
        is_final: false,
        audio_base64: audioBase64,
      }),
    );
    setRealtimeChunkCount((current) => current + 1);
    setRealtimeEventMessage(`Sent chunk ${sequence} (${blob.size} bytes).`);
    if (isFinal) {
      console.info("FRONTEND_FINAL_CHUNK_SENT");
      setRealtimeEventMessage("Final audio chunk sent. Waiting for transcript and teacher response.");
    }
  }

  async function beginRealtimeCapture() {
    if (realtimeRecorderRef.current && realtimeRecorderRef.current.state !== "inactive") {
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      realtimeStreamRef.current = stream;

      const preferredMimeType = getPreferredRealtimeMimeType();
      const recorder = preferredMimeType
        ? new MediaRecorder(stream, { mimeType: preferredMimeType })
        : new MediaRecorder(stream);

      recorder.ondataavailable = (event) => {
        if (event.data.size <= 0) {
          return;
        }
        const chunkMimeType = recorder.mimeType || event.data.type || "audio/webm";
        const isFinal = realtimeStopRequestedRef.current;
        const sendPromise = sendRealtimeAudioChunk(event.data, chunkMimeType, isFinal).catch(
          (error) => {
            failRealtimeExperiment(
              error instanceof Error
                ? error.message
                : "Unable to send a realtime audio chunk.",
            );
          },
        );
        realtimeLastChunkSendRef.current = sendPromise;
      };
      recorder.onstop = () => {
        console.info("FRONTEND_RECORDER_STOPPED");
        realtimeRecorderRef.current = null;
        stopRealtimeTracks();
        if (
          !realtimeDisconnectRequestedRef.current &&
          realtimeSocketRef.current?.readyState === WebSocket.OPEN
        ) {
          setRealtimeRecordingStatus("stopped");
          setRealtimeEventMessage("Microphone stopped. Waiting for final transcript.");
          if (realtimeEndTurnRequestedRef.current) {
            void finalizeRealtimeTurnAfterRecorderStop();
          }
        }
      };

      realtimeRecorderRef.current = recorder;
      realtimeStopRequestedRef.current = false;
      realtimeEndTurnRequestedRef.current = false;
      realtimeLastChunkSendRef.current = null;
      recorder.start(REALTIME_CHUNK_TIMESLICE_MS);
      setRealtimeRecordingStatus("recording");
      setRealtimeEventMessage("Microphone connected. Sending audio chunks.");
      sendRealtimeClientStatus({
        capture_state: "recording",
        chunk_sequence: realtimeChunkSequenceRef.current,
        input_mode: "realtime_test",
        mic_available: true,
      });
    } catch (error) {
      failRealtimeExperiment(getRecordingErrorMessage(error));
    }
  }

  async function handleConnectRealtime() {
    if (!selectedSession) {
      setRealtimeError("Select a voice conversation session before connecting realtime.");
      setRealtimeNotice("");
      return;
    }
    if (selectedSession.status !== "active") {
      setRealtimeError("Realtime is only available for active practice sessions.");
      setRealtimeNotice("Start a new session to keep using the existing V5A practice flow.");
      return;
    }

    setRealtimeError("");
    setRealtimeNotice("");
    if (realtimeSocketRef.current?.readyState === WebSocket.OPEN) {
      setRealtimeConnectionStatus("connected");
      setRealtimeRecordingStatus("idle");
      setRealtimeEventMessage("Realtime socket already connected. Start speaking when ready.");
      return;
    }

    discardRealtimeCapture();
    closeRealtimeSocket();
    realtimeDisconnectRequestedRef.current = false;
    realtimeStopRequestedRef.current = false;
    realtimeChunkSequenceRef.current = 0;
    realtimeStatusEventRef.current = 0;
    clearRealtimeGeneratedAudioArtifacts();
    setRealtimeChunkCount(0);
    setRealtimeAckCount(0);
    setRealtimeLastAckSequence(null);
    setRealtimeProtocolVersion("");
    setRealtimeTransport("");
    setRealtimeSessionStatus(selectedSession.status);
    setRealtimeSttState("Idle");
    setRealtimeAiState("Idle");
    setRealtimeTtsState("Idle");
    setRealtimeTtsChunkCount(0);
    setRealtimePartialTranscript("");
    setRealtimeFinalTranscripts([]);
    setRealtimeAiStreamingText("");
    setRealtimeAiResponses([]);
    setRealtimePlayingResponseId(null);
    realtimeActiveAiResponseIdRef.current = null;
    realtimeInterruptedResponseIdsRef.current.clear();
    setRealtimeConnectionStatus("connecting");
    setRealtimeRecordingStatus("idle");
    setRealtimeEventMessage("Opening realtime socket.");

    const socket = new WebSocket(getVoiceConversationRealtimeUrl(selectedSession.id));
    realtimeSocketRef.current = socket;

    socket.onopen = () => {
      setRealtimeConnectionStatus("connected");
      setRealtimeRecordingStatus("idle");
      setRealtimeEventMessage("Realtime socket connected. Start speaking when ready.");
      sendRealtimeClientStatus({
        capture_state: "idle",
        input_mode: "realtime_test",
        mic_available: !!navigator.mediaDevices,
      });
    };

    socket.onmessage = (event) => {
      try {
        const message = parseRealtimeServerEvent(event.data);
        setRealtimeProtocolVersion(message.protocol_version);

        if (message.type === "connected") {
          setRealtimeTransport(message.transport);
          setRealtimeEventMessage(message.message);
          return;
        }

        if (message.type === "session_status") {
          setRealtimeSessionStatus(message.session.status);
          return;
        }

        if (message.type === "audio_chunk_ack") {
          setRealtimeAckCount((current) => current + 1);
          setRealtimeLastAckSequence(message.sequence);
          setRealtimeEventMessage(
            `Backend acknowledged chunk ${message.sequence} (${message.size_bytes} bytes).`,
          );
          return;
        }

        if (message.type === "stt_status") {
          setRealtimeSttState(`${message.provider}: ${message.state}`);
          setRealtimeEventMessage(message.message);
          if (message.state === "no_speech") {
            setRealtimeError("");
            setRealtimeAiState("Idle");
            setRealtimeTtsState("Idle");
            setRealtimeNotice(message.message);
            return;
          }
          if (message.state === "unavailable" || message.state === "error") {
            handleRealtimeSttFailure(message.message, message.state);
          }
          return;
        }

        if (message.type === "transcript_partial") {
          setRealtimeSttState("Listening");
          setRealtimePartialTranscript(message.transcript);
          setRealtimeEventMessage("Receiving partial transcript from realtime STT.");
          return;
        }

        if (message.type === "transcript_final") {
          setRealtimeSttState("Transcript ready");
          setRealtimePartialTranscript("");
          setRealtimeFinalTranscripts((current) => [...current, message.transcript]);
          setRealtimeEventMessage("Received final transcript from realtime STT.");
          return;
        }

        if (message.type === "ai_response_start") {
          if (realtimeInterruptedResponseIdsRef.current.has(message.response_id)) {
            return;
          }
          realtimeActiveAiResponseIdRef.current = message.response_id;
          setRealtimeAiState("Generating");
          setRealtimeAiStreamingText("");
          setRealtimeEventMessage("Generating a practice-only AI teacher response.");
          return;
        }

        if (message.type === "ai_response_delta") {
          if (realtimeInterruptedResponseIdsRef.current.has(message.response_id)) {
            return;
          }
          realtimeActiveAiResponseIdRef.current = message.response_id;
          setRealtimeAiState("Streaming");
          setRealtimeAiStreamingText(message.accumulated_text);
          setRealtimeEventMessage(`Streaming AI teacher response chunk ${message.sequence}.`);
          return;
        }

        if (message.type === "ai_response_final") {
          if (realtimeInterruptedResponseIdsRef.current.has(message.response_id)) {
            return;
          }
          realtimeActiveAiResponseIdRef.current = message.response_id;
          setRealtimeAiState(`Completed (${message.response_source})`);
          setRealtimeAiStreamingText(message.response_text);
          setRealtimeAiResponses((current) => [
            ...current,
            {
              responseId: message.response_id,
              responseSource: message.response_source,
              responseText: message.response_text,
              audioUrl: null,
              audioContentType: null,
              wasInterrupted: false,
            },
          ]);
          setRealtimeTtsState("Generating audio");
          setRealtimeEventMessage("Received final AI teacher response. Generating teacher audio.");
          return;
        }

        if (message.type === "ai_response_error") {
          realtimeActiveAiResponseIdRef.current = null;
          setRealtimeAiState("Error");
          setRealtimeError(message.message);
          setRealtimeNotice(
            "Realtime AI response failed. Continue with the turn-based transcript or audio flow below.",
          );
          setRealtimeEventMessage("Realtime AI teacher response failed.");
          return;
        }

        if (message.type === "tts_audio_start") {
          if (realtimeInterruptedResponseIdsRef.current.has(message.response_id)) {
            return;
          }
          realtimeTtsBuffersRef.current[message.response_id] = {
            contentType: message.content_type,
            chunks: [],
          };
          setRealtimeTtsState(`Receiving audio (${message.provider})`);
          setRealtimeTtsChunkCount(0);
          setRealtimeEventMessage("Receiving AI teacher audio from the backend.");
          return;
        }

        if (message.type === "tts_audio_chunk") {
          if (realtimeInterruptedResponseIdsRef.current.has(message.response_id)) {
            return;
          }
          const buffer = realtimeTtsBuffersRef.current[message.response_id];
          if (!buffer) {
            realtimeTtsBuffersRef.current[message.response_id] = {
              contentType: "audio/mpeg",
              chunks: [message.audio_base64],
            };
          } else {
            buffer.chunks.push(message.audio_base64);
          }
          setRealtimeTtsChunkCount((current) => current + 1);
          setRealtimeEventMessage(`Receiving AI teacher audio chunk ${message.sequence}.`);
          return;
        }

        if (message.type === "tts_audio_complete") {
          if (realtimeInterruptedResponseIdsRef.current.has(message.response_id)) {
            delete realtimeTtsBuffersRef.current[message.response_id];
            return;
          }
          const buffer = realtimeTtsBuffersRef.current[message.response_id];
          if (!buffer) {
            setRealtimeTtsState("Audio assembly error");
            setRealtimeNotice(
              "Realtime teacher audio finished without buffered chunks. You can keep using the text response above.",
            );
            return;
          }

          const audioParts = buffer.chunks.map((chunk) => base64ToUint8Array(chunk));
          const audioBlob = new Blob(audioParts, { type: message.content_type });
          const audioUrl = URL.createObjectURL(audioBlob);
          realtimeAudioUrlsRef.current.push(audioUrl);
          delete realtimeTtsBuffersRef.current[message.response_id];

          setRealtimeTtsState("Ready to play");
          setRealtimeAiResponses((current) =>
            current.map((response) =>
              response.responseId === message.response_id
                ? {
                    ...response,
                    audioUrl,
                    audioContentType: message.content_type,
                  }
                : response,
            ),
          );
          setRealtimeEventMessage("AI teacher audio is ready to play.");
          void playRealtimeAiResponse(
            message.response_id,
            audioUrl,
            "AI teacher audio is ready, but autoplay was blocked. Use the play button below.",
          );
          return;
        }

        if (message.type === "tts_audio_error") {
          if (realtimeInterruptedResponseIdsRef.current.has(message.response_id)) {
            return;
          }
          realtimeActiveAiResponseIdRef.current = null;
          delete realtimeTtsBuffersRef.current[message.response_id];
          setRealtimeTtsState("Audio unavailable");
          setRealtimeNotice(
            `${message.message} The text response is still available above, and the turn-based flow remains available below.`,
          );
          setRealtimeEventMessage("Realtime teacher audio generation failed.");
          return;
        }

        if (message.type === "realtime_turn_persisted") {
          void refreshSessions(message.session_id).catch(() => undefined);
          setRealtimeEventMessage("Realtime practice turn saved to history.");
          setRealtimeNotice(
            "Realtime turn saved. You can keep speaking here or continue with the V5A transcript/audio flow below.",
          );
          return;
        }

        if (message.type === "realtime_turn_interrupted") {
          void refreshSessions(message.session_id).catch(() => undefined);
          setRealtimeEventMessage("Saved realtime turn marked as interrupted.");
          return;
        }

        if (message.type === "assistant_interrupted") {
          if (message.response_id) {
            realtimeInterruptedResponseIdsRef.current.add(message.response_id);
          }
          if (message.stop_playback) {
            stopRealtimeGeneratedAudio();
          }
          realtimeActiveAiResponseIdRef.current = null;
          delete realtimeTtsBuffersRef.current[message.response_id ?? ""];
          setRealtimeAiState("Interrupted");
          setRealtimeTtsState("Interrupted");
          setRealtimeAiStreamingText("");
          setRealtimeAiResponses((current) =>
            current.map((response) =>
              response.responseId === message.response_id
                ? {
                    ...response,
                    wasInterrupted: true,
                  }
                : response,
            ),
          );
          setRealtimeEventMessage(message.reason);
          return;
        }

        if (message.type === "client_status_ack") {
          setRealtimeEventMessage("Realtime status acknowledged by backend.");
          return;
        }

        if (message.type === "pong") {
          setRealtimeEventMessage(`Realtime heartbeat received at ${message.server_ts}.`);
          return;
        }

        if (message.type === "error") {
          failRealtimeExperiment(message.message);
        }
      } catch (error) {
        failRealtimeExperiment(
          error instanceof Error ? error.message : "Unable to read a realtime server message.",
        );
      }
    };

    socket.onerror = () => {
      setRealtimeEventMessage("Realtime socket reported an error.");
    };

    socket.onclose = (event) => {
      const userStopped = realtimeDisconnectRequestedRef.current;
      discardRealtimeCapture();
      closeRealtimeSocket();
      if (userStopped) {
        finalizeRealtimeStop(
          "Realtime test stopped. The turn-based transcript and audio controls remain available below.",
        );
        return;
      }

      const closeReason =
        event.code === 4401
          ? "Realtime authentication failed. Please log in again."
          : event.code === 4404
            ? "This realtime session is unavailable or no longer belongs to you."
            : "Realtime connection closed unexpectedly.";
      setRealtimeConnectionStatus("error");
      setRealtimeRecordingStatus("stopped");
      setRealtimeError(closeReason);
      setRealtimeEventMessage("Realtime connection closed.");
      setRealtimeNotice(
        "Fallback is still available. Continue with the turn-based transcript or audio flow below.",
      );
    };
  }

  async function handleStartRealtimeCapture() {
    if (!selectedSession) {
      setRealtimeError("Select a voice conversation session before starting to speak.");
      setRealtimeNotice("");
      return;
    }
    if (selectedSession.status !== "active") {
      setRealtimeError("Realtime speech capture is only available for active practice sessions.");
      setRealtimeNotice("Start a new session to keep using the existing V5A practice flow.");
      return;
    }
    if (!navigator.mediaDevices || typeof MediaRecorder === "undefined") {
      setRealtimeError(
        "Realtime microphone streaming is not available in this browser. Use the turn-based controls below instead.",
      );
      setRealtimeNotice(
        "V5A remains available. Type a transcript, upload audio, or record a turn below.",
      );
      return;
    }

    const socket = realtimeSocketRef.current;
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      setRealtimeError("Connect realtime before you start speaking.");
      setRealtimeNotice(
        "Open the websocket first with Connect Realtime, or continue with the V5A controls below.",
      );
      return;
    }

    setRealtimeError("");
    setRealtimeNotice("");
    realtimeDisconnectRequestedRef.current = false;
    if (hasInterruptibleAssistantOutput()) {
      interruptAssistantOutputLocally("Learner interrupted the current teacher output.");
      sendRealtimeInterrupt(
        "learner_speaking",
        "Learner started speaking while the teacher output was active.",
      );
    }
    setRealtimeRecordingStatus("requesting_permission");
    setRealtimeEventMessage("Requesting microphone permission.");
    await beginRealtimeCapture();
  }

  function handleEndRealtimeTurn() {
    const recorder = realtimeRecorderRef.current;
    if (!recorder || recorder.state === "inactive") {
      return;
    }

    console.info("FRONTEND_END_TURN_CLICKED");
    realtimeStopRequestedRef.current = true;
    realtimeEndTurnRequestedRef.current = true;
    setRealtimeError("");
    setRealtimeRecordingStatus("stopping");
    setRealtimeEventMessage("Ending the current learner turn.");
    sendRealtimeClientStatus({
      capture_state: "stopping_turn",
      chunk_sequence: realtimeChunkSequenceRef.current,
      input_mode: "realtime_test",
      mic_available: true,
    });
    recorder.stop();
  }

  function handleStopRealtimeTest() {
    if (
      !realtimeSocketRef.current &&
      !realtimeRecorderRef.current &&
      realtimeConnectionStatus !== "connected" &&
      realtimeConnectionStatus !== "connecting"
    ) {
      return;
    }

    realtimeDisconnectRequestedRef.current = true;
    realtimeStopRequestedRef.current = true;
    setRealtimeError("");
    setRealtimeEventMessage("Disconnecting realtime experiment.");
    sendRealtimeClientStatus({
      capture_state: "disconnecting",
      chunk_sequence: realtimeChunkSequenceRef.current,
      input_mode: "realtime_test",
      mic_available: true,
    });

    const recorder = realtimeRecorderRef.current;
    if (recorder && recorder.state !== "inactive") {
      recorder.stop();
    }
    stopRealtimeGeneratedAudio();
    closeRealtimeSocket();
    finalizeRealtimeStop(
      "Realtime test stopped. The turn-based transcript and audio controls remain available below.",
    );
  }

  async function handleInterruptAndSpeak() {
    const socket = realtimeSocketRef.current;
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      return;
    }

    interruptAssistantOutputLocally("Learner interrupted the current teacher output.");
    sendRealtimeInterrupt(
      "interrupt_button",
      "Learner interrupted the current AI output to speak again.",
    );
    setRealtimeRecordingStatus("requesting_permission");
    setRealtimeNotice("");
    await beginRealtimeCapture();
  }

  useEffect(() => {
    let active = true;
    const interruptedResponseIds = realtimeInterruptedResponseIdsRef.current;

    getVoiceConversationSessions()
      .then(async (data) => {
        if (!active) {
          return;
        }

        setSessions(data);
        const selectedId = getPreferredSessionId(data);
        if (!selectedId) {
          if (active) {
            setSelectedSession(null);
          }
          return;
        }

        setLoadingSessionDetail(true);
        try {
          const detail = await getVoiceConversationSession(selectedId);
          if (active) {
            setSelectedSession(detail);
          }
        } catch (requestError) {
          if (active) {
            setPageError(
              requestError instanceof Error
                ? requestError.message
                : "Unable to load the latest conversation session.",
            );
            setPageNotice("");
          }
        } finally {
          if (active) {
            setLoadingSessionDetail(false);
          }
        }
      })
      .catch((requestError) => {
        if (active) {
          setPageError(
            requestError instanceof Error
              ? requestError.message
              : "Unable to load voice conversation sessions.",
          );
          setPageNotice("");
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
      streamRef.current = null;

      const recorder = realtimeRecorderRef.current;
      if (recorder && recorder.state !== "inactive") {
        recorder.ondataavailable = null;
        recorder.onstop = null;
        recorder.stop();
      }
      realtimeRecorderRef.current = null;
      realtimeStreamRef.current?.getTracks().forEach((track) => track.stop());
      realtimeStreamRef.current = null;
      realtimeLastChunkSendRef.current = null;
      realtimeEndTurnRequestedRef.current = false;

      const socket = realtimeSocketRef.current;
      if (socket) {
        socket.onopen = null;
        socket.onmessage = null;
        socket.onerror = null;
        socket.onclose = null;
        if (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING) {
          socket.close(1000, "client_stop");
        }
      }
      realtimeSocketRef.current = null;
      stopRealtimeGeneratedAudio();
      revokeRealtimeAudioUrls();
      realtimeTtsBuffersRef.current = {};
      interruptedResponseIds.clear();
    };
  }, []);

  useEffect(() => {
    if (!isSessionModalOpen) {
      return;
    }

    const previousOverflow = document.body.style.overflow;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !startingSession) {
        setIsSessionModalOpen(false);
        setSessionModalError("");
      }
    };

    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", handleKeyDown);

    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [isSessionModalOpen, startingSession]);

  useEffect(() => {
    const previewElement = recordingPreviewRef.current;
    if (!previewElement) {
      return;
    }
    if (pendingAudio?.source !== "recording") {
      previewElement.removeAttribute("src");
      previewElement.load();
      return;
    }

    const nextPreviewUrl = URL.createObjectURL(pendingAudio.blob);
    previewElement.src = nextPreviewUrl;

    return () => URL.revokeObjectURL(nextPreviewUrl);
  }, [pendingAudio]);

  function resetComposer(nextMode: InputMode = "transcript") {
    discardActiveRecording();
    setInputMode(nextMode);
    setTranscript("");
    setPendingAudio(null);
    setRecorderState("idle");
    setRecordingError("");
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  }

  function resetSessionSetup() {
    setTitle("Voice Conversation Practice");
    setCefrLevel("");
    setTargetSkill("speaking");
    setSessionModalError("");
  }

  function openSessionModal() {
    resetSessionSetup();
    setPageError("");
    setPageNotice("");
    setIsSessionModalOpen(true);
  }

  function closeSessionModal() {
    if (startingSession) {
      return;
    }
    setIsSessionModalOpen(false);
    setSessionModalError("");
  }

  function clearUploadDraft() {
    setPendingAudio((current) => (current?.source === "upload" ? null : current));
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  }

  function clearRecordingDraft() {
    discardActiveRecording();
    setPendingAudio((current) => (current?.source === "recording" ? null : current));
    setRecorderState("idle");
    setRecordingError("");
  }

  function handleInputModeChange(nextMode: InputMode) {
    if (recorderState === "recording") {
      stopRecording();
    }
    setInputMode(nextMode);
    setPageError("");
    setRecordingError("");
  }

  async function refreshSessions(preferredSessionId?: number) {
    const nextSessions = await getVoiceConversationSessions();
    setSessions(nextSessions);

    const selectedId = getPreferredSessionId(nextSessions, preferredSessionId ?? selectedSession?.id);
    if (!selectedId) {
      setSelectedSession(null);
      return;
    }

    const detail = await getVoiceConversationSession(selectedId);
    setSelectedSession(detail);
  }

  async function handleSelectSession(sessionId: number) {
    handleStopRealtimeTest();
    setPageError("");
    setPageNotice("");
    setLoadingSessionDetail(true);
    try {
      const detail = await getVoiceConversationSession(sessionId);
      setSelectedSession(detail);
      resetComposer();
    } catch (requestError) {
      setPageError(
        requestError instanceof Error
          ? requestError.message
          : "Unable to load this conversation session.",
      );
    } finally {
      setLoadingSessionDetail(false);
    }
  }

  async function handleStartSession() {
    handleStopRealtimeTest();
    setPageError("");
    setPageNotice("");
    setSessionModalError("");
    setStartingSession(true);
    try {
      const startedSession = await startVoiceConversationSession({
        title: title.trim() || undefined,
        cefr_level: cefrLevel.trim() || undefined,
        target_skill: targetSkill,
      });
      await refreshSessions(startedSession.id);
      resetComposer();
      resetSessionSetup();
      setIsSessionModalOpen(false);
    } catch (requestError) {
      setSessionModalError(
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

    handleStopRealtimeTest();
    setPageError("");
    setPageNotice("");
    setEndingSession(true);
    try {
      await endVoiceConversationSession(selectedSession.id);
      await refreshSessions(selectedSession.id);
    } catch (requestError) {
      setPageError(
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
      setRecordingError(
        "Microphone is not available. You can type a transcript or upload an audio file instead.",
      );
      return;
    }

    setRecordingError("");
    setPageError("");
    clearRecordingDraft();
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
        mediaRecorderRef.current = null;
        stream.getTracks().forEach((track) => track.stop());
        streamRef.current = null;
      };

      mediaRecorderRef.current = recorder;
      recorder.start();
      setRecorderState("recording");
    } catch (requestError) {
      stopStream();
      mediaRecorderRef.current = null;
      setRecordingError(getRecordingErrorMessage(requestError));
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
    setPageError("");
    const file = event.target.files?.[0] ?? null;
    if (!file) {
      clearUploadDraft();
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
      setPageError("Start a new session before sending another turn.");
      return;
    }

    const trimmedTranscript = transcript.trim();
    let payload:
      | {
          user_transcript: string;
          transcript_source: "manual";
        }
      | FormData;

    if (inputMode === "transcript") {
      if (!trimmedTranscript) {
        setPageError("Add a transcript before sending.");
        return;
      }
      payload = {
        user_transcript: trimmedTranscript,
        transcript_source: "manual",
      };
    } else if (inputMode === "upload") {
      if (pendingAudio?.source !== "upload") {
        setPageError("Choose an audio file before sending.");
        return;
      }
      payload = new FormData();
      payload.append("audio_file", pendingAudio.blob, pendingAudio.filename);
    } else {
      if (pendingAudio?.source !== "recording") {
        setRecordingError("Record your voice before sending.");
        return;
      }
      payload = new FormData();
      payload.append("audio_file", pendingAudio.blob, pendingAudio.filename);
    }

    setPageError("");
    setPageNotice("");
    setSubmittingTurn(true);
    try {
      await createVoiceConversationTurn(selectedSession.id, payload);
      await refreshSessions(selectedSession.id);
      resetComposer(inputMode);
    } catch (requestError) {
      setPageError(
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

    setPageError("");
    setPageNotice("");
    setPlayingTurnId(turnId);
    try {
      const player = new Audio(audioUrl);
      player.onended = () => setPlayingTurnId(null);
      await player.play();
    } catch (requestError) {
      setPageError(
        requestError instanceof Error
          ? requestError.message
          : "Unable to play AI audio for this turn.",
      );
      setPlayingTurnId(null);
    }
  }

  async function handleDeleteSession(
    event: MouseEvent<HTMLButtonElement>,
    session: VoiceConversationSessionSummary,
  ) {
    event.stopPropagation();
    const confirmed = window.confirm(
      "Are you sure you want to delete this practice session? This cannot be undone.",
    );
    if (!confirmed) {
      return;
    }

    setPageError("");
    setPageNotice("");
    if (selectedSession?.id === session.id) {
      handleStopRealtimeTest();
    }
    setDeletingSessionId(session.id);
    try {
      await deleteVoiceConversationSession(session.id);
      setSessions((current) => current.filter((item) => item.id !== session.id));
      if (selectedSession?.id === session.id) {
        setSelectedSession(null);
        resetComposer();
      }
      setPageNotice("Practice session deleted.");
    } catch {
      setPageError("We could not delete this practice session. Please try again.");
    } finally {
      setDeletingSessionId(null);
    }
  }

  const activeSkill = targetSkillOptions.find(
    (option) => option.value === targetSkill,
  );
  const canSendTranscript =
    !!selectedSession &&
    selectedSession.status === "active" &&
    !submittingTurn &&
    !!transcript.trim();
  const canSendUploadedAudio =
    !!selectedSession &&
    selectedSession.status === "active" &&
    !submittingTurn &&
    pendingAudio?.source === "upload";
  const canSendRecording =
    !!selectedSession &&
    selectedSession.status === "active" &&
    !submittingTurn &&
    pendingAudio?.source === "recording";
  const realtimeSocketReady =
    realtimeConnectionStatus === "connected" ||
    realtimeConnectionStatus === "connecting";
  const realtimeCanConnect =
    !!selectedSession &&
    selectedSession.status === "active" &&
    realtimeConnectionStatus !== "connecting" &&
    realtimeConnectionStatus !== "connected";
  const realtimeCanStartSpeaking =
    !!selectedSession &&
    selectedSession.status === "active" &&
    realtimeConnectionStatus === "connected" &&
    realtimeSttState !== "Error" &&
    realtimeSttState !== "Unavailable" &&
    realtimeRecordingStatus !== "recording" &&
    realtimeRecordingStatus !== "requesting_permission" &&
    realtimeRecordingStatus !== "stopping";
  const realtimeHasInterruptibleOutput =
    realtimePlayingResponseId !== null ||
    realtimeAiState === "Generating" ||
    realtimeAiState === "Streaming" ||
    realtimeTtsState === "Generating audio" ||
    realtimeTtsState.startsWith("Receiving audio") ||
    realtimeTtsState === "Ready to play" ||
    realtimeTtsState === "Playing" ||
    realtimeAiResponses.some((response) => !response.wasInterrupted && !!response.audioUrl);
  const realtimeCanEndTurn =
    realtimeConnectionStatus === "connected" &&
    (realtimeRecordingStatus === "recording" ||
      realtimeRecordingStatus === "requesting_permission" ||
      realtimeRecordingStatus === "stopping");
  const realtimeCanInterrupt =
    realtimeConnectionStatus === "connected" &&
    realtimeRecordingStatus !== "recording" &&
    realtimeRecordingStatus !== "requesting_permission" &&
    realtimeHasInterruptibleOutput;
  const realtimeCanDisconnect =
    realtimeSocketReady ||
    realtimeRecordingStatus === "recording" ||
    realtimeRecordingStatus === "requesting_permission";

  return (
    <main className="page-shell">
      <p className="eyebrow">Turn-based voice practice</p>
      <h1 className="page-title">Voice Conversation Teacher</h1>
      <p className="page-copy">
        Start a practice-only conversation session, send transcript or audio
        one turn at a time, and review the AI teacher response with optional
        playback when audio is available.
      </p>

      {pageError ? <div className="error-box">{pageError}</div> : null}
      {pageNotice ? <div className="note-box">{pageNotice}</div> : null}

      <section className="mt-8">
        <div className="flex flex-wrap items-end justify-between gap-5 rounded-[2rem] border border-[#dce4ef] bg-[linear-gradient(135deg,#ffffff_0%,#f2f6ff_100%)] p-6 shadow-[0_18px_45px_rgba(20,33,61,0.08)]">
          <div className="max-w-3xl">
            <p className="text-sm font-bold uppercase tracking-[0.16em] text-[#335cff]">
              Practice Session
            </p>
            <h2 className="mt-2 text-3xl font-black text-[#14213d]">
              Keep the workspace in view and start new practice from a modal.
            </h2>
            <p className="mt-3 text-sm leading-7 text-[#60708a]">
              Review recent practice on the left, keep the selected conversation
              open on the right, and start a fresh practice session only when
              you need one.
            </p>
          </div>
          <Button
            disabled={startingSession}
            onClick={openSessionModal}
            type="button"
          >
            New Practice Session
          </Button>
        </div>

        <div className="mt-5 grid gap-5 lg:grid-cols-[320px_1fr]">
          <Card className="flex flex-col gap-5 self-start">
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="text-sm font-bold uppercase tracking-wider text-[#335cff]">
                  Session Library
                </p>
                <h2 className="mt-2 text-2xl font-black text-[#14213d]">
                  Recent practice
                </h2>
              </div>
              <span className="rounded-full bg-[#eef3ff] px-3 py-1 text-xs font-bold uppercase tracking-[0.14em] text-[#335cff]">
                {sessions.length} saved
              </span>
            </div>

            <p className="text-sm leading-6 text-[#60708a]">
              Open a saved practice session or clean up old ones without leaving
              the workspace.
            </p>

            {loadingSessions ? (
              <p className="text-sm text-[#60708a]">Loading sessions...</p>
            ) : sessions.length ? (
              <div className="grid gap-3">
                {sessions.map((session) => {
                  const isSelected = selectedSession?.id === session.id;
                  return (
                    <div
                      className={`rounded-2xl border p-4 text-left transition ${
                        isSelected
                          ? "border-[#335cff] bg-[#eef3ff]"
                          : "border-[#dce4ef] bg-[#f8fafc] hover:border-[#9cb2ff]"
                      }`}
                      key={session.id}
                    >
                      <div className="flex items-start justify-between gap-3">
                        <button
                          className="flex-1 text-left"
                          onClick={() => handleSelectSession(session.id)}
                          type="button"
                        >
                          <p className="font-bold text-[#14213d]">
                            {getSessionTitle(session)}
                          </p>
                          <p className="mt-1 text-xs uppercase tracking-[0.12em] text-[#60708a]">
                            {session.target_skill} | {session.status}
                          </p>
                        </button>
                        <div className="flex flex-col items-end gap-2">
                          <span className="text-xs font-semibold text-[#60708a]">
                            {formatDate(session.started_at)}
                          </span>
                          <Button
                            className="px-3 py-2 text-xs"
                            disabled={deletingSessionId === session.id}
                            onClick={(event) => void handleDeleteSession(event, session)}
                            type="button"
                            variant="secondary"
                          >
                            {deletingSessionId === session.id ? "Deleting..." : "Delete"}
                          </Button>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="note-box">
                No practice sessions yet. Start a new practice session to begin.
              </div>
            )}
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
                    : "No practice session selected."}
                </h2>
                <p className="mt-3 text-sm leading-6 text-[#60708a]">
                  {selectedSession
                    ? `Status: ${selectedSession.status} | Started ${formatDate(
                        selectedSession.started_at,
                      )}`
                    : "Start a new practice session to begin."}
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

                <div className="mt-6 rounded-[1.8rem] border border-[#d7e4ff] bg-[linear-gradient(135deg,#f8fbff_0%,#eef4ff_100%)] p-5">
                  <div className="flex flex-wrap items-start justify-between gap-4">
                    <div>
                      <p className="text-sm font-bold uppercase tracking-[0.14em] text-[#335cff]">
                        Realtime Experiment
                      </p>
                      <h3 className="mt-2 text-xl font-black text-[#14213d]">
                        Stream microphone chunks to the V5B socket
                      </h3>
                      <p className="mt-2 max-w-2xl text-sm leading-6 text-[#60708a]">
                        This experiment uses the active practice session at{" "}
                        <code>/ws/voice-conversation/sessions/{selectedSession.id}/</code>.
                        It requests microphone permission only when you start
                        speaking, keeps the websocket alive across turns, and
                        supports controlled interruption so learner speech can
                        preempt teacher playback. If anything fails, the V5A
                        turn-based controls below remain available: Type
                        Transcript, Upload Audio, Record Audio, End Session,
                        and Practice History.
                      </p>
                    </div>
                    <span className="rounded-full bg-white px-3 py-1 text-sm font-bold text-[#335cff]">
                      Experimental
                    </span>
                  </div>

                  <div className="mt-5 grid gap-3 md:grid-cols-2 xl:grid-cols-6">
                    <div className="rounded-2xl border border-white/70 bg-white/90 p-4">
                      <p className="text-xs font-bold uppercase tracking-[0.14em] text-[#60708a]">
                        Connection
                      </p>
                      <span
                        className={`mt-3 inline-flex rounded-full border px-3 py-1 text-sm font-bold ${getRealtimeStatusTone(
                          realtimeConnectionStatus,
                        )}`}
                      >
                        {getRealtimeConnectionLabel(realtimeConnectionStatus)}
                      </span>
                    </div>
                    <div className="rounded-2xl border border-white/70 bg-white/90 p-4">
                      <p className="text-xs font-bold uppercase tracking-[0.14em] text-[#60708a]">
                        Recorder
                      </p>
                      <span
                        className={`mt-3 inline-flex rounded-full border px-3 py-1 text-sm font-bold ${getRealtimeStatusTone(
                          realtimeRecordingStatus,
                        )}`}
                      >
                        {getRealtimeRecordingLabel(realtimeRecordingStatus)}
                      </span>
                    </div>
                    <div className="rounded-2xl border border-white/70 bg-white/90 p-4">
                      <p className="text-xs font-bold uppercase tracking-[0.14em] text-[#60708a]">
                        Chunks
                      </p>
                      <p className="mt-3 text-2xl font-black text-[#14213d]">
                        {realtimeChunkCount}
                      </p>
                      <p className="mt-1 text-sm text-[#60708a]">
                        Acked: {realtimeAckCount}
                        {realtimeLastAckSequence ? ` | Last #${realtimeLastAckSequence}` : ""}
                      </p>
                    </div>
                    <div className="rounded-2xl border border-white/70 bg-white/90 p-4">
                      <p className="text-xs font-bold uppercase tracking-[0.14em] text-[#60708a]">
                        STT status
                      </p>
                      <p className="mt-3 text-sm font-bold text-[#14213d]">
                        {realtimeSttState}
                      </p>
                      <p className="mt-1 text-sm text-[#60708a]">
                        {realtimeTransport || "Awaiting socket"} | {realtimeProtocolVersion || "No protocol"} | Session{" "}
                        {realtimeSessionStatus || "unknown"}
                      </p>
                    </div>
                    <div className="rounded-2xl border border-white/70 bg-white/90 p-4">
                      <p className="text-xs font-bold uppercase tracking-[0.14em] text-[#60708a]">
                        AI status
                      </p>
                      <p className="mt-3 text-sm font-bold text-[#14213d]">
                        {realtimeAiState}
                      </p>
                      <p className="mt-1 text-sm text-[#60708a]">
                        Practice-only teacher text stream
                      </p>
                    </div>
                    <div className="rounded-2xl border border-white/70 bg-white/90 p-4">
                      <p className="text-xs font-bold uppercase tracking-[0.14em] text-[#60708a]">
                        TTS status
                      </p>
                      <p className="mt-3 text-sm font-bold text-[#14213d]">
                        {realtimeTtsState}
                      </p>
                      <p className="mt-1 text-sm text-[#60708a]">
                        Audio chunks: {realtimeTtsChunkCount}
                      </p>
                    </div>
                  </div>

                  {realtimeError ? (
                    <div className="mt-4 rounded-2xl border border-[#f5c2c7] bg-[#fff1f2] px-4 py-3 text-sm text-[#b42318]">
                      {realtimeError}
                    </div>
                  ) : null}
                  {realtimeNotice ? <div className="note-box mt-4">{realtimeNotice}</div> : null}

                  <div className="mt-4 rounded-2xl border border-[#dce4ef] bg-white p-4">
                    <p className="text-xs font-bold uppercase tracking-[0.14em] text-[#60708a]">
                      Latest realtime event
                    </p>
                    <p className="mt-2 text-sm leading-6 text-[#14213d]">
                      {realtimeEventMessage}
                    </p>
                  </div>

                  <div className="mt-4 grid gap-4 xl:grid-cols-3">
                    <div className="rounded-2xl border border-[#dce4ef] bg-white p-4">
                      <p className="text-xs font-bold uppercase tracking-[0.14em] text-[#60708a]">
                        Partial transcript
                      </p>
                      <p className="mt-2 text-sm leading-6 text-[#14213d]">
                        {realtimePartialTranscript || "No partial transcript yet."}
                      </p>
                    </div>
                    <div className="rounded-2xl border border-[#dce4ef] bg-white p-4">
                      <p className="text-xs font-bold uppercase tracking-[0.14em] text-[#60708a]">
                        Final transcripts
                      </p>
                      {realtimeFinalTranscripts.length ? (
                        <div className="mt-2 grid gap-2">
                          {realtimeFinalTranscripts.map((item, index) => (
                            <p
                              className="rounded-xl bg-[#f8fafc] px-3 py-2 text-sm leading-6 text-[#14213d]"
                              key={`${index}-${item}`}
                            >
                              {item}
                            </p>
                          ))}
                        </div>
                      ) : (
                        <p className="mt-2 text-sm leading-6 text-[#14213d]">
                          No final transcript yet.
                        </p>
                      )}
                    </div>
                    <div className="rounded-2xl border border-[#dce4ef] bg-white p-4">
                      <p className="text-xs font-bold uppercase tracking-[0.14em] text-[#60708a]">
                        AI teacher stream
                      </p>
                      <p className="mt-2 text-sm leading-6 text-[#14213d]">
                        {realtimeAiStreamingText || "No AI response stream yet."}
                      </p>
                    </div>
                  </div>

                  <div className="mt-4 rounded-2xl border border-[#dce4ef] bg-white p-4">
                    <p className="text-xs font-bold uppercase tracking-[0.14em] text-[#60708a]">
                      AI responses
                    </p>
                    {realtimeAiResponses.length ? (
                      <div className="mt-2 grid gap-2">
                        {realtimeAiResponses.map((response) => (
                          <div
                            className="rounded-xl bg-[#f8fafc] px-3 py-3"
                            key={response.responseId}
                          >
                            <div className="flex flex-wrap items-center justify-between gap-3">
                              <p className="text-xs font-bold uppercase tracking-[0.12em] text-[#60708a]">
                                {response.responseSource}
                              </p>
                              {response.wasInterrupted ? (
                                <span className="rounded-full border border-[#f5c2c7] bg-[#fff1f2] px-3 py-1 text-xs font-bold uppercase tracking-[0.12em] text-[#b42318]">
                                  Interrupted
                                </span>
                              ) : response.audioUrl ? (
                                <Button
                                  className="px-3 py-2 text-xs"
                                  onClick={() =>
                                    void playRealtimeAiResponse(
                                      response.responseId,
                                      response.audioUrl,
                                      "Unable to play the realtime teacher audio.",
                                    )
                                  }
                                  type="button"
                                  variant="secondary"
                                >
                                  {realtimePlayingResponseId === response.responseId
                                    ? "Playing..."
                                    : "Play Teacher Audio"}
                                </Button>
                              ) : null}
                            </div>
                            <p className="mt-2 text-sm leading-6 text-[#14213d]">
                              {response.responseText}
                            </p>
                            {response.audioUrl && !response.wasInterrupted ? (
                              <audio
                                className="mt-3 w-full"
                                controls
                                preload="none"
                                src={response.audioUrl}
                              />
                            ) : null}
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p className="mt-2 text-sm leading-6 text-[#14213d]">
                        No AI response yet.
                      </p>
                    )}
                  </div>

                  <div className="mt-5 flex flex-wrap gap-3">
                    <Button
                      disabled={!realtimeCanConnect}
                      onClick={() => void handleConnectRealtime()}
                      type="button"
                    >
                      Connect Realtime
                    </Button>
                    <Button
                      disabled={!realtimeCanStartSpeaking}
                      onClick={() => void handleStartRealtimeCapture()}
                      type="button"
                      variant="secondary"
                    >
                      Start Speaking
                    </Button>
                    <Button
                      disabled={!realtimeCanEndTurn}
                      onClick={handleEndRealtimeTurn}
                      type="button"
                      variant="secondary"
                    >
                      End Current Turn
                    </Button>
                    <Button
                      disabled={!realtimeCanInterrupt}
                      onClick={() => void handleInterruptAndSpeak()}
                      type="button"
                      variant="secondary"
                    >
                      Interrupt and Speak
                    </Button>
                    <Button
                      disabled={!realtimeCanDisconnect}
                      onClick={handleStopRealtimeTest}
                      type="button"
                      variant="secondary"
                    >
                      Disconnect Realtime
                    </Button>
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
                                AI Teacher Response
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
                          How do you want to send your next turn?
                        </h3>
                        <p className="mt-2 max-w-2xl text-sm leading-6 text-[#60708a]">
                          Choose one input mode at a time. Only the selected card
                          stays visible so you can focus on the next practice turn.
                        </p>
                      </div>
                      <span className="rounded-full bg-[#eef3ff] px-3 py-1 text-sm font-bold text-[#335cff]">
                        Practice only
                      </span>
                    </div>

                    <div className="mt-5 grid gap-3 md:grid-cols-3">
                      {inputModeOptions.map((option) => (
                        <button
                          className={`rounded-2xl border p-4 text-left transition ${
                            inputMode === option.value
                              ? "border-[#335cff] bg-[#eef3ff]"
                              : "border-[#dce4ef] bg-white hover:border-[#9cb2ff]"
                          }`}
                          key={option.value}
                          onClick={() => handleInputModeChange(option.value)}
                          type="button"
                        >
                          <p className="font-bold text-[#14213d]">{option.label}</p>
                          <p className="mt-2 text-sm leading-6 text-[#60708a]">
                            {option.description}
                          </p>
                        </button>
                      ))}
                    </div>

                    {inputMode === "transcript" ? (
                      <div className="mt-5 rounded-2xl border border-[#dce4ef] bg-white p-5">
                        <label className="field-label" htmlFor="voice-conversation-transcript">
                          Type Transcript
                        </label>
                        <p className="mt-2 text-sm leading-6 text-[#60708a]">
                          Type your answer or paste what you said. This does not require a microphone.
                        </p>
                        <textarea
                          className="text-area mt-4"
                          id="voice-conversation-transcript"
                          onChange={(event) => setTranscript(event.target.value)}
                          placeholder="Type what you want to say to the teacher."
                          value={transcript}
                        />
                        <div className="mt-5 flex flex-wrap gap-3">
                          <Button
                            disabled={!canSendTranscript}
                            onClick={handleSubmitTurn}
                            type="button"
                          >
                            {submittingTurn ? "Sending..." : "Send Turn"}
                          </Button>
                          <Button
                            onClick={() => setTranscript("")}
                            type="button"
                            variant="secondary"
                          >
                            Clear Draft
                          </Button>
                        </div>
                      </div>
                    ) : null}

                    {inputMode === "upload" ? (
                      <div className="mt-5 rounded-2xl border border-[#dce4ef] bg-white p-5">
                        <p className="text-sm font-bold uppercase tracking-[0.14em] text-[#60708a]">
                          Upload Audio
                        </p>
                        <p className="mt-2 text-sm leading-6 text-[#60708a]">
                          Upload an audio file. The backend will transcribe it before the AI teacher responds.
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
                            : "Choose an audio file to send your next practice turn."}
                        </p>
                        <div className="mt-5 flex flex-wrap gap-3">
                          <Button
                            disabled={!canSendUploadedAudio}
                            onClick={handleSubmitTurn}
                            type="button"
                          >
                            {submittingTurn ? "Sending..." : "Send Audio"}
                          </Button>
                          <Button
                            onClick={clearUploadDraft}
                            type="button"
                            variant="secondary"
                          >
                            Clear Selected File
                          </Button>
                        </div>
                      </div>
                    ) : null}

                    {inputMode === "record" ? (
                      <div className="mt-5 rounded-2xl border border-[#dce4ef] bg-white p-5">
                        <p className="text-sm font-bold uppercase tracking-[0.14em] text-[#60708a]">
                          Record Audio
                        </p>
                        <p className="mt-2 text-sm leading-6 text-[#60708a]">
                          Record your voice using your microphone. If microphone is unavailable, use Type Transcript or Upload Audio instead.
                        </p>
                        {recordingError ? (
                          <div className="mt-4 rounded-2xl border border-[#f5c2c7] bg-[#fff1f2] px-4 py-3 text-sm text-[#b42318]">
                            {recordingError}
                          </div>
                        ) : null}
                        <div className="mt-4 flex flex-wrap gap-3">
                          <Button
                            disabled={recorderState === "recording"}
                            onClick={startRecording}
                            type="button"
                            variant="secondary"
                          >
                            Start Recording
                          </Button>
                          <Button
                            disabled={recorderState !== "recording"}
                            onClick={stopRecording}
                            type="button"
                            variant="secondary"
                          >
                            Stop Recording
                          </Button>
                        </div>
                        <p className="mt-3 text-sm leading-6 text-[#60708a]">
                          {getRecorderStatusLabel(recorderState)}
                        </p>
                        {pendingAudio?.source === "recording" ? (
                          <>
                            <p className="mt-2 text-sm font-semibold text-[#14213d]">
                              Recorded file ready: {pendingAudio.filename}
                            </p>
                            <audio
                              className="mt-4 w-full"
                              controls
                              preload="none"
                              ref={recordingPreviewRef}
                            />
                          </>
                        ) : null}
                        <div className="mt-5 flex flex-wrap gap-3">
                          <Button
                            disabled={!canSendRecording}
                            onClick={handleSubmitTurn}
                            type="button"
                          >
                            {submittingTurn ? "Sending..." : "Send Recording"}
                          </Button>
                          <Button
                            onClick={clearRecordingDraft}
                            type="button"
                            variant="secondary"
                          >
                            Clear Recording
                          </Button>
                        </div>
                      </div>
                    ) : null}
                  </div>
                ) : (
                  <div className="note-box mt-6">
                    This session is read-only because it is already {selectedSession.status}.
                    Start a new session to continue practicing.
                  </div>
                )}
              </>
            ) : (
              <div className="mt-6 rounded-[1.8rem] border border-dashed border-[#c7d6ea] bg-[linear-gradient(135deg,#fbfdff_0%,#f2f7ff_100%)] p-8 text-center">
                <p className="text-sm font-bold uppercase tracking-[0.16em] text-[#335cff]">
                  Practice Workspace
                </p>
                <h3 className="mt-3 text-2xl font-black text-[#14213d]">
                  No practice session selected.
                </h3>
                <p className="mx-auto mt-3 max-w-xl text-sm leading-7 text-[#60708a]">
                  Start a new practice session to begin.
                </p>
                <div className="mt-6 flex justify-center">
                  <Button onClick={openSessionModal} type="button">
                    New Practice Session
                  </Button>
                </div>
              </div>
            )}
          </Card>
        </div>
      </section>

      {isSessionModalOpen ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-[rgba(20,33,61,0.55)] px-4 py-8">
          <div
            aria-hidden="true"
            className="absolute inset-0"
            onClick={closeSessionModal}
          />
          <Card className="relative z-10 max-h-[calc(100vh-4rem)] w-full max-w-4xl overflow-y-auto rounded-[2rem] border-[#cddaf0] bg-[linear-gradient(180deg,#ffffff_0%,#f8fbff_100%)] p-0 shadow-[0_30px_80px_rgba(20,33,61,0.22)]">
            <div className="border-b border-[#e2eaf5] px-6 py-5 md:px-8">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className="text-sm font-bold uppercase tracking-[0.16em] text-[#335cff]">
                    Practice Session
                  </p>
                  <h2 className="mt-2 text-3xl font-black text-[#14213d]">
                    New voice conversation practice
                  </h2>
                  <p className="mt-3 max-w-2xl text-sm leading-7 text-[#60708a]">
                    Choose a title, optional CEFR tag, and a focus skill. The new
                    practice session will open directly in the conversation workspace.
                  </p>
                </div>
                <Button onClick={closeSessionModal} type="button" variant="secondary">
                  Cancel
                </Button>
              </div>
            </div>

            <div className="px-6 py-6 md:px-8 md:py-7">
              {sessionModalError ? <div className="error-box mt-0">{sessionModalError}</div> : null}

              <div className="mt-2 grid gap-4 md:grid-cols-[1.2fr_0.8fr]">
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

              <div className="mt-6">
                <p className="text-sm font-bold uppercase tracking-[0.14em] text-[#60708a]">
                  Focus skill
                </p>
                <div className="mt-3 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
                  {targetSkillOptions.map((option) => (
                    <button
                      className={`rounded-2xl border p-4 text-left transition ${
                        targetSkill === option.value
                          ? "border-[#335cff] bg-[#eef3ff]"
                          : "border-[#dce4ef] bg-white hover:border-[#9cb2ff]"
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
              </div>

              <div className="mt-6 rounded-[1.5rem] border border-[#dce4ef] bg-white p-4">
                <p className="text-xs font-bold uppercase tracking-[0.14em] text-[#60708a]">
                  Current focus
                </p>
                <p className="mt-2 text-lg font-black text-[#14213d]">{activeSkill?.label}</p>
                <p className="mt-1 text-sm leading-6 text-[#60708a]">
                  This remains practice-only and does not update official mastery.
                </p>
              </div>

              <div className="mt-6 flex flex-wrap justify-end gap-3">
                <Button onClick={closeSessionModal} type="button" variant="secondary">
                  Cancel
                </Button>
                <Button
                  disabled={startingSession}
                  onClick={handleStartSession}
                  type="button"
                >
                  {startingSession ? "Starting..." : "Start Voice Session"}
                </Button>
              </div>
            </div>
          </Card>
        </div>
      ) : null}
    </main>
  );
}
