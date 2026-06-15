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
    plan_data: { focus?: string[]; days?: string[] };
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

export type DiagnosticAnswerFeedback = {
  question: string;
  answer: string;
  feedback: string;
};

export type DiagnosticResult = {
  overall_level: string;
  skill_scores: Record<string, number>;
  weak_skills: string[];
  recommendation: string;
  level_explanation: string;
  answer_feedback: DiagnosticAnswerFeedback[];
  next_step: string;
};

export type RecommendationData = {
  recommended_module: ModuleSummary | null;
  reason: string;
};

export type TeacherSession = {
  session_id: number;
  lesson: string;
  practice_question: string;
};

export type TeacherFeedback = {
  score: number;
  feedback: string;
  updated_mastery: {
    skill: string;
    score: number;
    status: string;
  };
};

export type StudyPlanData = {
  plan: {
    focus: string[];
    days: string[];
  };
};

export type CoachSummary = {
  summary: string;
  next_step: string;
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
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    credentials: "include",
    headers: {
      Accept: "application/json",
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
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

export function generateStudyPlan() {
  return request<StudyPlanData>("/api/scheduler/generate-plan/", {
    method: "POST",
    body: JSON.stringify({}),
  });
}

export function getCoachSummary() {
  return request<CoachSummary>("/api/coach/summary/");
}
