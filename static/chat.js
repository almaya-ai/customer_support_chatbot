const KEY_NAME = "openrouter-key";
const MAX_UPLOAD = 2 * 1024 * 1024;
const keyField = document.querySelector("#openrouter-key");
const keyStatus = document.querySelector("#key-status");
const keyButton = document.querySelector("#key-button");
const keyBanner = document.querySelector("#key-banner");

function storedKey() {
  try {
    return sessionStorage.getItem(KEY_NAME) || "";
  } catch {
    return "";
  }
}

function showKeyStatus() {
  const ready = Boolean(keyField.value.trim());
  keyStatus.textContent = ready ? "המפתח מוגדר בלשונית הזו." : "עדיין לא הוגדר מפתח.";
  if (keyButton) keyButton.toggleAttribute("data-ready", ready);
  if (keyBanner) keyBanner.hidden = ready;
}

if (keyField) {
  keyField.value = storedKey();
  showKeyStatus();
  keyField.addEventListener("input", () => {
    try {
      sessionStorage.setItem(KEY_NAME, keyField.value.trim());
    } catch {
      // Without storage the key still works until the page reloads.
    }
    showKeyStatus();
  });
}

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text) node.textContent = text;
  return node;
}

const form = document.querySelector("#ask");
if (form) {
  const STORAGE_KEY = `chat:${document.body.dataset.user}`;
  const MAX_STORED = 30;
  const HISTORY_EXCHANGES = 6;
  const welcome = document.querySelector("#welcome");
  const answer = document.querySelector("#answer");
  const scroller = document.querySelector(".conversation");
  const newChat = document.querySelector("#new-chat");
  const question = form.elements.question;
  const send = document.querySelector("#send");
  let exchanges = loadExchanges();

  function loadExchanges() {
    try {
      const stored = JSON.parse(sessionStorage.getItem(STORAGE_KEY) || "[]");
      return Array.isArray(stored) ? stored : [];
    } catch {
      return [];
    }
  }

  function saveExchanges() {
    try {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(exchanges.slice(-MAX_STORED)));
    } catch {
      // Without storage the conversation still works until the page reloads.
    }
  }

  function clearStoredChats() {
    try {
      for (const name of Object.keys(sessionStorage)) {
        if (name.startsWith("chat:")) sessionStorage.removeItem(name);
      }
    } catch {
      // Nothing was stored.
    }
  }

  function showState() {
    const started = exchanges.length > 0;
    answer.hidden = !started;
    welcome.hidden = started;
    newChat.hidden = !started;
  }

  function scrollToEnd() {
    scroller.scrollTop = scroller.scrollHeight;
  }

  function fillReply(reply, result) {
    const text = element("p", "", result.answer || result.error);
    reply.replaceChildren(text);
    reply.classList.remove("waiting");
    if (result.sources?.length) {
      const sources = element("div", "sources", "מקורות");
      for (const source of result.sources) {
        const chip = element("bdi", "source", source);
        chip.dir = "auto";
        sources.append(chip);
      }
      reply.append(sources);
    }
    if (result.quotes?.length) {
      const quotes = element("details", "quotes");
      quotes.append(element("summary", "", "הצגת הטקסט המקורי"));
      for (const quote of result.quotes) {
        const row = element("blockquote", "", quote.text);
        row.dir = "auto";
        if (quote.date) row.append(element("span", "quote-date", `${quote.source}, ${quote.date}`));
        quotes.append(row);
      }
      reply.append(quotes);
    }
    if (result.mode === "local") reply.append(element("small", "", "תצוגת מקורות ללא מודל"));
    if (result.checked?.length) {
      reply.append(element("small", "checked", "הסוכן בדק: " + result.checked.join(", ")));
    }
  }

  function addExchange(text) {
    const reply = element("div", "reply");
    answer.append(element("p", "bubble", text), reply);
    return reply;
  }

  function historyForModel() {
    return exchanges.filter((item) => item.result?.answer).slice(-HISTORY_EXCHANGES).flatMap((item) => [
      {role: "user", text: item.question},
      {role: "assistant", text: item.result.answer},
    ]);
  }

  for (const item of exchanges) fillReply(addExchange(item.question), item.result);
  showState();
  scrollToEnd();

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const asked = question.value;
    const body = new FormData(form);
    body.set("openrouter_key", keyField.value.trim());
    body.set("history", JSON.stringify(historyForModel()));
    const reply = addExchange(asked);
    reply.classList.add("waiting");
    reply.append(element("p", "", "מחפש תשובה…"));
    answer.hidden = false;
    welcome.hidden = true;
    newChat.hidden = false;
    scrollToEnd();
    send.disabled = true;
    question.value = "";
    let result;
    try {
      const response = await fetch(form.action, {method: "POST", body});
      result = await response.json();
    } catch {
      result = {error: "הבקשה נכשלה. רעננו את הדף ונסו שוב."};
    }
    fillReply(reply, result);
    exchanges.push({question: asked, result});
    saveExchanges();
    send.disabled = false;
    question.focus();
    scrollToEnd();
  });

  newChat.addEventListener("click", () => {
    exchanges = [];
    saveExchanges();
    answer.replaceChildren();
    showState();
    question.focus();
  });

  document.querySelector(".tools form").addEventListener("submit", clearStoredChats);

  for (const suggestion of document.querySelectorAll(".suggestion")) {
    suggestion.addEventListener("click", () => {
      question.value = suggestion.textContent;
      form.requestSubmit();
    });
  }
}

for (const deleteForm of document.querySelectorAll(".delete-document")) {
  deleteForm.addEventListener("submit", (event) => {
    if (!window.confirm(`למחוק את ${deleteForm.dataset.name}? אי אפשר לבטל את המחיקה.`)) event.preventDefault();
  });
}

const dropZone = document.querySelector("#drop-zone");
if (dropZone) {
  const fileInput = document.querySelector("#upload-file");
  const fileStatus = document.querySelector("#file-status");
  const uploadButton = document.querySelector("#upload-button");
  const pending = document.querySelector("#pending");
  const carriesFile = (event) => event.dataTransfer?.types?.includes("Files");

  function fileProblem(files) {
    if (files.length !== 1) return "גררו קובץ אחד בכל פעם.";
    if (!/\.(txt|pdf)$/i.test(files[0].name)) return "אפשר להעלות קובצי TXT או PDF בלבד.";
    if (files[0].size > MAX_UPLOAD) return "אפשר להעלות עד 2 MB.";
    if (files[0].size === 0) return "הקובץ ריק.";
    return "";
  }

  function offerFile(files) {
    const problem = fileProblem(files);
    const name = files[0]?.name;
    if (problem) {
      fileInput.value = "";
    } else if (fileInput.files !== files) {
      fileInput.files = files;
    }
    fileStatus.textContent = problem || `הקובץ ${name} נבדק ומוכן להעלאה.`;
    uploadButton.hidden = Boolean(problem);
    pending.hidden = false;
    if (!problem) uploadButton.focus();
  }

  function clearFile() {
    fileInput.value = "";
    pending.hidden = true;
  }

  window.addEventListener("dragenter", (event) => {
    if (!carriesFile(event)) return;
    event.preventDefault();
    dropZone.hidden = false;
  });
  window.addEventListener("dragover", (event) => {
    if (!carriesFile(event)) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = "copy";
  });
  dropZone.addEventListener("dragleave", (event) => {
    if (event.target === dropZone) dropZone.hidden = true;
  });
  window.addEventListener("drop", (event) => {
    if (!carriesFile(event)) return;
    event.preventDefault();
    dropZone.hidden = true;
    offerFile(event.dataTransfer.files);
  });

  fileInput.addEventListener("change", () => {
    if (fileInput.files.length) offerFile(fileInput.files);
  });
  document.querySelector("#cancel-file").addEventListener("click", clearFile);
  document.querySelector("#attach").addEventListener("click", () => fileInput.click());
  document.querySelector("#panel-attach").addEventListener("click", () => {
    document.querySelector("#documents-panel").hidePopover();
    fileInput.click();
  });
}

const instructions = document.querySelector("#instructions");
if (instructions) {
  const VIEW_NAME = "instructions-view";
  const preview = document.querySelector("#instructions-preview");
  const renderedButton = document.querySelector("#view-rendered");
  const codeButton = document.querySelector("#view-code");

  function setView(view) {
    const rendered = view === "rendered";
    if (rendered) renderMarkdown(instructions.value, preview);
    instructions.hidden = rendered;
    preview.hidden = !rendered;
    renderedButton.setAttribute("aria-pressed", String(rendered));
    codeButton.setAttribute("aria-pressed", String(!rendered));
    try {
      sessionStorage.setItem(VIEW_NAME, view);
    } catch {
      // The choice simply resets on the next page load.
    }
  }

  function storedView() {
    try {
      return sessionStorage.getItem(VIEW_NAME) || "rendered";
    } catch {
      return "rendered";
    }
  }

  renderedButton.addEventListener("click", () => setView("rendered"));
  codeButton.addEventListener("click", () => setView("code"));
  setView(storedView());
}
