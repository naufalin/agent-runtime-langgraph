const messagesEl = document.getElementById("messages");
const messageInput = document.getElementById("messageInput");
const sendBtn = document.getElementById("sendBtn");
const newThreadBtn = document.getElementById("newThread");
const threadList = document.getElementById("threadList");

let stickToBottom = true;
let activeToolGroup = null;
let activeToolStatus = null;
let activeAssistantEl = null;
let pendingToolEvents = [];
let thinkingTimer = null;
let hasToolActivity = false;

messagesEl.addEventListener("scroll", () => {
  const threshold = 60;
  const atBottom =
    messagesEl.scrollTop + messagesEl.clientHeight >=
    messagesEl.scrollHeight - threshold;
  stickToBottom = atBottom;
});

const STORAGE_KEY = "react-agent-threads";
const CURRENT_KEY = "react-agent-current-thread";

function loadThreads() {
  const raw = localStorage.getItem(STORAGE_KEY);
  if (!raw) {
    return [];
  }
  try {
    return JSON.parse(raw);
  } catch {
    return [];
  }
}

function saveThreads(threads) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(threads));
}

function setCurrentThread(id) {
  localStorage.setItem(CURRENT_KEY, id);
}

function getCurrentThread() {
  return localStorage.getItem(CURRENT_KEY);
}

function addMessage(role, content) {
  const wrapper = document.createElement("div");
  wrapper.className = `message ${role}`;
  if (role === "assistant") {
    const contentEl = document.createElement("div");
    contentEl.className = "message-content";
    wrapper.appendChild(contentEl);
  }
  renderMessageContent(wrapper, role, content);
  messagesEl.appendChild(wrapper);
  if (stickToBottom) {
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }
  return wrapper;
}

function addToolEvent({ kind, name, detail }) {
  if (kind === "call") {
    hasToolActivity = true;
    showToolStatus(name, detail);
    clearThinking();
  }

  pendingToolEvents.push({ kind, name, detail });

  if (stickToBottom) {
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }
}

function flushToolEvents() {
  if (!pendingToolEvents.length) return;
  const group = ensureToolGroup();
  const count = pendingToolEvents.length;
  const summary = group.wrapper.querySelector(".tool-summary");
  if (summary) {
    summary.textContent = `Tools (${count})`;
  }

  pendingToolEvents.forEach(({ kind, name, detail }) => {
    const row = document.createElement("div");
    row.className = "tool-row";

    const badge = document.createElement("div");
    badge.className = "tool-badge";
    badge.textContent = kind === "result" ? "Result" : "Call";

    const title = document.createElement("div");
    title.className = "tool-title";
    title.textContent = name || "tool";

    row.appendChild(badge);
    row.appendChild(title);

    group.list.appendChild(row);

    if (detail) {
      const pre = document.createElement("pre");
      pre.textContent = detail;
      group.body.appendChild(pre);
    }
  });

  pendingToolEvents = [];
}

function ensureToolGroup() {
  if (activeToolGroup) return activeToolGroup;

  const wrapper = document.createElement("details");
  wrapper.className = "tool-group";

  const summary = document.createElement("summary");
  summary.className = "tool-summary";
  summary.textContent = "Tools";

  const body = document.createElement("div");
  body.className = "tool-body";

  const list = document.createElement("div");
  list.className = "tool-list";

  body.appendChild(list);

  wrapper.appendChild(summary);
  wrapper.appendChild(body);

  const assistantEl = activeAssistantEl;
  if (assistantEl) {
    assistantEl.classList.add("has-tools");
    const contentEl = assistantEl.querySelector(".message-content");
    if (contentEl) {
      assistantEl.insertBefore(wrapper, contentEl);
    } else {
      assistantEl.appendChild(wrapper);
    }
  } else {
    const insertBefore = messagesEl.querySelector(".message.assistant.pending");
    if (insertBefore) {
      messagesEl.insertBefore(wrapper, insertBefore);
    } else {
      messagesEl.appendChild(wrapper);
    }
  }

  activeToolGroup = { wrapper, body, list };
  return activeToolGroup;
}

function showToolStatus(name, detail) {
  if (activeToolStatus) {
    activeToolStatus.remove();
  }
  clearThinking();
  const status = document.createElement("div");
  status.className = "message tool-status";

  const label = document.createElement("div");
  label.className = "tool-status-text";
  label.textContent = `Running ${name || "tool"}…`;

  const dots = document.createElement("span");
  dots.className = "tool-status-dots";

  label.appendChild(dots);
  status.appendChild(label);

  const insertBefore = messagesEl.querySelector(".message.assistant.pending");
  if (insertBefore) {
    messagesEl.insertBefore(status, insertBefore);
  } else {
    messagesEl.appendChild(status);
  }
  activeToolStatus = status;
}

function clearToolStatus() {
  if (activeToolStatus) {
    activeToolStatus.remove();
    activeToolStatus = null;
  }
}

function showThinking() {
  if (activeToolStatus) return;
  if (thinkingTimer) return;
  thinkingTimer = setTimeout(() => {
    if (activeToolStatus || hasToolActivity) return;
    const status = document.createElement("div");
    status.className = "message tool-status";

    const label = document.createElement("div");
    label.className = "tool-status-text";
    label.textContent = "Thinking…";

    const dots = document.createElement("span");
    dots.className = "tool-status-dots";

    label.appendChild(dots);
    status.appendChild(label);

    const insertBefore = messagesEl.querySelector(".message.assistant.pending");
    if (insertBefore) {
      messagesEl.insertBefore(status, insertBefore);
    } else {
      messagesEl.appendChild(status);
    }
    activeToolStatus = status;
  }, 350);
}

function clearThinking() {
  if (thinkingTimer) {
    clearTimeout(thinkingTimer);
    thinkingTimer = null;
  }
}

function renderMessageContent(el, role, content) {
  const target = el.querySelector(".message-content") || el;
  if (role === "assistant" && window.marked && window.DOMPurify) {
    const html = window.marked.parse(content ?? "", { breaks: true });
    target.innerHTML = window.DOMPurify.sanitize(html);
    return;
  }
  target.textContent = content ?? "";
}

async function loadHistory(threadId) {
  messagesEl.innerHTML = "";
  try {
    const res = await fetch(`/api/thread/${threadId}/history`);
    if (res.ok) {
      const data = await res.json();
      data.messages.forEach((msg) => addMessage(msg.role, msg.content));
      messagesEl.scrollTop = messagesEl.scrollHeight;
      stickToBottom = true;
      return;
    }
  } catch {
    // Fallback to local cache
  }
  const threads = loadThreads();
  const thread = threads.find((t) => t.id === threadId);
  if (!thread) return;
  thread.messages.forEach((msg) => addMessage(msg.role, msg.content));
  messagesEl.scrollTop = messagesEl.scrollHeight;
  stickToBottom = true;
}

function updateThreadList(selectedId) {
  const threads = loadThreads();
  threadList.innerHTML = "";
  threads.forEach((thread) => {
    const item = document.createElement("div");
    item.className = `thread-tab${
      thread.id === selectedId ? " active" : ""
    }`;

    const label = document.createElement("button");
    label.className = "thread-label";
    label.textContent = thread.label;
    label.addEventListener("click", () => {
      setCurrentThread(thread.id);
      updateThreadList(thread.id);
      loadHistory(thread.id);
    });

    const remove = document.createElement("button");
    remove.className = "thread-remove";
    remove.type = "button";
    remove.textContent = "×";
    remove.title = "Remove session";
    remove.addEventListener("click", async (event) => {
      event.stopPropagation();
      await removeThread(thread.id);
    });

    item.appendChild(label);
    item.appendChild(remove);
    threadList.appendChild(item);
  });
}

function upsertThread(threadId, label, message) {
  const threads = loadThreads();
  let thread = threads.find((t) => t.id === threadId);
  if (!thread) {
    thread = { id: threadId, label: label || "New Session", messages: [] };
    threads.unshift(thread);
  }
  if (message) {
    thread.messages.push(message);
  }
  if (
    message &&
    message.role === "user" &&
    (!thread.label ||
      thread.label === "New Session" ||
      thread.label.startsWith("Session "))
  ) {
    thread.label = summarizeTitle(message.content);
  }
  saveThreads(threads);
}

async function removeThread(threadId) {
  const res = await fetch(`/api/thread/${threadId}`, { method: "DELETE" });
  if (!res.ok) {
    alert("Failed to remove session.");
    return;
  }
  const threads = loadThreads().filter((t) => t.id !== threadId);
  saveThreads(threads);

  const current = getCurrentThread();
  if (current === threadId) {
    const next = threads[0]?.id || null;
    if (next) {
      setCurrentThread(next);
      loadHistory(next);
    } else {
      setCurrentThread("");
      messagesEl.innerHTML = "";
    }
    updateThreadList(next);
    return;
  }

  updateThreadList(current);
}

async function createThread() {
  const res = await fetch("/api/thread", { method: "POST" });
  const data = await res.json();
  const threadId = data.thread_id;
  upsertThread(threadId, "New Session");
  updateThreadList(threadId);
  setCurrentThread(threadId);
  loadHistory(threadId);
  return threadId;
}

async function sendMessage() {
  const content = messageInput.value.trim();
  if (!content) return;
  messageInput.value = "";

  let threadId = getCurrentThread();
  if (!threadId) {
    threadId = await createThread();
  }

  addMessage("user", content);
  upsertThread(threadId, `Session ${threadId.slice(0, 6)}`, {
    role: "user",
    content,
  });
  updateThreadList(threadId);
  stickToBottom = true;

  const assistantEl = addMessage("assistant", "");
  assistantEl.classList.add("pending");
  activeAssistantEl = assistantEl;
  let assistantText = "";
  activeToolGroup = null;
  pendingToolEvents = [];
  hasToolActivity = false;
  showThinking();

  const res = await fetch("/api/chat/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message: content, thread_id: threadId }),
  });

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop() || "";

    for (const part of parts) {
      const line = part
        .split("\n")
        .find((l) => l.startsWith("data: "));
      if (!line) continue;
      const payload = JSON.parse(line.replace("data: ", ""));

      if (payload.type === "thread") {
        threadId = payload.thread_id;
        setCurrentThread(threadId);
        updateThreadList(threadId);
        continue;
      }

      if (payload.type === "delta") {
        assistantText += payload.content;
        renderMessageContent(assistantEl, "assistant", assistantText);
        if (stickToBottom) {
          messagesEl.scrollTop = messagesEl.scrollHeight;
        }
        continue;
      }

      if (payload.type === "tool_call") {
        const args = payload.args ? JSON.stringify(payload.args, null, 2) : "";
        addToolEvent({
          kind: "call",
          name: payload.tool_name,
          detail: args,
        });
        continue;
      }

      if (payload.type === "tool_result") {
        clearToolStatus();
        const content =
          payload.content && typeof payload.content === "string"
            ? payload.content
            : payload.content
              ? JSON.stringify(payload.content, null, 2)
              : "";
        addToolEvent({
          kind: "result",
          name: payload.tool_name,
          detail: content,
        });
        continue;
      }

      if (payload.type === "done") {
        clearToolStatus();
        break;
      }
    }
  }

  assistantEl.classList.remove("pending");
  flushToolEvents();
  activeToolGroup = null;
  activeAssistantEl = null;
  clearToolStatus();
  clearThinking();
  if (!assistantText) {
    assistantText = "(no response)";
    renderMessageContent(assistantEl, "assistant", assistantText);
  }
  upsertThread(threadId, `Session ${threadId.slice(0, 6)}`, {
    role: "assistant",
    content: assistantText,
  });
}

sendBtn.addEventListener("click", sendMessage);
messageInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    sendMessage();
  }
});

newThreadBtn.addEventListener("click", async () => {
  await createThread();
});

function init() {
  const threads = loadThreads();
  if (threads.length === 0) {
    createThread();
    return;
  }
  const current = getCurrentThread() || threads[0].id;
  setCurrentThread(current);
  loadHistory(current);
  updateThreadList(current);
}

function summarizeTitle(text) {
  const cleaned = (text || "").replace(/\s+/g, " ").trim();
  if (!cleaned) return "New Session";
  if (cleaned.length <= 36) return cleaned;
  return `${cleaned.slice(0, 36)}…`;
}

init();
