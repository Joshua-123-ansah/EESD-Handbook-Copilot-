# Host this app (one link for faculty)

**Step-by-step (GitHub + Render):** see **[DEPLOY-GITHUB-RENDER.md](./DEPLOY-GITHUB-RENDER.md)**.

You need:

1. **`EESD_Handbook_2024-2025AY-FINAL.pdf`** in the project root (same folder as `Dockerfile`). The Docker image copies it; without it, the build fails.
2. An **`OPENAI_API_KEY`** from OpenAI (paid or credit-backed). Set it only in the host’s dashboard, never commit it.

After deploy, faculty open:

- **Chatbot:** `https://YOUR-SERVICE.onrender.com/`
- **Portfolio:** `https://YOUR-SERVICE.onrender.com/portfolio/`

## Option A: Render (Docker)

1. Push this repo to GitHub (include the PDF if policy allows).
2. [Render](https://render.com) → **New** → **Blueprint** → connect the repo → select `render.yaml`,  
   **or** **New** → **Web Service** → connect repo → **Docker**, root directory `/`, Dockerfile path `Dockerfile`.
3. In **Environment**, add `OPENAI_API_KEY` (secret).
4. Deploy. First boot builds the Chroma index in the background; `/health` returns `rag_ready: false` until it finishes. Wait 1–3 minutes, refresh `rag_ready` until `true`, then try chat.
5. Free tier **spins down** when idle; the next visit may be slow and may **rebuild** the index (ephemeral disk). For a stable demo, use a paid instance or accept the wait.

**Health check:** use path `/health`. Render’s default timeout can be tight on first index build; if deploy fails, retry once the service is up, or increase health check grace period in the service settings.

## Option B: Run the Docker image locally

```bash
docker build -t handbook-app .
docker run --rm -p 8000:8000 -e OPENAI_API_KEY=sk-... handbook-app
```

Open http://localhost:8000 and http://localhost:8000/portfolio/

## What we changed for hosting

- **`CHROMA_DIR`** defaults under the project root so the index is not written to a random working directory.
- **RAG loads in a background thread** after the API starts so platforms get HTTP 200 from `/health` while Chroma builds.

## If you cannot put the PDF on GitHub

Use a private repo, or deploy from your machine with `docker build` and push the image to a registry, or zip-upload to a host that accepts artifacts. Do not share the handbook publicly if your program forbids it.
