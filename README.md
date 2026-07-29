# Deep-Tech Briefing Mail Agent

This is a bot that runs every 3 days. It checks new AI/ML/Robotics research papers on arXiv and trending repos on GitHub, picks the best ones using an AI model, and emails you a short report. It can also read the report out loud as an audio file attached to the email.

Everything runs for free using GitHub Actions, Groq, and Gmail.

---

## How it works 

1. **Check if it's actually time to run.** The trigger might fire every day, but this bot is only supposed to send every 3 days. So first it checks the last run time. If it's too soon, it stops here and does nothing.

2. **Pull new papers and repos.** It grabs papers from arXiv and repos from GitHub, but only ones from since the last time it ran. It also skips anything it already sent before.

3. **Filter with keywords first.** Before spending AI credits, it does a cheap keyword check to throw out anything obviously irrelevant. This keeps the AI step small and cheap.

4. **Score everything with AI.** Each paper/repo gets a score out of 10. If a score is clearly high or clearly low, that's final. If a score is unclear (borderline), it gets looked at again with more detail, then double-checked once more. This only happens for the unclear ones, not everything — otherwise it would use too many AI credits.

5. **Write a script for the audio.** Once the final list is picked, one more AI call turns it into a short spoken script.

6. **Turn the script into audio.** If this step fails for any reason, the email still gets sent without audio. It never blocks the whole thing.

7. **Send the email.** Each person on the list gets their own separate email (not one email with everyone CC'd). The email has both a plain text version and a nice-looking version, plus the audio file attached if it worked.

8. **Save what happened.** It saves the current time and what was sent, so next time it knows where to pick up from.

---

## Why some things are built the way they are

**Why no database.**
The only thing that needs to be remembered between runs is "when did I last run" and "what did I already send." That's one small file (`last_run.json`), not a database. A database would be overkill for this.

**Why the schedule check is inside the code, not the trigger.**
The free scheduler (cron-job.org) can't do "every 3 days" cleanly — it only offers daily, monthly, etc. So instead of fighting with that, the code itself checks the last run time and skips early if it's too soon. The trigger can fire every day and it's fine — most days it'll just do nothing and exit in a second.

**Why scoring is done in steps instead of all at once.**
Most papers get scored once and that's it — cheap and fast. Only the unclear ones (borderline scores) get a second, more detailed look, plus one more check to keep the scoring consistent. This keeps AI usage low, but still gives unclear cases a fair second chance. There's also a hard limit on how many items can get this extra treatment per run, so it can never spiral into using too many AI credits even on a busy day.

**Why writing the audio script is separate from scoring.**
Scoring is about judging quality. Writing is about making it sound natural when read out loud. Those are two different jobs, so they're two separate AI steps. Writing only happens once per run (not once per item), so it's cheap either way.

**Why each person gets their own email instead of one email to everyone.**
If one person's email address is wrong or bounces, it doesn't affect anyone else's email in that run.

**Why the email has both plain text and a styled version.**
Plain text is what actually helps avoid spam filters. The styled version is what people actually see when they open it. Both are included together.

**Why the AI's math symbols get cleaned up before sending.**
arXiv papers often have raw math code in the title, like `$\pi\mathbf{R}^2$`. Left as-is, it looks broken and also looks suspicious to spam filters. So it gets cleaned into plain readable text before the email is built.

---

## Files in this project

| File | What it does |
|---|---|
| `config.yaml` | All the settings you can tune — topics, thresholds, voice, etc.  |
| `main.py` | Runs everything in order |
| `state.py` | Remembers the last run time and what was already sent |
| `ingest_arxiv.py` | Pulls new papers from arXiv |
| `ingest_github.py` | Pulls trending repos from GitHub |
| `score_agent.py` | The AI scoring + writing step |
| `audio_gen.py` | Turns the script into an audio file |
| `send_email.py` | Builds and sends the email |
| `requirements.txt` | Python packages needed |
| `.github/workflows/trigger.yml` | The GitHub Actions workflow that runs everything |

---

## Real problems we hit while building this (and the fix)

- **Audio doesn't show up as a playable button at the top of the email.** Gmail doesn't allow that for security reasons. It shows up as a normal attachment instead. This can't be fixed from our side — it's just how email works.

- **First email to someone new can land in Spam even if your account is fine.** This happened during testing. It wasn't the account's fault — it was the combination of an attachment + many links + newsletter-style layout, which looks like spam to filters regardless of sender. Mark it "Not spam" the first time and it gets better after that.

- **A narrow test (1 topic, short time window) can return 0 results.** That's normal, not a bug — proven by testing the real GitHub search directly and getting results back fine. The full settings (6 topics, 6 categories) return real results.

- **The workflow file has to be in a specific folder** (`.github/workflows/`), or GitHub won't recognize it at all — no error, it just won't show up.

- **Pushing that workflow file needs a token with "Workflows" permission specifically.** A token without it gets rejected by GitHub, even if it has full write access to everything else.

---

## What you need before running this

| Secret name | What it's for | Where to get it |
|---|---|---|
| `GROQ_API_KEY` | AI scoring + writing | console.groq.com |
| `GH_PAT` | GitHub search + triggering the workflow | GitHub → fine-grained token, scoped to this repo, with Actions + Contents + Workflows all set to read/write |
| `SMTP_USERNAME` | The email address sending the briefing | Your Gmail address |
| `SMTP_PASSWORD` | Login for sending | Gmail App Password (not your normal password) |
| `RECIPIENT_LIST` | Who receives it | Comma-separated email addresses |

All of these go into: repo → Settings → Secrets and variables → Actions.

To trigger it automatically, cron-job.org calls GitHub's API to run the workflow. Any schedule works (even daily) because the code itself decides whether it's actually the right day to send.