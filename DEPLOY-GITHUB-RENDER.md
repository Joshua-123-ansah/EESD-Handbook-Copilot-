# Deploy using GitHub + Render (recommended)

## Can this run “on GitHub”?

- **GitHub (the website)** stores your code. It does **not** run FastAPI, Chroma, or OpenAI calls for visitors.
- **GitHub Pages** only hosts **static** files (HTML/CSS). It cannot run this chatbot backend.
- The usual setup is: **GitHub** (code) + **Render** (or Railway, Fly.io, etc.) to **run** the app. Render pulls from GitHub whenever you push.

## Before you start

1. **GitHub account** and **Render account** (free tier is fine for a class demo).
2. **`OPENAI_API_KEY`** from OpenAI (set on Render only, never in git).
3. **`EESD_Handbook_2024-2025AY-FINAL.pdf`** committed in the **root** of the repo (same folder as `Dockerfile`). Your project already has this file locally; make sure `git status` shows it and you are allowed to push it (use a **private** repo if the handbook must not be public).

## Step 1: Push the project to GitHub

From your project folder (adjust branch name if you use `main`):

```bash
git init
git add .
git status
```

Confirm `.env` is **not** listed (it should be ignored). Confirm the PDF **is** listed if you want Docker builds on Render to work.

```bash
git commit -m "Add handbook assistant and deployment files"
```

Create a new empty repository on GitHub (no README needed). Then:

```bash
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
git branch -M main
git push -u origin main
```

Replace `YOUR_USERNAME` and `YOUR_REPO` with yours.

## Step 2: Create the web service on Render

1. Log in at [render.com](https://render.com) and connect your GitHub account when asked.
2. **New** → **Web Service**.
3. **Connect** the repository you just pushed.
4. Configure:
   - **Name:** anything (e.g. `eesd-handbook-assistant`).
   - **Region:** choose closest to you.
   - **Branch:** `main` (or whatever you use).
   - **Root directory:** leave empty (repo root).
   - **Runtime:** **Docker**.
   - **Dockerfile path:** `Dockerfile`.
   - **Instance type:** Free (ok for demos; see caveats in `DEPLOY.md`).
5. Open **Advanced** (or **Environment**):
   - **Add environment variable:** `OPENAI_API_KEY` = your key (paste as **secret**).
6. **Create Web Service** and wait for the first build (several minutes the first time).

## Step 3: Check that it is alive

When Render shows **Live**, open:

- Chat: `https://YOUR-SERVICE-NAME.onrender.com/`
- Portfolio: `https://YOUR-SERVICE-NAME.onrender.com/portfolio/`

If chat says the index is still building, wait 1–3 minutes and try again. You can also open:

- `https://YOUR-SERVICE-NAME.onrender.com/health`

When `"rag_ready": true`, handbook questions should work.

## Step 4: Give faculty two links

Send them exactly:

1. `https://YOUR-SERVICE-NAME.onrender.com/`
2. `https://YOUR-SERVICE-NAME.onrender.com/portfolio/`

No install steps on their side.

## Optional: Blueprint instead of clicking

In the Render dashboard you can use **New** → **Blueprint** and point at this repo so `render.yaml` pre-fills the Docker service. You still add `OPENAI_API_KEY` in the dashboard when prompted.

## If the build fails on Render

- **“COPY … pdf: not found”:** the PDF was not pushed to GitHub. Add, commit, and push `EESD_Handbook_2024-2025AY-FINAL.pdf`.
- **Docker build error from Chroma / Python:** paste the log into a search or ask for help with the exact error line.
- **Deploy timeout:** first Chroma build is heavy; try deploying again, or temporarily set the service health check to `/health` with a longer grace period in Render service settings.
