# Interview Bot (ABC Inc)

A Streamlit-based interview platform with:
- Candidate registration/login and dashboard
- Role-based interview flow (text or speech answers)
- Automated scoring and policy checks
- Admin control center for review, analytics, and actions

## Features

- Candidate onboarding
  - Registration and login
  - Password hashing with Werkzeug
  - Profile + role/specialization flow
- Interview engine
  - Question generation
  - Text mode and speech mode
  - Speech-to-text using Google Speech Recognition
  - Question read-aloud via browser speech synthesis
- Evaluation and policy
  - Relevance/confidence/coverage scoring
  - Plagiarism and duplication checks
  - Auto-ban workflows for policy violations
  - Retest support
- Admin dashboard
  - Candidate review and answer-level insights
  - Ban/unban controls with action logging
  - Analytics (bar/line/pie) rendered
  - Audit log and report download

## Project Structure

```text
.
|- login.py                # Candidate app entrypoint
|- pages/
|  `- admin.py             # Admin dashboard entrypoint
|  `- interview.py         # Interview experience page
|- intents.json            # Question/intent data
|- users.db                # SQLite database (runtime)
`- requirements.txt
```
```

## Default Admin Login

- Username: `Admin`
- Password: `Admin123`

## Notes

- The app creates/updates required SQLite schema automatically.
- Speech mode uses `SpeechRecognition` with Google recognizer.
- Browser permissions are required for mic/audio features.
- If microphone fallback is used on your machine, you may also need PyAudio.

##APP LINK
Applink: https://interview-bot-a4a3uno3n2hha4zqgxbplx.streamlit.app
