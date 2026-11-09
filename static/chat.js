const KEY_NAME = "openrouter-key";
const MAX_UPLOAD = 2 * 1024 * 1024;
const keyField = document.querySelector("#openrouter-key");
const keyStatus = document.querySelector("#key-status");

function storedKey() {
  try {
    return sessionStorage.getItem(KEY_NAME) || "";
  } catch {
    return "";
  }
}

function showKeyStatus() {
  keyStatus.textContent = keyField.value.trim() ? "המפתח מוגדר בלשונית הזו." : "עדיין לא הוגדר מפתח.";
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

const form = document.querySelector("#ask");
if (form) {
  const answer = document.querySelector("#answer");
  const question = form.elements.question;
  const button = form.querySelector("button");
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const prompt = document.createElement("strong");
    const reply = document.createElement("p");
    prompt.textContent = question.value;
    reply.textContent = "מחפש תשובה…";
    answer.replaceChildren(prompt, reply);
    answer.hidden = false;
    const body = new FormData(form);
    body.set("openrouter_key", keyField.value.trim());
    button.disabled = true;
    question.value = "";
    try {
      const response = await fetch(form.action, {method: "POST", body});
      const result = await response.json();
      reply.textContent = result.answer || result.error;
      if (result.sources?.length) {
        const sources = document.createElement("small");
        sources.textContent = "מקורות · " + result.sources.join(" · ");
        answer.append(sources);
      }
      if (result.mode === "local") {
        const mode = document.createElement("small");
        mode.textContent = "תצוגת מקורות ללא מודל";
        answer.append(mode);
      }
    } catch {
      reply.textContent = "הבקשה נכשלה. רעננו את הדף ונסו שוב.";
    } finally {
      button.disabled = false;
      question.focus();
    }
  });
}

const dropZone = document.querySelector("#drop-zone");
if (dropZone) {
  const fileInput = document.querySelector("#upload-file");
  const fileStatus = document.querySelector("#file-status");
  const uploadButton = document.querySelector("#upload-button");
  const carriesFile = (event) => event.dataTransfer?.types?.includes("Files");

  function fileProblem(files) {
    if (files.length !== 1) return "גררו קובץ אחד בכל פעם.";
    if (!/\.(txt|pdf)$/i.test(files[0].name)) return "אפשר להעלות קובצי TXT או PDF בלבד.";
    if (files[0].size > MAX_UPLOAD) return "אפשר להעלות עד 2 MB.";
    if (files[0].size === 0) return "הקובץ ריק.";
    return "";
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
    const files = event.dataTransfer.files;
    const problem = fileProblem(files);
    fileInput.value = "";
    if (problem) {
      fileStatus.textContent = problem;
    } else {
      fileInput.files = files;
      fileStatus.textContent = `הקובץ ${files[0].name} נבדק ומוכן להעלאה. לחצו על ״העלאה״.`;
    }
    fileInput.closest("form").scrollIntoView({behavior: "smooth", block: "center"});
    if (!problem) uploadButton.focus({preventScroll: true});
  });
  fileInput.addEventListener("change", () => {
    fileStatus.textContent = "";
  });
}
