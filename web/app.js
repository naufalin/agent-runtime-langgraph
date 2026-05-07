const messagesEl = document.getElementById("messages");
const messageInput = document.getElementById("messageInput");
const sendBtn = document.getElementById("sendBtn");
const newThreadBtn = document.getElementById("newThread");
const threadList = document.getElementById("threadList");
const layoutEl = document.querySelector(".layout");
const sidebarResize = document.getElementById("sidebarResize");

let stickToBottom = true;
let activeToolGroup = null;
let activeToolStatus = null;
let activeAssistantEl = null;
let pendingToolEvents = [];
let thinkingTimer = null;
let hasToolActivity = false;
let editingThreadId = null;

messagesEl.addEventListener("scroll", () => {
  const threshold = 60;
  const atBottom =
    messagesEl.scrollTop + messagesEl.clientHeight >=
    messagesEl.scrollHeight - threshold;
  stickToBottom = atBottom;
});

const STORAGE_KEY = "react-agent-threads";
const CURRENT_KEY = "react-agent-current-thread";
const SIDEBAR_WIDTH_KEY = "react-agent-sidebar-width";
const SIDEBAR_MIN_WIDTH = 220;
const SIDEBAR_MAX_WIDTH = 420;
const SIDEBAR_MOBILE_BREAKPOINT = 760;

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

function clampSidebarWidth(width) {
  return Math.min(SIDEBAR_MAX_WIDTH, Math.max(SIDEBAR_MIN_WIDTH, width));
}

function isSidebarResizeEnabled() {
  return window.innerWidth > SIDEBAR_MOBILE_BREAKPOINT;
}

function setSidebarWidth(width) {
  if (!layoutEl) return;
  const nextWidth = clampSidebarWidth(width);
  layoutEl.style.setProperty("--sidebar-width", `${nextWidth}px`);
  if (sidebarResize) {
    sidebarResize.setAttribute("aria-valuenow", String(nextWidth));
  }
  localStorage.setItem(SIDEBAR_WIDTH_KEY, String(nextWidth));
  requestAnimationFrame(updateOverflowingThreadLabels);
}

function loadSidebarWidth() {
  const stored = Number(localStorage.getItem(SIDEBAR_WIDTH_KEY));
  if (Number.isFinite(stored) && stored > 0) {
    setSidebarWidth(stored);
  }
}

function initSidebarResize() {
  if (!layoutEl || !sidebarResize) return;

  sidebarResize.setAttribute("aria-valuemin", String(SIDEBAR_MIN_WIDTH));
  sidebarResize.setAttribute("aria-valuemax", String(SIDEBAR_MAX_WIDTH));
  loadSidebarWidth();

  let dragStartX = 0;
  let dragStartWidth = 0;

  sidebarResize.addEventListener("pointerdown", (event) => {
    if (!isSidebarResizeEnabled()) return;
    event.preventDefault();
    dragStartX = event.clientX;
    dragStartWidth = Number(
      getComputedStyle(layoutEl)
        .getPropertyValue("--sidebar-width")
        .replace("px", ""),
    );
    if (!Number.isFinite(dragStartWidth) || dragStartWidth <= 0) {
      dragStartWidth = SIDEBAR_MIN_WIDTH;
    }
    sidebarResize.classList.add("dragging");
    sidebarResize.setPointerCapture(event.pointerId);
  });

  sidebarResize.addEventListener("pointermove", (event) => {
    if (!sidebarResize.classList.contains("dragging")) return;
    setSidebarWidth(dragStartWidth + event.clientX - dragStartX);
  });

  const endDrag = (event) => {
    if (!sidebarResize.classList.contains("dragging")) return;
    sidebarResize.classList.remove("dragging");
    if (sidebarResize.hasPointerCapture(event.pointerId)) {
      sidebarResize.releasePointerCapture(event.pointerId);
    }
  };

  sidebarResize.addEventListener("pointerup", endDrag);
  sidebarResize.addEventListener("pointercancel", endDrag);

  sidebarResize.addEventListener("keydown", (event) => {
    if (!isSidebarResizeEnabled()) return;
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
    event.preventDefault();
    const step = event.shiftKey ? 48 : 16;
    const direction = event.key === "ArrowRight" ? 1 : -1;
    const current = Number(
      getComputedStyle(layoutEl)
        .getPropertyValue("--sidebar-width")
        .replace("px", ""),
    );
    setSidebarWidth(
      (Number.isFinite(current) ? current : SIDEBAR_MIN_WIDTH) +
        step * direction,
    );
  });

  window.addEventListener("resize", () => {
    sidebarResize.classList.remove("dragging");
    updateOverflowingThreadLabels();
  });
}

function updateOverflowingThreadLabels() {
  document.querySelectorAll(".thread-label").forEach((label) => {
    const text = label.querySelector(".thread-label-text");
    if (!text) return;
    label.classList.remove("is-overflowing");
    text.style.removeProperty("--marquee-distance");
    const overflow = text.scrollWidth > label.clientWidth;
    if (overflow) {
      label.classList.add("is-overflowing");
      text.style.setProperty(
        "--marquee-distance",
        `${Math.max(0, text.scrollWidth - label.clientWidth)}px`,
      );
    }
  });
}

function updateCachedThread(threadId, updates) {
  const threads = loadThreads();
  let thread = threads.find((t) => t.id === threadId);
  if (!thread) {
    thread = {
      id: threadId,
      label: updates.label || "New Session",
      titleSource: updates.titleSource || "auto",
      messages: [],
    };
    threads.unshift(thread);
  }
  Object.assign(thread, updates);
  saveThreads(threads);
  return thread;
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
  appendToolEvents(group, pendingToolEvents);
  pendingToolEvents = [];
}

function appendToolEvents(group, events) {
  const count = events.length;
  const summary = group.wrapper.querySelector(".tool-summary");
  if (summary) {
    summary.textContent = `Tools (${count})`;
  }

  events.forEach(({ kind, name, detail }) => {
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
}

function createToolGroup() {
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

  return { wrapper, body, list };
}

function ensureToolGroup() {
  if (activeToolGroup) return activeToolGroup;

  const group = createToolGroup();
  const wrapper = group.wrapper;

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

  activeToolGroup = group;
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

function payloadToToolEvent(payload) {
  if (payload.type === "tool_call") {
    return {
      kind: "call",
      name: payload.tool_name,
      detail: payload.args ? JSON.stringify(payload.args, null, 2) : "",
    };
  }
  if (payload.type === "tool_result") {
    const content =
      payload.content && typeof payload.content === "string"
        ? payload.content
        : payload.content
          ? JSON.stringify(payload.content, null, 2)
          : "";
    return {
      kind: "result",
      name: payload.tool_name,
      detail: content,
    };
  }
  return null;
}

function legacyToolMessageToEvent(message) {
  if (message.role !== "tool") return null;
  return {
    kind: "result",
    name: message.tool_name || "tool",
    detail: message.content || "",
  };
}

function attachHistoryToolEvents(assistantEl, events) {
  if (!events.length) return;
  const group = createToolGroup();
  appendToolEvents(group, events);

  if (assistantEl) {
    assistantEl.classList.add("has-tools");
    const contentEl = assistantEl.querySelector(".message-content");
    if (contentEl) {
      assistantEl.insertBefore(group.wrapper, contentEl);
      return;
    }
    assistantEl.appendChild(group.wrapper);
    return;
  }

  messagesEl.appendChild(group.wrapper);
}

function renderHistoryMessages(messages) {
  const pendingToolEventsForAssistant = [];

  messages.forEach((msg) => {
    const payloadEvents = (msg.payloads || [])
      .map(payloadToToolEvent)
      .filter(Boolean);
    const legacyToolEvent = legacyToolMessageToEvent(msg);

    if (payloadEvents.length) {
      pendingToolEventsForAssistant.push(...payloadEvents);
    } else if (legacyToolEvent) {
      pendingToolEventsForAssistant.push(legacyToolEvent);
    }

    if (msg.role === "assistant") {
      if (!msg.content) return;
      const assistantEl = addMessage("assistant", msg.content);
      attachHistoryToolEvents(
        assistantEl,
        pendingToolEventsForAssistant.splice(0),
      );
      return;
    }

    if (msg.role === "tool") return;
    if (!msg.content) return;
    addMessage(msg.role, msg.content);
  });

  attachHistoryToolEvents(null, pendingToolEventsForAssistant);
}

async function loadHistory(threadId) {
  messagesEl.innerHTML = "";
  activeToolGroup = null;
  activeToolStatus = null;
  activeAssistantEl = null;
  pendingToolEvents = [];
  try {
    const res = await fetch(`/api/thread/${threadId}/history`);
    if (res.ok) {
      const data = await res.json();
      if (data.title) {
        updateCachedThread(threadId, {
          label: data.title,
          titleSource: data.title_source || "auto",
        });
        updateThreadList(threadId);
      }
      renderHistoryMessages(data.messages);
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
  renderHistoryMessages(thread.messages);
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

    const label = createThreadLabel(thread);

    const edit = document.createElement("button");
    edit.className = "thread-edit";
    edit.type = "button";
    edit.textContent = "Edit";
    edit.title = "Rename session";
    edit.addEventListener("click", (event) => {
      event.stopPropagation();
      editingThreadId = thread.id;
      updateThreadList(selectedId);
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
    item.appendChild(edit);
    item.appendChild(remove);
    threadList.appendChild(item);
  });
  requestAnimationFrame(updateOverflowingThreadLabels);
}

function createThreadLabel(thread) {
  if (editingThreadId === thread.id) {
    const input = document.createElement("input");
    input.className = "thread-title-input";
    input.value = thread.label || "New Session";
    input.setAttribute("aria-label", "Session title");

    let committed = false;
    const finish = async (save) => {
      if (committed) return;
      committed = true;
      const nextTitle = input.value.trim();
      editingThreadId = null;
      if (save && nextTitle && nextTitle !== thread.label) {
        await renameThread(thread.id, nextTitle);
        return;
      }
      updateThreadList(getCurrentThread());
    };

    input.addEventListener("click", (event) => event.stopPropagation());
    input.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        finish(true);
      }
      if (event.key === "Escape") {
        event.preventDefault();
        finish(false);
      }
    });
    input.addEventListener("blur", () => finish(true));
    setTimeout(() => {
      input.focus();
      input.select();
    }, 0);
    return input;
  }

  const label = document.createElement("button");
  label.className = "thread-label";
  label.title = thread.label || "New Session";
  const text = document.createElement("span");
  text.className = "thread-label-text";
  text.textContent = thread.label || "New Session";
  label.appendChild(text);
  label.addEventListener("click", () => {
    setCurrentThread(thread.id);
    updateThreadList(thread.id);
    loadHistory(thread.id);
  });
  label.addEventListener("dblclick", (event) => {
    event.preventDefault();
    editingThreadId = thread.id;
    updateThreadList(getCurrentThread());
  });
  return label;
}

function upsertThread(threadId, label, message, titleSource = "auto") {
  const threads = loadThreads();
  let thread = threads.find((t) => t.id === threadId);
  if (!thread) {
    thread = {
      id: threadId,
      label: label || "New Session",
      titleSource,
      messages: [],
    };
    threads.unshift(thread);
  } else if (!thread.titleSource) {
    thread.titleSource = titleSource;
  }
  if (message) {
    thread.messages.push(message);
  }
  saveThreads(threads);
}

function applyThreadTitle(threadId, title, titleSource = "auto") {
  updateCachedThread(threadId, {
    label: title || "New Session",
    titleSource,
  });
  updateThreadList(getCurrentThread());
}

async function renameThread(threadId, title) {
  const previous = loadThreads().find((thread) => thread.id === threadId);
  applyThreadTitle(threadId, title, "manual");
  try {
    const res = await fetch(`/api/thread/${threadId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title }),
    });
    if (!res.ok) throw new Error("Rename failed");
    const data = await res.json();
    applyThreadTitle(threadId, data.title, data.title_source || "manual");
  } catch {
    if (previous) {
      applyThreadTitle(threadId, previous.label, previous.titleSource || "auto");
    }
    alert("Failed to rename session.");
  }
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
  upsertThread(
    threadId,
    data.title || "New Session",
    null,
    data.title_source || "auto",
  );
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
        upsertThread(threadId, "New Session");
        updateThreadList(threadId);
        continue;
      }

      if (payload.type === "title") {
        applyThreadTitle(threadId, payload.title, payload.title_source || "auto");
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
  initSidebarResize();
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

init();
