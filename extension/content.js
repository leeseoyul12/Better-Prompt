const BETTER_PROMPT_BUTTON_ID = "better-prompt-trigger";
const BETTER_PROMPT_WRAPPER_CLASS = "better-prompt-wrapper";
const BETTER_PROMPT_POPUP_ID = "better-prompt-popup";
const BETTER_PROMPT_API_URL = "http://127.0.0.1:8000/improve";

function getPromptInputElement() {
  return document.querySelector("#prompt-textarea");
}

function getPromptText(inputElement) {
  if (!inputElement) {
    return "";
  }

  if (inputElement instanceof HTMLTextAreaElement) {
    return inputElement.value.trim();
  }

  return inputElement.innerText?.trim() ?? inputElement.textContent?.trim() ?? "";
}

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

function removeBetterPromptPopup() {
  const existingPopup = document.querySelector(`#${BETTER_PROMPT_POPUP_ID}`);

  if (existingPopup) {
    existingPopup.remove();
  }
}

async function requestPromptImprovement(promptText) {
  const response = await fetch(BETTER_PROMPT_API_URL, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      prompt: promptText
    })
  });

  if (!response.ok) {
    let detail = `Request failed with status ${response.status}`;

    try {
      const errorData = await response.json();
      if (typeof errorData?.detail === "string" && errorData.detail.trim()) {
        detail = errorData.detail;
      }
    } catch (jsonError) {
      console.debug("[Better Prompt] Error response parsing failed:", jsonError);
    }

    throw new Error(detail);
  }

  return response.json();
}

function createBetterPromptPopup(currentPrompt) {
  removeBetterPromptPopup();

  const popup = document.createElement("div");
  popup.id = BETTER_PROMPT_POPUP_ID;
  popup.className = "better-prompt-popup";

  popup.innerHTML = `
    <div class="better-prompt-popup-header">
      <h3>Better Prompt</h3>
      <button type="button" class="better-prompt-close-button" aria-label="\uB2EB\uAE30">\u2715</button>
    </div>
    <div class="better-prompt-popup-section">
      <p class="better-prompt-section-title">\uD604\uC7AC \uD504\uB86C\uD504\uD2B8</p>
      <div class="better-prompt-preview"></div>
    </div>
    <div class="better-prompt-results"></div>
    <div class="better-prompt-popup-actions">
      <button type="button" class="better-prompt-secondary-button" data-action="keep">
        \uC720\uC9C0\uD558\uAE30
      </button>
      <button type="button" class="better-prompt-primary-button" data-action="apply" disabled>
        \uAC1C\uC120 \uC801\uC6A9
      </button>
    </div>
  `;

  const previewElement = popup.querySelector(".better-prompt-preview");
  const resultsContainer = popup.querySelector(".better-prompt-results");
  const closeButton = popup.querySelector(".better-prompt-close-button");
  const keepButton = popup.querySelector('[data-action="keep"]');
  const applyButton = popup.querySelector('[data-action="apply"]');

  if (previewElement) {
    previewElement.textContent =
      currentPrompt || "\uC785\uB825\uB41C \uD504\uB86C\uD504\uD2B8\uAC00 \uC5C6\uC2B5\uB2C8\uB2E4.";
  }

  closeButton?.addEventListener("click", () => {
    removeBetterPromptPopup();
  });

  keepButton?.addEventListener("click", () => {
    removeBetterPromptPopup();
  });

  document.body.appendChild(popup);

  return {
    popup,
    resultsContainer,
    applyButton
  };
}

function renderLoadingState(resultsContainer) {
  if (!resultsContainer) {
    return;
  }

  resultsContainer.innerHTML = `
    <div class="better-prompt-popup-section">
      <p class="better-prompt-section-title">\uBD84\uC11D \uACB0\uACFC</p>
      <div class="better-prompt-status">\uD504\uB86C\uD504\uD2B8\uB97C \uBD84\uC11D\uD558\uACE0 \uC788\uC2B5\uB2C8\uB2E4...</div>
    </div>
  `;
}

function renderErrorState(resultsContainer, message) {
  if (!resultsContainer) {
    return;
  }

  resultsContainer.innerHTML = `
    <div class="better-prompt-popup-section">
      <p class="better-prompt-section-title">\uC624\uB958 \uC548\uB0B4</p>
      <div class="better-prompt-error-box">${message}</div>
    </div>
  `;
}

function renderNoticeState(resultsContainer, message) {
  if (!resultsContainer) {
    return;
  }

  resultsContainer.innerHTML = `
    <div class="better-prompt-popup-section">
      <p class="better-prompt-section-title">\uC548\uB0B4</p>
      <div class="better-prompt-status">${message}</div>
    </div>
  `;
}

function renderIssues(issueListElement, issues) {
  issues.forEach((issue) => {
    const issueItem = document.createElement("li");
    issueItem.className = "better-prompt-issue-item";

    const issueTitle = document.createElement("strong");
    issueTitle.textContent = issue.type;

    const issueDescription = document.createElement("p");
    issueDescription.textContent = issue.description;

    issueItem.appendChild(issueTitle);
    issueItem.appendChild(issueDescription);
    issueListElement.appendChild(issueItem);
  });
}

function renderNoIssuesMessage(resultsContainer) {
  resultsContainer.innerHTML = `
    <div class="better-prompt-popup-section">
      <p class="better-prompt-section-title">\uBD84\uC11D \uACB0\uACFC</p>
      <div class="better-prompt-status">\uCDA9\uBD84\uD788 \uC88B\uC740 \uD504\uB86C\uD504\uD2B8\uC785\uB2C8\uB2E4.</div>
    </div>
    <div class="better-prompt-popup-section">
      <p class="better-prompt-section-title">\uCD94\uCC9C \uD504\uB86C\uD504\uD2B8</p>
      <div class="better-prompt-improved-prompt"></div>
    </div>
  `;
}

function renderAnalysisState(resultsContainer, analysisResult) {
  if (!resultsContainer) {
    return;
  }

  const issues = Array.isArray(analysisResult?.issues) ? analysisResult.issues : [];

  if (issues.length === 0) {
    renderNoIssuesMessage(resultsContainer);

    const improvedPromptElement = resultsContainer.querySelector(
      ".better-prompt-improved-prompt"
    );

    if (improvedPromptElement) {
      improvedPromptElement.textContent = analysisResult?.improved_prompt || "";
    }

    return;
  }

  resultsContainer.innerHTML = `
    <div class="better-prompt-popup-section">
      <p class="better-prompt-section-title">\uBB38\uC81C\uC810</p>
      <ul class="better-prompt-issue-list"></ul>
    </div>
    <div class="better-prompt-popup-section">
      <p class="better-prompt-section-title">\uAC1C\uC120 \uD504\uB86C\uD504\uD2B8</p>
      <div class="better-prompt-improved-prompt"></div>
    </div>
  `;

  const issueListElement = resultsContainer.querySelector(".better-prompt-issue-list");
  const improvedPromptElement = resultsContainer.querySelector(
    ".better-prompt-improved-prompt"
  );

  if (issueListElement) {
    renderIssues(issueListElement, issues);
  }

  if (improvedPromptElement) {
    improvedPromptElement.textContent = analysisResult?.improved_prompt || "";
  }
}

async function handleBetterPromptClick(inputElement) {
  const promptText = getPromptText(inputElement);
  console.log("[Better Prompt] Current prompt:", promptText);

  const popupParts = createBetterPromptPopup(promptText);
  if (!promptText) {
    renderNoticeState(
      popupParts.resultsContainer,
      "\uD504\uB86C\uD504\uD2B8\uB97C \uBA3C\uC800 \uC785\uB825\uD574 \uC8FC\uC138\uC694."
    );
    return;
  }

  renderLoadingState(popupParts.resultsContainer);

  try {
    const analysisResult = await requestPromptImprovement(promptText);
    renderAnalysisState(popupParts.resultsContainer, analysisResult);

    if (popupParts.applyButton) {
      popupParts.applyButton.disabled = false;
      popupParts.applyButton.addEventListener(
        "click",
        () => {
          const improvedPrompt = analysisResult?.improved_prompt || "";
          setPromptText(inputElement, improvedPrompt);
          inputElement.focus();
          removeBetterPromptPopup();
        },
        { once: true }
      );
    }
  } catch (error) {
    console.error("[Better Prompt] Failed to improve prompt:", error);
    const message =
      error instanceof Error && error.message
        ? error.message
        : "\uBC31\uC5D4\uB4DC \uC11C\uBC84\uC5D0 \uC5F0\uACB0\uD560 \uC218 \uC5C6\uC2B5\uB2C8\uB2E4.";
    renderErrorState(popupParts.resultsContainer, message);
  }
}

function injectBetterPromptButton() {
  const inputElement = getPromptInputElement();

  if (!inputElement) {
    return;
  }

  const inputWrapper = inputElement.parentElement;

  if (!inputWrapper) {
    return;
  }

  if (inputWrapper.querySelector(`#${BETTER_PROMPT_BUTTON_ID}`)) {
    return;
  }

  inputWrapper.classList.add(BETTER_PROMPT_WRAPPER_CLASS);

  const button = document.createElement("button");
  button.id = BETTER_PROMPT_BUTTON_ID;
  button.type = "button";
  button.className = "better-prompt-button";
  button.textContent = "\u2728";
  button.title = "Better Prompt";
  button.setAttribute("aria-label", "Better Prompt");

  button.addEventListener("click", () => {
    const latestInput = getPromptInputElement();

    if (!latestInput) {
      return;
    }

    handleBetterPromptClick(latestInput);
  });

  inputWrapper.appendChild(button);
}

function startBetterPrompt() {
  injectBetterPromptButton();

  const observer = new MutationObserver(() => {
    injectBetterPromptButton();
  });

  observer.observe(document.body, {
    childList: true,
    subtree: true
  });
}

startBetterPrompt();
