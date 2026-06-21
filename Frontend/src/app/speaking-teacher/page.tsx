"use client";

import { useEffect, useRef, useState } from "react";

import Button from "@/components/Button";
import Card from "@/components/Card";
import {
  answerSpeakingTeacherSession,
  getDashboard,
  getSpeakingTeacherSession,
  startSpeakingTeacherSession,
  type SpeakingTeacherSession,
} from "@/lib/api";

type RecorderState = "idle" | "recording" | "recorded";
type OfficialSpeakingMastery = {
  assessed: boolean;
  score: string;
  level: string;
  status: string;
};

const DEFAULT_OFFICIAL_MASTERY: OfficialSpeakingMastery = {
  assessed: false,
  score: "Not yet assessed",
  level: "A1",
  status: "Complete the Speaking Diagnostic for an official score.",
};

export default function SpeakingTeacherPage() {
  const [officialMastery, setOfficialMastery] = useState<OfficialSpeakingMastery>(
    DEFAULT_OFFICIAL_MASTERY,
  );
  const [session, setSession] = useState<SpeakingTeacherSession | null>(null);
  const [transcript, setTranscript] = useState("");
  const [audioBlob, setAudioBlob] = useState<Blob | null>(null);
  const [recorderState, setRecorderState] = useState<RecorderState>("idle");
  const [error, setError] = useState("");
  const [loadingMastery, setLoadingMastery] = useState(true);
  const [startingSession, setStartingSession] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<BlobPart[]>([]);

  useEffect(() => {
    let active = true;
    getDashboard()
      .then((dashboard) => {
        if (!active) {
          return;
        }
        const speakingMastery = dashboard.skill_mastery.find(
          (mastery) => mastery.skill.name === "Speaking",
        );
        if (!speakingMastery) {
          setOfficialMastery(DEFAULT_OFFICIAL_MASTERY);
          return;
        }
        setOfficialMastery({
          assessed: true,
          score: `${Number(speakingMastery.score)}%`,
          level: speakingMastery.level_code,
          status: speakingMastery.status,
        });
      })
      .catch((requestError: Error) => {
        if (active) {
          setError(requestError.message);
        }
      })
      .finally(() => {
        if (active) {
          setLoadingMastery(false);
        }
      });

    return () => {
      active = false;
      streamRef.current?.getTracks().forEach((track) => track.stop());
    };
  }, []);

  async function handleStartSession() {
    setError("");
    setStartingSession(true);
    try {
      const startedSession = await startSpeakingTeacherSession();
      setSession(startedSession);
      setTranscript("");
      setAudioBlob(null);
      setRecorderState("idle");
      setOfficialMastery({
        assessed: startedSession.official_mastery_assessed,
        score: startedSession.official_mastery_assessed
          ? `${startedSession.official_mastery_score}%`
          : "Not yet assessed",
        level: startedSession.official_mastery_level,
        status: startedSession.official_mastery_assessed
          ? "Official diagnostic-backed speaking mastery"
          : "Using an A1 fallback until you complete the Speaking Diagnostic.",
      });
    } catch (requestError) {
      setError((requestError as Error).message);
    } finally {
      setStartingSession(false);
    }
  }

  async function startRecording() {
    if (!navigator.mediaDevices || typeof MediaRecorder === "undefined") {
      setError("Voice recording is not supported in this browser. Use the transcript fallback below.");
      return;
    }

    setError("");
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

  async function handleSubmitAnswer() {
    if (!session) {
      return;
    }

    const trimmedTranscript = transcript.trim();
    if (!trimmedTranscript && !audioBlob) {
      setError("Add a transcript or record audio before submitting.");
      return;
    }

    setError("");
    setSubmitting(true);
    try {
      const payload =
        trimmedTranscript.length > 0
          ? { transcript: trimmedTranscript }
          : (() => {
              const formData = new FormData();
              if (audioBlob) {
                formData.append("audio_file", audioBlob, "speaking-teacher.webm");
              }
              return formData;
            })();
      await answerSpeakingTeacherSession(session.session_id, payload);
      const refreshedSession = await getSpeakingTeacherSession(session.session_id);
      setSession(refreshedSession);
      setTranscript("");
      setAudioBlob(null);
      setRecorderState("idle");
    } catch (requestError) {
      setError((requestError as Error).message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="page-shell">
      <p className="eyebrow">Practice speaking</p>
      <h1 className="page-title">Speaking Teacher Session</h1>
      <p className="page-copy">
        Complete a three-turn speaking practice session with voice recording or
        transcript fallback. This is practice only and does not change your
        official mastery.
      </p>

      {error ? <div className="error-box">{error}</div> : null}

      <div className="mt-8 grid gap-5 lg:grid-cols-[320px_1fr]">
        <Card>
          <p className="text-sm font-bold uppercase tracking-wider text-[#335cff]">
            Official Mastery
          </p>
          <p className="mt-4 text-4xl font-black text-[#14213d]">
            {loadingMastery ? "Loading..." : officialMastery.score}
          </p>
          <p className="mt-2 text-sm font-semibold text-[#60708a]">
            Level: {officialMastery.level}
          </p>
          <p className="mt-4 text-sm leading-6 text-[#60708a]">
            {officialMastery.status}
          </p>
          <p className="mt-4 rounded-2xl bg-[#f8fafc] px-4 py-3 text-sm leading-6 text-[#42536b]">
            Practice sessions do not update `SkillMastery`. Only diagnostics
            change official speaking mastery.
          </p>
        </Card>

        <Card>
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <p className="text-sm font-bold uppercase tracking-wider text-[#335cff]">
                Speaking Teacher Session
              </p>
              <h2 className="mt-2 text-2xl font-black text-[#14213d]">
                Guided speaking practice
              </h2>
              <p className="mt-3 max-w-2xl leading-7 text-[#60708a]">
                Start a new session to receive three speaking prompts matched to
                your official speaking level.
              </p>
            </div>
            <Button disabled={startingSession} onClick={handleStartSession} type="button">
              {startingSession ? "Starting..." : "Start Speaking Session"}
            </Button>
          </div>
        </Card>
      </div>

      {session ? (
        <div className="mt-8 grid gap-5">
          <Card>
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="text-sm font-bold uppercase tracking-wider text-[#335cff]">
                  Current session
                </p>
                <h2 className="mt-2 text-2xl font-black text-[#14213d]">
                  {session.skill} practice at {session.official_mastery_level}
                </h2>
              </div>
              <span className="rounded-full bg-[#e9eeff] px-3 py-1 text-sm font-bold text-[#335cff]">
                Turn {session.current_turn} of {session.total_turns}
              </span>
            </div>
            <p className="mt-4 leading-7 text-[#60708a]">{session.lesson}</p>
          </Card>

          {session.status !== "completed" && session.current_task ? (
            <Card>
              <p className="text-sm font-bold uppercase tracking-wider text-[#335cff]">
                Next Speaking Task
              </p>
              <h3 className="mt-3 text-xl font-bold text-[#14213d]">
                {session.current_task.teacher_prompt}
              </h3>
              <p className="mt-3 text-sm leading-6 text-[#60708a]">
                Target focus: {session.current_task.target_focus}
              </p>

              <div className="mt-6 flex flex-wrap gap-3">
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

              <p className="mt-4 rounded-2xl bg-[#f8fafc] px-4 py-3 text-sm leading-6 text-[#42536b]">
                Recording status:{" "}
                {recorderState === "recording"
                  ? "Recording"
                  : recorderState === "recorded"
                    ? "Recording ready to submit"
                    : "Use recording or transcript fallback"}
              </p>

              <label className="field-label mt-6" htmlFor="speaking-transcript">
                Transcript fallback
              </label>
              <textarea
                className="text-area"
                id="speaking-transcript"
                onChange={(event) => setTranscript(event.target.value)}
                placeholder="Type your speaking answer here if you are not using audio."
                value={transcript}
              />

              <Button
                className="mt-5"
                disabled={submitting}
                onClick={handleSubmitAnswer}
                type="button"
              >
                {submitting ? "Submitting..." : "Submit Answer"}
              </Button>
            </Card>
          ) : null}

          {session.turns.length ? (
            <section className="grid gap-4">
              {session.turns.map((turn) => (
                <Card key={turn.turn_number}>
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <p className="text-sm font-bold uppercase tracking-wider text-[#335cff]">
                        Turn {turn.turn_number}
                      </p>
                      <h3 className="mt-2 text-lg font-bold text-[#14213d]">
                        {turn.teacher_task}
                      </h3>
                    </div>
                    <span className="rounded-full bg-[#14213d] px-3 py-1 text-sm font-bold text-white">
                      Practice Score: {turn.score ?? "Not scored"}%
                    </span>
                  </div>
                  <p className="mt-4 text-sm font-bold text-[#60708a]">Transcript</p>
                  <p className="mt-2 leading-7 text-[#14213d]">{turn.transcript}</p>
                  <p className="mt-4 text-sm font-bold text-[#60708a]">Feedback</p>
                  <p className="mt-2 leading-7 text-[#14213d]">{turn.feedback}</p>
                  <p className="mt-4 text-sm font-bold text-[#60708a]">Correction</p>
                  <p className="mt-2 leading-7 text-[#14213d]">{turn.correction}</p>
                  <p className="mt-4 text-sm font-bold text-[#60708a]">Explanation</p>
                  <p className="mt-2 leading-7 text-[#14213d]">{turn.explanation}</p>
                  <p className="mt-4 text-sm font-bold text-[#60708a]">Encouragement</p>
                  <p className="mt-2 leading-7 text-[#14213d]">{turn.encouragement}</p>
                </Card>
              ))}
            </section>
          ) : null}

          {session.final_result ? (
            <div className="grid gap-5 lg:grid-cols-[1.1fr_1fr]">
              <Card className="bg-[#f4f7ff]">
                <p className="text-sm font-bold uppercase tracking-wider text-[#335cff]">
                  Final Practice Result
                </p>
                <div className="mt-4 inline-flex rounded-2xl bg-[#335cff] px-5 py-4 text-white shadow-[0_12px_24px_rgba(51,92,255,0.22)]">
                  <div>
                    <p className="text-sm font-bold uppercase tracking-wider">
                      {session.final_result.label}
                    </p>
                    <p className="mt-2 text-6xl font-black">
                      {session.final_result.practice_score}%
                    </p>
                  </div>
                </div>
                <p className="mt-6 leading-7 text-[#14213d]">
                  {session.final_result.feedback_summary}
                </p>
                <p className="mt-4 rounded-2xl bg-white/70 px-4 py-3 text-sm leading-6 text-[#42536b]">
                  Practice sessions stay in practice history only. Your
                  dashboard mastery cards still show official diagnostic scores.
                </p>
              </Card>

              <div className="grid gap-5">
                <Card>
                  <h3 className="text-lg font-bold">Strengths</h3>
                  <ul className="mt-3 list-disc space-y-2 pl-5 text-[#42536b]">
                    {session.final_result.strengths.map((strength) => (
                      <li key={strength}>{strength}</li>
                    ))}
                  </ul>
                  <h3 className="mt-6 text-lg font-bold">Improvement areas</h3>
                  <ul className="mt-3 list-disc space-y-2 pl-5 text-[#42536b]">
                    {session.final_result.improvement_areas.map((area) => (
                      <li key={area}>{area}</li>
                    ))}
                  </ul>
                </Card>
                <Card>
                  <p className="text-sm font-bold uppercase tracking-wider text-[#335cff]">
                    Next speaking recommendation
                  </p>
                  <p className="mt-3 leading-7 text-[#42536b]">
                    {session.final_result.next_suggestion}
                  </p>
                </Card>
              </div>
            </div>
          ) : null}
        </div>
      ) : null}
    </main>
  );
}
