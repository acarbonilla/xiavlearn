# Verification Checklist

## Navigation Checklist

- [ ] Assessment dropdown contains `Text Diagnostic` and `Voice Diagnostic`.
- [ ] Teacher Sessions dropdown contains `Speaking Teacher`, `Listening Teacher`, and `Pronunciation Teacher`.
- [ ] Account dropdown contains the username and `Logout`.
- [ ] Logged-out state shows `Login` and `Sign Up`.

## Teacher Session Checklist

- [ ] Speaking teacher page loads from `/speaking-teacher`.
- [ ] Listening teacher page loads from `/listening-teacher`.
- [ ] Pronunciation teacher page loads from `/pronunciation-teacher`.
- [ ] Teacher sessions use practice labels such as `Practice Score` and `Final Practice Result`.
- [ ] Teacher sessions do not claim official mastery updates.

## Voice Diagnostic Checklist

- [ ] Voice Diagnostic completes Pronunciation, Listening, and Speaking sections.
- [ ] Each voice skill uses 3 items.
- [ ] Final voice scores are aggregated from item scores.
- [ ] Voice Diagnostic saves `VoiceDiagnosticSession`.
- [ ] Voice Diagnostic saves `VoiceDiagnosticItem` records.
- [ ] Voice Diagnostic history is private to the signed-in user.
- [ ] Voice Diagnostic report shows `Official Mastery Updated`.
- [ ] Voice Diagnostic report shows recommended focus.
- [ ] Voice Diagnostic report links to the matching teacher session.

## SkillMastery Checklist

- [ ] Dashboard reads official `SkillMastery`.
- [ ] Recommendation reads latest official `SkillMastery`.
- [ ] Study Plan uses official `SkillMastery`-derived focus.
- [ ] Teacher Sessions do not update `SkillMastery`.
- [ ] Voice diagnostic updates official voice `SkillMastery`.
- [ ] Pronunciation does not block CEFR progression under current rules.

## Recommendation Checklist

- [ ] Recommendation reflects latest official mastery after diagnostics.
- [ ] Weak voice skills can be recommended.
- [ ] Voice recommendation routes to the matching voice teacher session.
- [ ] Text skill recommendation still supports module-based lessons.

## Study Plan Checklist

- [ ] Study Plan routes Pronunciation focus to `/pronunciation-teacher`.
- [ ] Study Plan routes Listening focus to `/listening-teacher`.
- [ ] Study Plan routes Speaking focus to `/speaking-teacher`.
- [ ] Study Plan does not show module-fallback warnings for implemented voice teacher routes.

## V5 Readiness Checklist

- [ ] V5 voice conversation plan is documented.
- [ ] V5 is marked as planned, not implemented.
- [ ] Practice-only rule is preserved for V5.
- [ ] Proposed models and endpoints are documented for future work.

## Commands

```bash
python manage.py test agents learning --keepdb --noinput
npm run lint
npm run build
```

Windows PowerShell backend test command:

```powershell
$env:DEBUG='True'; .\.venv\Scripts\python.exe manage.py test agents learning --keepdb --noinput
```
