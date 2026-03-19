const PROMPT_COACH_BUTTON_ID = "prompt-coach-trigger";
const PROMPT_COACH_WRAPPER_CLASS = "prompt-coach-wrapper";
const PROMPT_COACH_POPUP_ID = "prompt-coach-popup";
const PROMPT_COACH_API_URL = "http://127.0.0.1:8000/improve";

/**
 * ChatGPT input box selector.
 * The current UI uses #prompt-textarea, so we check that first.
 */
function getPromptInputElement() {
  return document.querySelector("#prompt-textarea");
}

/**
 * Returns the text currently written in the ChatGPT input.
 */
function getPromptText(inputElement) {
  if (!inputElement) {
    return "";
  }

  if (inputElement instanceof HTMLTextAreaElement) {
    return inputElement.value.trim();
  }

  return inputElement.innerText?.trim() ?? inputElement.textContent?.trim() ?? "";
}

/**
 * Replaces all text inside a contenteditable element.
 */
function setContentEditableText(element, nextValue) {
  element.focus();
  element.replaceChildren(document.createTextNode(nextValue));

  const inputEvent = new InputEvent("input", {
    bubbles: true,
    cancelable: true,
    data: nextValue,
    inputType: "insertText"
  });

  element.dispatchEvent(inputEvent);
}

/**
 * Updates the input in a way that also notifies React-style listeners.
 */
function setPromptText(inputElement, nextValue) {
  if (inputElement instanceof HTMLTextAreaElement) {
    const nativeSetter = Object.getOwnPropertyDescriptor(
      window.HTMLTextAreaElement.prototype,
      "value"
    )?.set;

    if (nativeSetter) {
      nativeSetter.call(inputElement, nextValue);
    } else {
      inputElement.value = nextValue;
    }

    inputElement.dispatchEvent(new Event("input", { bubbles: true }));
    return;
  }

  setContentEditableText(inputElement, nextValue);
}

/**
 * Removes the popup if it already exists.
 */
function removePromptCoachPopup() {
  const existingPopup = document.querySelector(`#${PROMPT_COACH_POPUP_ID}`);

  if (existingPopup) {
    existingPopup.remove();
  }
}

/**
 * Calls the local FastAPI server and returns the analysis result.
 */
async function requestPromptImprovement(promptText) {
  const response = await fetch(PROMPT_COACH_API_URL, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      prompt: promptText
    })
  });

  if (!response.ok) {
    throw new Error(`API request failed with status ${response.status}`);
  }

  return response.json();
}

/**
 * Creates the popup shell first, then we fill it with loading/data/error content.
 */
function createPromptCoachPopup(currentPrompt) {
  removePromptCoachPopup();

  const popup = document.createElement("div");
  popup.id = PROMPT_COACH_POPUP_ID;
  popup.className = "prompt-coach-popup";

  popup.innerHTML = `
    <div class="prompt-coach-popup-header">
      <h3>Prompt Coach</h3>
      <button type="button" class="prompt-coach-close-button" aria-label="\uB2EB\uAE30">\u00D7</button>
    </div>
    <div class="prompt-coach-popup-section">
      <p class="prompt-coach-section-title">\uD604\uC7AC \uD504\uB86C\uD504\uD2B8</p>
      <div class="prompt-coach-preview"></div>
    </div>
    <div class="prompt-coach-results"></div>
    <div class="prompt-coach-popup-actions">
      <button type="button" class="prompt-coach-secondary-button" data-action="keep">
        \uC720\uC9C0\uD558\uAE30
      </button>
      <button type="button" class="prompt-coach-primary-button" data-action="apply" disabled>
        \uAC1C\uC120 \uC801\uC6A9
      </button>
    </div>
  `;

  const previewElement = popup.querySelector(".prompt-coach-preview");
  const resultsContainer = popup.querySelector(".prompt-coach-results");
  const closeButton = popup.querySelector(".prompt-coach-close-button");
  const keepButton = popup.querySelector('[data-action="keep"]');
  const applyButton = popup.querySelector('[data-action="apply"]');

  if (previewElement) {
    previewElement.textContent =
      currentPrompt || "\uC785\uB825\uB41C \uD504\uB86C\uD504\uD2B8\uAC00 \uC5C6\uC2B5\uB2C8\uB2E4.";
  }

  closeButton?.addEventListener("click", () => {
    removePromptCoachPopup();
  });

  keepButton?.addEventListener("click", () => {
    removePromptCoachPopup();
  });

  document.body.appendChild(popup);

  return {
    popup,
    resultsContainer,
    applyButton
  };
}

/**
 * Shows a simple loading state while the API request is running.
 */
function renderLoadingState(resultsContainer) {
  if (!resultsContainer) {
    return;
  }

  resultsContainer.innerHTML = `
    <div class="prompt-coach-popup-section">
      <p class="prompt-coach-section-title">\uBD84\uC11D \uACB0\uACFC</p>
      <div class="prompt-coach-status">
        \uD504\uB86C\uD504\uD2B8\uB97C \uBD84\uC11D \uC911\uC785\uB2C8\uB2E4...
      </div>
    </div>
  `;
}

/**
 * Shows an error message when the API call fails.
 */
function renderErrorState(resultsContainer, errorMessage) {
  if (!resultsContainer) {
    return;
  }

  resultsContainer.innerHTML = `
    <div class="prompt-coach-popup-section">
      <p class="prompt-coach-section-title">\uC624\uB958</p>
      <div class="prompt-coach-error-box">${errorMessage}</div>
    </div>
  `;
}

/**
 * Renders the issues returned by the API.
 */
function renderIssues(issueListElement, issues) {
  issues.forEach((issue) => {
    const issueItem = document.createElement("li");
    issueItem.className = "prompt-coach-issue-item";

    const issueTitle = document.createElement("strong");
    issueTitle.textContent = issue.type;

    const issueDescription = document.createElement("p");
    issueDescription.textContent = issue.description;

    issueItem.appendChild(issueTitle);
    issueItem.appendChild(issueDescription);
    issueListElement.appendChild(issueItem);
  });
}

/**
 * Shows the analysis result inside the popup.
 */
function renderAnalysisState(resultsContainer, analysisResult) {
  if (!resultsContainer) {
    return;
  }

  resultsContainer.innerHTML = `
    <div class="prompt-coach-popup-section">
      <p class="prompt-coach-section-title">\uBB38\uC81C\uC810</p>
      <ul class="prompt-coach-issue-list"></ul>
    </div>
    <div class="prompt-coach-popup-section">
      <p class="prompt-coach-section-title">\uAC1C\uC120\uB41C \uD504\uB86C\uD504\uD2B8</p>
      <div class="prompt-coach-improved-prompt"></div>
    </div>
  `;

  const issueListElement = resultsContainer.querySelector(".prompt-coach-issue-list");
  const improvedPromptElement = resultsContainer.querySelector(
    ".prompt-coach-improved-prompt"
  );

  if (issueListElement) {
    renderIssues(issueListElement, analysisResult.issues || []);
  }

  if (improvedPromptElement) {
    improvedPromptElement.textContent = analysisResult.improved_prompt || "";
  }
}

/**
 * Handles the full request flow: read prompt, show loading, call API, then render result.
 */
async function handlePromptCoachClick(inputElement) {
  const promptText = getPromptText(inputElement);
  console.log("[Prompt Coach] Current prompt:", promptText);

  const popupParts = createPromptCoachPopup(promptText);
  renderLoadingState(popupParts.resultsContainer);

  try {
    const analysisResult = await requestPromptImprovement(promptText);
    renderAnalysisState(popupParts.resultsContainer, analysisResult);

    if (popupParts.applyButton) {
      popupParts.applyButton.disabled = false;
      popupParts.applyButton.addEventListener(
        "click",
        () => {
          setPromptText(inputElement, analysisResult.improved_prompt || "");
          inputElement.focus();
          removePromptCoachPopup();
        },
        { once: true }
      );
    }
  } catch (error) {
    console.error("[Prompt Coach] API request failed:", error);

    renderErrorState(
      popupParts.resultsContainer,
      "\uBC31\uC5D4\uB4DC \uC11C\uBC84\uC5D0 \uC5F0\uACB0\uD558\uC9C0 \uBABB\uD588\uC2B5\uB2C8\uB2E4. FastAPI \uC11C\uBC84\uAC00 \uC2E4\uD589 \uC911\uC778\uC9C0 \uD655\uC778\uD574\uC8FC\uC138\uC694."
    );
  }
}

/**
 * Adds the Prompt Coach button next to the ChatGPT input box.
 * If the button already exists, we do nothing.
 */
function injectPromptCoachButton() {
  const inputElement = getPromptInputElement();

  if (!inputElement) {
    return;
  }

  const inputWrapper = inputElement.parentElement;

  if (!inputWrapper) {
    return;
  }

  // Prevent duplicate button creation when the page re-renders.
  if (inputWrapper.querySelector(`#${PROMPT_COACH_BUTTON_ID}`)) {
    return;
  }

  inputWrapper.classList.add(PROMPT_COACH_WRAPPER_CLASS);

  const button = document.createElement("button");
  button.id = PROMPT_COACH_BUTTON_ID;
  button.type = "button";
  button.className = "prompt-coach-button";
  button.textContent = "\u2728";
  button.title = "Prompt Coach";
  button.setAttribute("aria-label", "Prompt Coach");

  button.addEventListener("click", () => {
    handlePromptCoachClick(inputElement);
  });

  inputWrapper.appendChild(button);
}

/**
 * ChatGPT updates the page dynamically, so we observe DOM changes
 * and try to inject the button whenever the input box appears again.
 */
function startPromptCoach() {
  injectPromptCoachButton();

  const observer = new MutationObserver(() => {
    injectPromptCoachButton();
  });

  observer.observe(document.body, {
    childList: true,
    subtree: true
  });
}

startPromptCoach();
