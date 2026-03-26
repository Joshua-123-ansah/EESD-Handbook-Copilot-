const messagesEl = document.getElementById("messages");
const formEl = document.getElementById("chat-form");
const inputEl = document.getElementById("message-input");
const micBtnEl = document.getElementById("mic-btn");
const voiceStatusEl = document.getElementById("voice-status");

let mediaRecorder = null;
let recordedChunks = [];
let isRecording = false;
let currentAudio = null;

function stopCurrentAudio() {
  if (currentAudio) {
    currentAudio.pause();
    currentAudio.currentTime = 0;
    currentAudio = null;
  }
}

function getSessionId() {
  let id = localStorage.getItem("session_id");
  if (!id) {
    id = "sess_" + Math.random().toString(16).slice(2) + "_" + Date.now().toString(16);
    localStorage.setItem("session_id", id);
  }
  return id;
}

function appendMessage(who, text, { sources } = {}) {
  const row = document.createElement("div");
  row.className = "msg";

  const whoEl = document.createElement("div");
  whoEl.className = "who";
  whoEl.textContent = who;

  const bubble = document.createElement("div");
  bubble.className = "bubble" + (who === "You" ? " user" : "");
  bubble.textContent = text;

  if (sources && sources.length > 0) {
    const srcEl = document.createElement("div");
    srcEl.className = "sources";
    const pages = [...new Set(sources.map((s) => s.page))].sort((a, b) => a - b);
    srcEl.textContent = "Sources: " + pages.map((p) => "Page " + p).join(", ");
    bubble.appendChild(srcEl);
  }

  row.appendChild(whoEl);
  row.appendChild(bubble);
  messagesEl.appendChild(row);
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

async function sendMessage(message, { speakReply = false } = {}) {
  const session_id = getSessionId();

  appendMessage("You", message);
  inputEl.value = "";

  const loadingId = "loading_" + Date.now().toString(16);
  appendMessage("Assistant", "Thinking...", { sources: [] });

  const resp = await fetch("/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id, message }),
  });

  if (!resp.ok) {
    appendMessage("Assistant", "Error: " + (await resp.text()));
    return;
  }

  const data = await resp.json();

  // Replace the last "Thinking..." message.
  const last = messagesEl.lastElementChild;
  if (last) {
    const bubble = last.querySelector(".bubble");
    if (bubble) bubble.textContent = data.answer;

    if (data.citations && data.citations.length > 0) {
      const srcEl = document.createElement("div");
      srcEl.className = "sources";
      const pages = [...new Set(data.citations.map((s) => s.page))].sort((a, b) => a - b);
      srcEl.textContent = "Sources: " + pages.map((p) => "Page " + p).join(", ");
      bubble.appendChild(srcEl);
    }
  }

  if (speakReply) {
    playAssistantVoice(data.answer).catch(() => {
      // Voice playback failure should not block text chat.
    });
  }
}

async function playAssistantVoice(text) {
  const resp = await fetch("/text-to-speech", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
  if (!resp.ok) return;

  const blob = await resp.blob();
  const url = URL.createObjectURL(blob);

  stopCurrentAudio();

  const audio = new Audio(url);
  currentAudio = audio;
  audio.onended = () => URL.revokeObjectURL(url);
  await audio.play();
}

function setVoiceStatus(text) {
  if (voiceStatusEl) {
    voiceStatusEl.textContent = text;
  }
}

async function ensureRecorder() {
  if (mediaRecorder) return;

  const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  mediaRecorder = new MediaRecorder(stream);

  mediaRecorder.ondataavailable = (event) => {
    if (event.data && event.data.size > 0) {
      recordedChunks.push(event.data);
    }
  };

  mediaRecorder.onstop = async () => {
    if (!recordedChunks.length) {
      setVoiceStatus("No voice captured. Try again.");
      return;
    }

    setVoiceStatus("Transcribing voice...");
    const audioBlob = new Blob(recordedChunks, { type: "audio/webm" });
    recordedChunks = [];

    const formData = new FormData();
    formData.append("file", audioBlob, "voice-message.webm");

    const sttResp = await fetch("/speech-to-text", {
      method: "POST",
      body: formData,
    });
    if (!sttResp.ok) {
      setVoiceStatus("Voice transcription failed.");
      return;
    }

    const data = await sttResp.json();
    const text = (data.text || "").trim();
    if (!text) {
      setVoiceStatus("Could not understand audio. Please try again.");
      return;
    }

    inputEl.value = text;
    setVoiceStatus("Voice captured. Sending message...");
    await sendMessage(text, { speakReply: true });
    setVoiceStatus("Answers are grounded in the handbook and include page citations.");
  };
}

async function toggleRecording() {
  try {
    await ensureRecorder();
  } catch (err) {
    setVoiceStatus("Microphone permission denied or unavailable.");
    return;
  }

  if (!isRecording) {
    recordedChunks = [];
    mediaRecorder.start();
    isRecording = true;
    micBtnEl.classList.add("recording");
    micBtnEl.textContent = "Stop Voice";
    setVoiceStatus("Recording... click Stop Voice when done.");
    return;
  }

  mediaRecorder.stop();
  isRecording = false;
  micBtnEl.classList.remove("recording");
  micBtnEl.textContent = "Start Voice";
}

formEl.addEventListener("submit", (e) => {
  e.preventDefault();
  const message = inputEl.value.trim();
  if (!message) return;
  // Typed messages should not speak; also stop any previous audio playback.
  stopCurrentAudio();
  sendMessage(message, { speakReply: false }).catch((err) => {
    appendMessage("Assistant", "Error: " + err);
  });
});

if (micBtnEl) {
  micBtnEl.addEventListener("click", () => {
    toggleRecording().catch((err) => {
      setVoiceStatus("Voice error: " + err);
    });
  });
}

// Optional starter message.
appendMessage("Assistant", "Hello! Ask me anything from the handbook.", { sources: [] });

