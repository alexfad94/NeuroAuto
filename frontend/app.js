const sessionId = `session_${Math.random().toString(36).slice(2, 10)}`;
const panelEl = document.getElementById("assistant-panel");
const overlayEl = document.getElementById("overlay");
const toggleEl = document.getElementById("assistant-toggle");
const closeEl = document.getElementById("assistant-close");
const logEl = document.getElementById("chat-log");
const formEl = document.getElementById("chat-form");
const inputEl = document.getElementById("message");
const statusEl = document.getElementById("status");
const quickActionsEl = document.getElementById("quick-actions");
const typingEl = document.getElementById("typing");

function setPanelOpen(open) {
  panelEl.classList.toggle("open", open);
  overlayEl.classList.toggle("open", open);
  panelEl.setAttribute("aria-hidden", open ? "false" : "true");
  if (open) inputEl.focus();
}

function addMessage(text, role) {
  const div = document.createElement("div");
  div.className = `msg ${role}`;
  div.textContent = text;
  logEl.appendChild(div);
  logEl.scrollTop = logEl.scrollHeight;
}

async function sendMessage(message) {
  statusEl.textContent = "Отправляем...";
  typingEl.classList.remove("hidden");
  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 20000);
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      signal: controller.signal,
      body: JSON.stringify({
        session_id: sessionId,
        message,
        client_name: "Гость сайта",
        preferred_contact: "call",
      }),
    });
    clearTimeout(timer);
    if (!res.ok) {
      throw new Error(`HTTP ${res.status}`);
    }
    const data = await res.json();
    addMessage(data.answer, "bot");
    statusEl.textContent = data.escalated
      ? "Запрос передан менеджеру."
      : "Ответ готов.";
  } catch (error) {
    console.error("Chat request failed:", error);
    const msg =
      error?.name === "AbortError"
        ? "Сервер долго отвечает. Попробуйте еще раз."
        : "Сервер недоступен или вернул ошибку. Проверьте, что backend запущен.";
    addMessage(msg, "bot");
    statusEl.textContent = error?.message
      ? `Ошибка: ${error.message}`
      : "Ошибка запроса.";
  } finally {
    typingEl.classList.add("hidden");
  }
}

async function submitMessage(rawMessage) {
  const message = rawMessage.trim();
  if (!message) return;
  addMessage(message, "user");
  inputEl.value = "";
  await sendMessage(message);
}

formEl.addEventListener("submit", async (e) => {
  e.preventDefault();
  await submitMessage(inputEl.value);
});

quickActionsEl.addEventListener("click", async (e) => {
  const target = e.target;
  if (!(target instanceof HTMLButtonElement)) return;
  const text = target.dataset.prompt || "";
  await submitMessage(text);
});

toggleEl.addEventListener("click", () => {
  setPanelOpen(!panelEl.classList.contains("open"));
});
closeEl.addEventListener("click", () => setPanelOpen(false));
overlayEl.addEventListener("click", () => setPanelOpen(false));

window.addEventListener("keydown", (e) => {
  if (e.key === "Escape") setPanelOpen(false);
});

addMessage(
  "Здравствуйте! Я NeuroAuto Assistant. Помогу выбрать автомобиль, рассчитать кредит или записать вас на тест-драйв. Что вам интереснее всего?",
  "bot"
);
