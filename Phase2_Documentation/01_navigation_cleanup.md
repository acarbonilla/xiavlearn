# Navigation Cleanup

## Problem

The learner navbar was previously too crowded when diagnostics, voice tools, account identity, and logout all competed for top-level space.

## Solution

The current header groups related actions into dropdowns inside `Frontend/src/components/Header.tsx`.

Implemented structure:

```text
Dashboard
Recommendation
Study Plan
Assessment ▼
  Text Diagnostic
  Voice Diagnostic
Teacher Sessions ▼
  Speaking Teacher
  Listening Teacher
  Pronunciation Teacher
username ▼
  Signed in as username
  Logout
```

## Final Navigation Structure

- Top-level links:
  - `Dashboard`
  - `Recommendation`
  - `Study Plan`
- Dropdown groups:
  - `Assessment`
  - `Teacher Sessions`
  - account menu using the signed-in username

## Routes

```text
/diagnostic
/voice-diagnostic
/speaking-teacher
/listening-teacher
/pronunciation-teacher
/recommendation
/study-plan
/dashboard
```

## Account Dropdown

- Logged-in users see the username as the account trigger.
- The dropdown shows:

```text
Signed in as username
Logout
```

- Logged-out users see `Login` and `Sign Up` links instead of the account menu.

## Acceptance Rules

```text
Login and Sign Up remain visible only when logged out.
Username and Logout are grouped when logged in.
Assessment contains Text Diagnostic and Voice Diagnostic.
Teacher Sessions contains Speaking, Listening, and Pronunciation teacher routes.
```

## Files Affected

- `Frontend/src/components/Header.tsx`

## Notes

The V5 `Voice Conversation` entry discussed later is not present in the current navbar yet. That remains planned behavior, not implemented behavior.
