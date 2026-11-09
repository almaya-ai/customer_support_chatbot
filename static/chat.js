const KEY_NAME = "openrouter-key";
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

const form = document.querySelector("#ask");
if (form) {
  const conversation = document.querySelector("#conversation");
  const question = form.elements.question;
  const button = form.querySelector("button");
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const row = document.createElement("li");
    const prompt = document.createElement("strong");
    const reply = document.createElement("p");
    prompt.textContent = question.value;
    reply.textContent = "מחפש תשובה…";
    row.append(prompt, reply);
    conversation.append(row);
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
        row.append(sources);
      }
      if (result.mode === "local") {
        const mode = document.createElement("small");
        mode.textContent = "תצוגת מקורות ללא מודל";
        row.append(mode);
      }
    } catch {
      reply.textContent = "הבקשה נכשלה. רעננו את הדף ונסו שוב.";
    } finally {
      button.disabled = false;
      question.focus();
    }
  });
}
