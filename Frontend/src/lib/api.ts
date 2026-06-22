const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

export const ADMIN_LOGIN_URL = `${API_BASE_URL}/admin/login/`;
export const AUTH_NOTE =
  "Please log in to continue.";

export type AuthUser = {
  id: number;
  username: string;
  email: string;
};

export type ModuleSummary = {
  id: number;
  title: string;
  level: string;
  skill: string;
};

export type DashboardData = {
  profile: {
    current_level: string;
    target_level: string;
    learning_goal: string;
  };
  skill_mastery: Array<{
    id: number;
    skill: { id: number; name: string };
    level_code: string;
    score: string;
    status: string;
    last_updated: string;
  }>;
  recommended_module: ModuleSummary | null;
  latest_study_plan: {
    plan_data: {
      focus?: string[];
      days?: string[];
      items?: StudyPlanItem[];
    };
    focus_skills: string[];
    start_date: string;
    end_date: string;
  } | null;
  recent_sessions: Array<{
    id: number;
    module: {
      id: number;
      title: string;
      level: { level_code: string };
      skill: { name: string };
    } | null;
    session_type: string;
    score: string | null;
    started_at: string;
    completed_at: string | null;
  }>;
};

export type DiagnosticMistake = {
  type: string;
  original: string;
  correction: string;
  explanation: string;
};

export type DiagnosticAnswerFeedback = {
  question: string;
  answer: string;
  feedback: string;
  corrected_answer: string;
  mistakes: DiagnosticMistake[];
};

export type DiagnosticResult = {
  assessment_mode: string;
  assessed_skills: string[];
  unassessed_skills: string[];
  skill_scores: Record<string, number>;
  skill_status: Record<string, string>;
  overall_level: string;
  weak_skills: string[];
  recommendation: string;
  level_explanation: string;
  answer_feedback: DiagnosticAnswerFeedback[];
  next_step: string;
};

export type RecommendationData = {
  recommended_module: ModuleSummary | null;
  reason: string;
  diagnostic_scores: {
    Grammar: number | null;
    Vocabulary: number | null;
    Listening: number | null;
    Speaking: number | null;
    Pronunciation: number | null;
  };
  current_skill_scores: {
    Grammar: number | null;
    Vocabulary: number | null;
    Listening: number | null;
    Speaking: number | null;
    Pronunciation: number | null;
  };
  weakest_skill: string | null;
  recommended_focus: string | null;
  recommended_focus_reason: string;
  recommended_action: {
    type: "teacher_session" | "module";
    skill: string | null;
    label: string;
    href: string;
  } | null;
  learner_level: string;
  module_level: string | null;
  fallback_used: boolean;
  fallback_reason: string | null;
};

export type TeacherSession = {
  session_id: number;
  lesson: string;
  practice_question: string;
};

export type TeacherFeedback = {
  session_score: number;
  feedback: string;
  correction?: string;
  explanation?: string;
  encouragement?: string;
  completed?: boolean;
  next_task?: {
    turn_number: number;
    teacher_task: string;
  } | null;
  final_result?: GuidedTeacherFinalResult | null;
};

export type GuidedTeacherTurn = {
  turn_number: number;
  teacher_task: string;
  student_answer: string;
  score: number | null;
  feedback: string;
  correction: string;
  explanation: string;
  encouragement: string;
};

export type GuidedTeacherFinalResult = {
  session_score: number | null;
  strengths: string[];
  improvement_areas: string[];
  next_study_suggestion: string;
  feedback_summary: string;
};

export type GuidedTeacherSession = {
  session_id: number;
  study_session_id: number;
  module: ModuleSummary | null;
  lesson: string;
  lesson_objective: string;
  status: string;
  current_turn: number;
  total_turns: number;
  current_task: {
    turn_number: number;
    teacher_task: string;
  } | null;
  turns: GuidedTeacherTurn[];
  final_result: GuidedTeacherFinalResult | null;
};

export type GuidedTeacherAnswerResponse = {
  session_id: number;
  turn: GuidedTeacherTurn;
  completed: boolean;
  next_task: {
    turn_number: number;
    teacher_task: string;
  } | null;
  final_result: GuidedTeacherFinalResult | null;
};

export type SpeakingTeacherCurrentTask = {
  turn_number: number;
  task_type: string;
  teacher_prompt: string;
  target_focus: string;
};

export type SpeakingTeacherNextTask = {
  turn_number: number;
  teacher_task: string;
  target_focus: string;
};

export type SpeakingTeacherTurn = {
  turn_number: number;
  task_type: string;
  target_focus: string;
  teacher_task: string;
  transcript: string;
  score: number | null;
  feedback: string;
  correction: string;
  explanation: string;
  encouragement: string;
  evaluation_breakdown: Record<string, number>;
};

export type SpeakingTeacherFinalResult = {
  practice_score: number | null;
  label: string;
  strengths: string[];
  improvement_areas: string[];
  next_suggestion: string;
  feedback_summary: string;
};

export type SpeakingTeacherSession = {
  session_id: number;
  study_session_id: number;
  session_mode: "speaking";
  skill: string;
  official_mastery_assessed: boolean;
  official_mastery_score: number;
  official_mastery_level: string;
  status: string;
  current_turn: number;
  total_turns: number;
  lesson: string;
  turns: SpeakingTeacherTurn[];
  current_task: SpeakingTeacherCurrentTask | null;
  final_result: SpeakingTeacherFinalResult | null;
};

export type SpeakingTeacherAnswerResponse = {
  session_id: number;
  turn: SpeakingTeacherTurn;
  completed: boolean;
  next_task: SpeakingTeacherNextTask | null;
  final_result: SpeakingTeacherFinalResult | null;
};

export type PronunciationSubstitution = {
  expected: string;
  heard: string;
};

export type PronunciationTeacherCurrentTask = {
  turn_number: number;
  task_type: string;
  teacher_prompt: string;
  target_text: string;
  target_focus: string;
};

export type PronunciationTeacherNextTask = {
  turn_number: number;
  teacher_task: string;
  target_text: string;
  target_focus: string;
};

export type PronunciationTeacherTurn = {
  turn_number: number;
  task_type: string;
  teacher_task: string;
  target_text: string;
  target_focus: string;
  transcript: string;
  score: number | null;
  feedback: string;
  correction: string;
  explanation: string;
  encouragement: string;
  word_accuracy: number;
  missing_words: string[];
  extra_words: string[];
  substituted_words: PronunciationSubstitution[];
  evaluation_breakdown: Record<string, number>;
};

export type PronunciationTeacherFinalResult = {
  practice_score: number | null;
  label: string;
  strengths: string[];
  improvement_areas: string[];
  next_suggestion: string;
  feedback_summary: string;
};

export type PronunciationTeacherSession = {
  session_id: number;
  study_session_id: number;
  session_mode: "pronunciation";
  skill: string;
  official_mastery_assessed: boolean;
  official_mastery_score: number;
  official_mastery_level: string;
  status: string;
  current_turn: number;
  total_turns: number;
  lesson: string;
  turns: PronunciationTeacherTurn[];
  current_task: PronunciationTeacherCurrentTask | null;
  final_result: PronunciationTeacherFinalResult | null;
};

export type PronunciationTeacherAnswerResponse = {
  session_id: number;
  turn: PronunciationTeacherTurn;
  completed: boolean;
  next_task: PronunciationTeacherNextTask | null;
  final_result: PronunciationTeacherFinalResult | null;
};

export type ListeningTeacherCurrentTask = {
  turn_number: number;
  task_type: string;
  teacher_prompt: string;
  passage_text: string;
  audio_url: string | null;
  question_text: string;
  target_focus: string;
};

export type ListeningTeacherNextTask = {
  turn_number: number;
  teacher_task: string;
  passage_text: string;
  audio_url: string | null;
  question_text: string;
  target_focus: string;
};

export type ListeningTeacherTurn = {
  turn_number: number;
  task_type: string;
  teacher_task: string;
  passage_text: string;
  question_text: string;
  expected_answer: string;
  student_answer: string;
  score: number | null;
  feedback: string;
  correction: string;
  explanation: string;
  encouragement: string;
  answer_match: string;
  matched_keywords: string[];
  missing_keywords: string[];
  evaluation_breakdown: Record<string, string | number | string[]>;
};

export type ListeningTeacherFinalResult = {
  practice_score: number | null;
  label: string;
  strengths: string[];
  improvement_areas: string[];
  next_suggestion: string;
  feedback_summary: string;
};

export type ListeningTeacherSession = {
  session_id: number;
  study_session_id: number;
  session_mode: "listening";
  skill: string;
  official_mastery_assessed: boolean;
  official_mastery_score: number;
  official_mastery_level: string;
  status: string;
  current_turn: number;
  total_turns: number;
  lesson: string;
  turns: ListeningTeacherTurn[];
  current_task: ListeningTeacherCurrentTask | null;
  final_result: ListeningTeacherFinalResult | null;
};

export type ListeningTeacherAnswerResponse = {
  session_id: number;
  turn: ListeningTeacherTurn;
  completed: boolean;
  next_task: ListeningTeacherNextTask | null;
  final_result: ListeningTeacherFinalResult | null;
};

export type StudyPlanData = {
  plan: {
    focus: string[];
    days: string[];
    items: StudyPlanItem[];
  };
};

export type StudyPlanItem = {
  day: string;
  title: string;
  skill: string;
  level: string | null;
  learner_level: string;
  module_level: string | null;
  module_id: number | null;
  module_title: string | null;
  fallback_used: boolean;
  fallback_reason: string | null;
  href: string;
};

export type CoachSummary = {
  summary: string;
  next_step: string;
};

export type VoiceDiagnosticPrompts = {
  level_code: string;
  pronunciation: {
    target_sentence: string;
    items: Array<{
      item_number: number;
      target_sentence: string;
    }>;
  };
  listening: {
    passage: string;
    question: string;
    expected_answer: string;
    items: Array<{
      item_number: number;
      passage: string;
      question: string;
      expected_answer: string;
    }>;
  };
  speaking: {
    question: string;
    items: Array<{
      item_number: number;
      question: string;
    }>;
  };
};

export type PronunciationResult = {
  target_sentence: string;
  transcript: string;
  score: number;
  status: string;
  feedback: string;
  explanation: string;
  word_accuracy: number;
  missing_words: string[];
  extra_words: string[];
  breakdown: {
    rubric: string;
    word_accuracy: number;
    target_completion: number;
    sequence_accuracy: number;
    substitution_control: number;
    missing_word_control: number;
    extra_word_control: number;
    clarity_estimate: number;
    missing_words: string[];
    extra_words: string[];
    substituted_words: Array<{
      expected: string;
      heard: string;
    }>;
    score_reasons: string[];
  };
  substituted_words?: Array<{
    expected: string;
    heard: string;
  }>;
};

export type ListeningResult = {
  score: number;
  status: string;
  feedback: string;
  explanation: string;
  question: string;
  expected_answer: string;
  user_answer: string;
  answer?: string;
  matched_keywords?: string[];
  missing_keywords?: string[];
  answer_match?: string;
  breakdown: {
    rubric: string;
    correct_detail: number;
    question_relevance: number;
    completeness: number;
    semantic_match: number;
    clarity: number;
    matched_keywords: string[];
    missing_keywords: string[];
    answer_match: string;
    score_reasons: string[];
  };
};

export type SpeakingResult = {
  question: string;
  transcript: string;
  score: number;
  status: string;
  feedback: string;
  explanation: string;
  strengths: string[];
  improvement_areas: string[];
  breakdown: {
    rubric: string;
    task_relevance: number;
    completeness: number;
    clarity: number;
    grammar_control: number;
    vocabulary_range: number;
    coherence: number;
    fluency_signal: number;
    word_count: number;
    sentence_count: number;
    filler_count: number;
    strengths: string[];
    improvement_areas: string[];
    score_reasons: string[];
  };
};

export type VoiceDiagnosticSessionState = {
  session_id: number;
  session_status: string;
  recommended_focus: string;
  summary: string;
  started_at: string;
  completed_at: string | null;
};

export type VoiceDiagnosticAggregation = {
  base_average: number;
  score_range: number;
  consistency_adjustment: number;
  final_score: number;
};

export type PronunciationBatchResult = {
  items: Array<PronunciationResult & { item_number: number }>;
  final_score: number;
  status: string;
  level_code: string;
  feedback_summary: string;
  aggregation: VoiceDiagnosticAggregation;
} & VoiceDiagnosticSessionState;

export type ListeningBatchResult = {
  items: Array<
    ListeningResult & {
      item_number: number;
      passage: string;
    }
  >;
  final_score: number;
  status: string;
  level_code: string;
  feedback_summary: string;
  aggregation: VoiceDiagnosticAggregation;
} & VoiceDiagnosticSessionState;

export type SpeakingBatchResult = {
  items: Array<SpeakingResult & { item_number: number }>;
  final_score: number;
  status: string;
  level_code: string;
  feedback_summary: string;
  aggregation: VoiceDiagnosticAggregation;
} & VoiceDiagnosticSessionState;

export type VoiceDiagnosticSessionStart = {
  session_id: number;
  status: string;
  started_at: string;
};

export type VoiceDiagnosticHistoryItem = {
  id: number;
  skill: string;
  item_number: number;
  task_type: string;
  prompt_text: string;
  target_text: string;
  passage_text: string;
  question_text: string;
  expected_answer: string;
  user_answer: string;
  transcript: string;
  score: number | null;
  feedback: string;
  details: Record<string, unknown>;
  created_at: string;
};

export type VoiceDiagnosticHistorySession = {
  id: number;
  status: string;
  pronunciation_score: number | null;
  listening_score: number | null;
  speaking_score: number | null;
  recommended_focus: string;
  summary: string;
  started_at: string;
  completed_at: string | null;
};

export type VoiceDiagnosticHistoryDetail = VoiceDiagnosticHistorySession & {
  items: VoiceDiagnosticHistoryItem[];
};

export type VoiceDiagnosticReport = {
  session_id: number;
  status: string;
  official_mastery_updated: boolean;
  message?: string;
  scores?: {
    Pronunciation: number | null;
    Listening: number | null;
    Speaking: number | null;
  };
  skill_breakdown?: Array<{
    skill: string;
    final_score: number | null;
    item_scores: number[];
    item_count: number;
  }>;
  recommended_focus?: string | null;
  recommended_focus_reason?: string;
  next_teacher_session?: {
    skill: string;
    label: string;
    href: string;
  } | null;
  recommendation_href?: string;
  study_plan_href?: string;
  history_href?: string;
  dashboard_href?: string;
  summary?: string;
};

type ApiEnvelope<T> = {
  success: boolean;
  data: T;
  message: string;
};

function readCsrfCookie() {
  if (typeof document === "undefined") {
    return "";
  }

  return (
    document.cookie
      .split("; ")
      .find((cookie) => cookie.startsWith("csrftoken="))
      ?.split("=")[1] ?? ""
  );
}

function getErrorMessage(error: unknown): string {
  if (typeof error === "string") {
    return error;
  }
  if (Array.isArray(error)) {
    return error.map(getErrorMessage).join(" ");
  }
  if (error && typeof error === "object") {
    return Object.values(error).map(getErrorMessage).join(" ");
  }
  return "Request failed.";
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const method = init?.method?.toUpperCase() ?? "GET";
  if (method !== "GET" && !readCsrfCookie()) {
    await getCsrfToken();
  }
  const csrfToken = readCsrfCookie();
  const isFormData =
    typeof FormData !== "undefined" && init?.body instanceof FormData;
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    credentials: "include",
    headers: {
      Accept: "application/json",
      ...(init?.body && !isFormData ? { "Content-Type": "application/json" } : {}),
      ...(method !== "GET" && csrfToken ? { "X-CSRFToken": csrfToken } : {}),
      ...init?.headers,
    },
  });

  let payload: ApiEnvelope<T> | { error?: unknown } | null = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }

  if (!response.ok) {
    if (response.status === 401 || response.status === 403) {
      throw new Error(AUTH_NOTE);
    }

    const apiError =
      payload && "error" in payload
        ? getErrorMessage(payload.error)
        : null;
    throw new Error(apiError || `Request failed with status ${response.status}.`);
  }

  if (!payload || !("data" in payload)) {
    throw new Error("The backend returned an unexpected response.");
  }

  return payload.data;
}

async function requestBlob(path: string, init?: RequestInit): Promise<Blob> {
  const method = init?.method?.toUpperCase() ?? "GET";
  if (method !== "GET" && !readCsrfCookie()) {
    await getCsrfToken();
  }
  const csrfToken = readCsrfCookie();
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    credentials: "include",
    headers: {
      Accept: "audio/mpeg,application/json",
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      ...(method !== "GET" && csrfToken ? { "X-CSRFToken": csrfToken } : {}),
      ...init?.headers,
    },
  });

  if (!response.ok) {
    let payload: { error?: unknown } | null = null;
    try {
      payload = await response.json();
    } catch {
      payload = null;
    }
    if (response.status === 401 || response.status === 403) {
      throw new Error(AUTH_NOTE);
    }
    throw new Error(
      payload?.error ? getErrorMessage(payload.error) : `Request failed with status ${response.status}.`,
    );
  }

  return response.blob();
}

function notifyAuthChange() {
  if (typeof window !== "undefined") {
    window.dispatchEvent(new Event("xiav-auth-change"));
  }
}

export async function getCsrfToken() {
  const data = await request<{ csrf_token: string }>("/api/auth/csrf/");
  return data.csrf_token;
}

export async function loginUser(username: string, password: string) {
  const user = await request<AuthUser>("/api/auth/login/", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
  notifyAuthChange();
  return user;
}

export async function registerUser(
  username: string,
  email: string,
  password: string,
) {
  const user = await request<AuthUser>("/api/auth/register/", {
    method: "POST",
    body: JSON.stringify({ username, email, password }),
  });
  notifyAuthChange();
  return user;
}

export async function logoutUser() {
  await request<Record<string, never>>("/api/auth/logout/", {
    method: "POST",
    body: JSON.stringify({}),
  });
  notifyAuthChange();
}

export function getCurrentUser() {
  return request<AuthUser>("/api/auth/me/");
}

export function getDashboard() {
  return request<DashboardData>("/api/dashboard/");
}

export function submitDiagnostic(
  answers: Array<{ question: string; answer: string }>,
) {
  return request<DiagnosticResult>("/api/diagnostic/evaluate/", {
    method: "POST",
    body: JSON.stringify({ answers }),
  });
}

export function getRecommendation() {
  return request<RecommendationData>("/api/curriculum/recommendation/");
}

export function startTeacherSession(moduleId: number) {
  return request<TeacherSession>("/api/teacher/session/", {
    method: "POST",
    body: JSON.stringify({ module_id: moduleId }),
  });
}

export function submitTeacherFeedback(sessionId: number, answer: string) {
  return request<TeacherFeedback>("/api/teacher/feedback/", {
    method: "POST",
    body: JSON.stringify({ session_id: sessionId, answer }),
  });
}

export function startGuidedTeacherSession(moduleId?: number) {
  return request<GuidedTeacherSession>("/api/teacher/session/start/", {
    method: "POST",
    body: JSON.stringify(moduleId ? { module_id: moduleId } : {}),
  });
}

export function submitGuidedTeacherAnswer(
  sessionId: number,
  studentAnswer: string,
) {
  return request<GuidedTeacherAnswerResponse>("/api/teacher/session/answer/", {
    method: "POST",
    body: JSON.stringify({ session_id: sessionId, student_answer: studentAnswer }),
  });
}

export function getGuidedTeacherSession(sessionId: number) {
  return request<GuidedTeacherSession>(`/api/teacher/session/${sessionId}/`);
}

export function startSpeakingTeacherSession() {
  return request<SpeakingTeacherSession>("/api/teacher/speaking/sessions/start/", {
    method: "POST",
    body: JSON.stringify({}),
  });
}

export function getSpeakingTeacherSession(sessionId: number) {
  return request<SpeakingTeacherSession>(`/api/teacher/speaking/sessions/${sessionId}/`);
}

export function answerSpeakingTeacherSession(
  sessionId: number,
  payload: FormData | { transcript: string },
) {
  const body =
    typeof FormData !== "undefined" && payload instanceof FormData
      ? payload
      : JSON.stringify(payload);
  return request<SpeakingTeacherAnswerResponse>(
    `/api/teacher/speaking/sessions/${sessionId}/answer/`,
    {
      method: "POST",
      body,
    },
  );
}

export function startListeningTeacherSession() {
  return request<ListeningTeacherSession>(
    "/api/teacher/listening/sessions/start/",
    {
      method: "POST",
      body: JSON.stringify({}),
    },
  );
}

export function getListeningTeacherSession(sessionId: number) {
  return request<ListeningTeacherSession>(
    `/api/teacher/listening/sessions/${sessionId}/`,
  );
}

export function answerListeningTeacherSession(
  sessionId: number,
  payload: FormData | { answer: string },
) {
  const body =
    typeof FormData !== "undefined" && payload instanceof FormData
      ? payload
      : JSON.stringify(payload);
  return request<ListeningTeacherAnswerResponse>(
    `/api/teacher/listening/sessions/${sessionId}/answer/`,
    {
      method: "POST",
      body,
    },
  );
}

export function startPronunciationTeacherSession() {
  return request<PronunciationTeacherSession>(
    "/api/teacher/pronunciation/sessions/start/",
    {
      method: "POST",
      body: JSON.stringify({}),
    },
  );
}

export function getPronunciationTeacherSession(sessionId: number) {
  return request<PronunciationTeacherSession>(
    `/api/teacher/pronunciation/sessions/${sessionId}/`,
  );
}

export function answerPronunciationTeacherSession(
  sessionId: number,
  payload: FormData | { transcript: string },
) {
  const body =
    typeof FormData !== "undefined" && payload instanceof FormData
      ? payload
      : JSON.stringify(payload);
  return request<PronunciationTeacherAnswerResponse>(
    `/api/teacher/pronunciation/sessions/${sessionId}/answer/`,
    {
      method: "POST",
      body,
    },
  );
}

export function generateStudyPlan() {
  return request<StudyPlanData>("/api/scheduler/generate-plan/", {
    method: "POST",
    body: JSON.stringify({}),
  });
}

export function getCoachSummary() {
  return request<CoachSummary>("/api/coach/summary/");
}

export function getVoiceDiagnosticPrompts() {
  return request<VoiceDiagnosticPrompts>("/api/voice-diagnostic/prompts/");
}

export function startVoiceDiagnosticSession() {
  return request<VoiceDiagnosticSessionStart>("/api/voice-diagnostic/sessions/start/", {
    method: "POST",
    body: JSON.stringify({}),
  });
}

export function getVoiceDiagnosticSessions() {
  return request<VoiceDiagnosticHistorySession[]>("/api/voice-diagnostic/sessions/");
}

export function getVoiceDiagnosticSession(sessionId: number) {
  return request<VoiceDiagnosticHistoryDetail>(`/api/voice-diagnostic/sessions/${sessionId}/`);
}

export function getVoiceDiagnosticReport(sessionId: number) {
  return request<VoiceDiagnosticReport>(`/api/voice-diagnostic/sessions/${sessionId}/report/`);
}

export function requestTTS(text: string) {
  return requestBlob("/api/voice-diagnostic/tts/", {
    method: "POST",
    body: JSON.stringify({ text }),
  });
}

export function evaluatePronunciation(audioBlob: Blob, targetSentence: string) {
  const formData = new FormData();
  formData.append("audio_file", audioBlob, "pronunciation.webm");
  formData.append("target_sentence", targetSentence);
  formData.append("update_mastery", "false");

  return request<PronunciationResult>("/api/voice-diagnostic/pronunciation/evaluate/", {
    method: "POST",
    body: formData,
  });
}

export function evaluatePronunciationPreview(audioBlob: Blob, targetSentence: string) {
  const formData = new FormData();
  formData.append("audio_file", audioBlob, "pronunciation.webm");
  formData.append("target_sentence", targetSentence);
  formData.append("update_mastery", "false");

  return request<PronunciationResult>("/api/voice-diagnostic/pronunciation/evaluate/", {
    method: "POST",
    body: formData,
  });
}

export function evaluateListening(
  question: string,
  expectedAnswer: string,
  userAnswer: string,
) {
  return request<ListeningResult>("/api/voice-diagnostic/listening/evaluate/", {
    method: "POST",
    body: JSON.stringify({
      question,
      expected_answer: expectedAnswer,
      user_answer: userAnswer,
      update_mastery: false,
    }),
  });
}

export function evaluateListeningPreview(
  question: string,
  expectedAnswer: string,
  userAnswer: string,
) {
  return request<ListeningResult>("/api/voice-diagnostic/listening/evaluate/", {
    method: "POST",
    body: JSON.stringify({
      question,
      expected_answer: expectedAnswer,
      user_answer: userAnswer,
      update_mastery: false,
    }),
  });
}

export function evaluateSpeaking(audioBlob: Blob, question: string) {
  const formData = new FormData();
  formData.append("audio_file", audioBlob, "speaking.webm");
  formData.append("question", question);
  formData.append("update_mastery", "false");

  return request<SpeakingResult>("/api/voice-diagnostic/speaking/evaluate/", {
    method: "POST",
    body: formData,
  });
}

export function evaluateSpeakingPreview(audioBlob: Blob, question: string) {
  const formData = new FormData();
  formData.append("audio_file", audioBlob, "speaking.webm");
  formData.append("question", question);
  formData.append("update_mastery", "false");

  return request<SpeakingResult>("/api/voice-diagnostic/speaking/evaluate/", {
    method: "POST",
    body: formData,
  });
}

export function submitPronunciationDiagnosticBatch({
  sessionId,
  items,
}: {
  sessionId?: number;
  items: Array<{ target_sentence: string; transcript: string }>;
}) {
  return request<PronunciationBatchResult>("/api/voice-diagnostic/pronunciation/evaluate-batch/", {
    method: "POST",
    body: JSON.stringify({ session_id: sessionId, items }),
  });
}

export function submitListeningDiagnosticBatch({
  sessionId,
  items,
}: {
  sessionId?: number;
  items: Array<{
    passage: string;
    question: string;
    expected_answer: string;
    answer: string;
  }>;
}) {
  return request<ListeningBatchResult>("/api/voice-diagnostic/listening/evaluate-batch/", {
    method: "POST",
    body: JSON.stringify({ session_id: sessionId, items }),
  });
}

export function submitSpeakingDiagnosticBatch({
  sessionId,
  items,
}: {
  sessionId?: number;
  items: Array<{ question: string; transcript: string }>;
}) {
  return request<SpeakingBatchResult>("/api/voice-diagnostic/speaking/evaluate-batch/", {
    method: "POST",
    body: JSON.stringify({ session_id: sessionId, items }),
  });
}
