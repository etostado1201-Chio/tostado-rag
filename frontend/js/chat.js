/* Tostado Restaurant Group — chat front-end */

const messagesEl = document.getElementById("messages");
const formEl     = document.getElementById("chatForm");
const inputEl    = document.getElementById("chatInput");
const sendBtn    = document.getElementById("sendBtn");
const micBtn     = document.getElementById("micBtn");
const ttsToggle  = document.getElementById("ttsToggle");

/* ---------------------------------------------------------------------- */
/* Textarea ergonomics                                                    */
/* ---------------------------------------------------------------------- */

inputEl.addEventListener("input", () => {
  inputEl.style.height = "auto";
  inputEl.style.height = Math.min(inputEl.scrollHeight, 160) + "px";
});

inputEl.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    formEl.requestSubmit();
  }
});

document.querySelectorAll(".suggestions li").forEach((li) => {
  li.addEventListener("click", () => {
    inputEl.value = li.dataset.prompt;
    inputEl.dispatchEvent(new Event("input"));
    inputEl.focus();
  });
});

/* ---------------------------------------------------------------------- */
/* Render helpers                                                         */
/* ---------------------------------------------------------------------- */

function appendMessage(role, text) {
  const div = document.createElement("div");
  div.className = `msg msg--${role}`;
  div.textContent = text;
  messagesEl.appendChild(div);
  div.scrollIntoView({ behavior: "smooth", block: "end" });
  return div;
}

function appendSources(parent, sources) {
  if (!sources || !sources.length) return;
  const det = document.createElement("details");
  det.className = "sources";

  const sum = document.createElement("summary");
  sum.textContent = `Retrieved ${sources.length} source${sources.length > 1 ? "s" : ""}`;
  det.appendChild(sum);

  const ul = document.createElement("ul");
  sources.forEach((s) => {
    const li = document.createElement("li");
    const meta = s.metadata || {};
    const tag  = meta.type ? meta.type.toUpperCase() : "DOC";
    const id   = meta.store_id || meta.employee_id || meta.department || "";
    const head = `[${tag}] ${id}`.trim();
    const snippet = (s.content || "").replace(/\s+/g, " ").slice(0, 110);
    li.textContent = `${head} — ${snippet}…`;
    ul.appendChild(li);
  });
  det.appendChild(ul);
  parent.appendChild(det);
}

function appendFollowups(parent, followups) {
  if (!followups || !followups.length) return;
  const wrap = document.createElement("div");
  wrap.className = "followups";

  const label = document.createElement("div");
  label.className = "followups__label";
  label.textContent = "Suggested next questions";
  wrap.appendChild(label);

  followups.forEach((q) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "followups__chip";
    btn.textContent = q;
    btn.addEventListener("click", () => {
      inputEl.value = q;
      inputEl.dispatchEvent(new Event("input"));
      formEl.requestSubmit();
    });
    wrap.appendChild(btn);
  });

  parent.appendChild(wrap);
}

function appendTyping() {
  const t = document.createElement("div");
  t.className = "typing";
  t.id = "typing";
  t.innerHTML = "<span></span><span></span><span></span>";
  messagesEl.appendChild(t);
  t.scrollIntoView({ behavior: "smooth", block: "end" });
}
function removeTyping() {
  document.getElementById("typing")?.remove();
}

/* ---------------------------------------------------------------------- */
/* Text-to-Speech (browser-native SpeechSynthesis)                        */
/* ---------------------------------------------------------------------- */

function speak(text) {
  if (!ttsToggle.checked) return;
  if (!("speechSynthesis" in window)) return;
  // Strip markdown-ish characters that sound bad when read aloud.
  const clean = text.replace(/[*_`#]/g, "").replace(/\s+/g, " ");
  const u = new SpeechSynthesisUtterance(clean);
  u.rate  = 1.0;
  u.pitch = 1.0;
  // Try to pick an English voice if available.
  const voices = window.speechSynthesis.getVoices();
  const en = voices.find(v => v.lang && v.lang.startsWith("en"));
  if (en) u.voice = en;
  window.speechSynthesis.cancel();    // stop any ongoing read-out
  window.speechSynthesis.speak(u);
}

/* ---------------------------------------------------------------------- */
/* Speech-to-Text (MediaRecorder -> POST /api/transcribe)                 */
/* ---------------------------------------------------------------------- */

let mediaRecorder = null;
let audioChunks   = [];

async function startRecording() {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });

    // Pick a mime type the browser actually supports.
    const candidates = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg", "audio/mp4"];
    const mimeType = candidates.find(t => window.MediaRecorder?.isTypeSupported?.(t)) || "";

    mediaRecorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
    audioChunks = [];

    mediaRecorder.ondataavailable = (e) => {
      if (e.data.size > 0) audioChunks.push(e.data);
    };

    mediaRecorder.onstop = async () => {
      stream.getTracks().forEach(t => t.stop());
      micBtn.classList.remove("is-recording");

      const blob = new Blob(audioChunks, { type: mimeType || "audio/webm" });
      if (blob.size === 0) return;

      const ext = (mimeType.includes("ogg")) ? "ogg"
                : (mimeType.includes("mp4")) ? "mp4"
                : "webm";

      micBtn.disabled = true;
      const placeholder = inputEl.value;
      inputEl.value = "Transcribing…";

      try {
        const fd = new FormData();
        fd.append("audio", blob, `recording.${ext}`);
        const res = await fetch("/api/transcribe", { method: "POST", body: fd });
        const data = await res.json();

        if (!res.ok) {
          appendMessage("bot", data.error || "Transcription failed.");
          inputEl.value = placeholder;
        } else {
          inputEl.value = (data.text || "").trim();
          inputEl.dispatchEvent(new Event("input"));
          inputEl.focus();
        }
      } catch (err) {
        appendMessage("bot", "Network error during transcription: " + err.message);
        inputEl.value = placeholder;
      } finally {
        micBtn.disabled = false;
      }
    };

    mediaRecorder.start();
    micBtn.classList.add("is-recording");
  } catch (err) {
    appendMessage("bot", "Microphone access denied: " + err.message);
  }
}

function stopRecording() {
  if (mediaRecorder && mediaRecorder.state === "recording") {
    mediaRecorder.stop();
  }
}

micBtn.addEventListener("click", () => {
  if (!navigator.mediaDevices?.getUserMedia) {
    appendMessage("bot", "Your browser does not support microphone capture.");
    return;
  }
  if (mediaRecorder && mediaRecorder.state === "recording") {
    stopRecording();
  } else {
    startRecording();
  }
});

/* ---------------------------------------------------------------------- */
/* Submit handler                                                         */
/* ---------------------------------------------------------------------- */

formEl.addEventListener("submit", async (e) => {
  e.preventDefault();
  const text = inputEl.value.trim();
  if (!text || text === "Transcribing…") return;

  appendMessage("user", text);
  inputEl.value = "";
  inputEl.style.height = "auto";
  sendBtn.disabled = true;
  appendTyping();

  try {
    const res = await fetch("/api/chat", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ message: text }),
    });
    const data = await res.json();
    removeTyping();

    if (!res.ok) {
      appendMessage("bot", data.error || "Something went wrong.");
    } else {
      const botEl = appendMessage("bot", data.answer || "(no answer)");
      appendSources(botEl, data.sources);
      appendFollowups(botEl, data.followups);
      speak(data.answer || "");
    }
  } catch (err) {
    removeTyping();
    appendMessage("bot", "Network error: " + err.message);
  } finally {
    sendBtn.disabled = false;
    inputEl.focus();
  }
});

/* ---------------------------------------------------------------------- */
/* Greeting                                                               */
/* ---------------------------------------------------------------------- */

appendMessage(
  "bot",
  "Welcome. I'm the Tostado Restaurant Group assistant. Ask me about any of the 500 stores across our four brands, vendor accounts, or corporate departments. Tap the microphone to speak — or toggle voice replies on top to hear my answers."
);

