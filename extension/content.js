const BETTER_PROMPT_BUTTON_ID = "better-prompt-trigger";
const BETTER_PROMPT_WRAPPER_CLASS = "better-prompt-wrapper";
const BETTER_PROMPT_POPUP_ID = "better-prompt-popup";
const BETTER_PROMPT_API_URL = "http://127.0.0.1:8000/improve";

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
function removeBetterPromptPopup() {
  const existingPopup = document.querySelector(`#${BETTER_PROMPT_POPUP_ID}`);

  if (existingPopup) {
    existingPopup.remove();
  }
}

/**
 * Calls FastAPI backend and returns prompt analysis JSON.
 */
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
      // Keep default message when error body is not valid JSON.
      console.debug("[Better Prompt] Error response parsing failed:", jsonError);
    }

    throw new Error(detail);
  }

  return response.json();
}

/**
 * Creates popup shell first. Result content is filled later.
 */
function createBetterPromptPopup(currentPrompt) {
  removeBetterPromptPopup();

  const popup = document.createElement("div");
  popup.id = BETTER_PROMPT_POPUP_ID;
  popup.className = "better-prompt-popup";

  popup.innerHTML = `
    <div class="better-prompt-popup-header">
      <h3>Better Prompt</h3>
      <button type="button" class="better-prompt-close-button" aria-label="닫기">×</button>
    </div>
    <div class="better-prompt-popup-section">
      <p class="better-prompt-section-title">현재 프롬프트</p>
      <div class="better-prompt-preview"></div>
    </div>
    <div class="better-prompt-results"></div>
    <div class="better-prompt-popup-actions">
      <button type="button" class="better-prompt-secondary-button" data-action="keep">
        유지하기
      </button>
      <button type="button" class="better-prompt-primary-button" data-action="apply" disabled>
        개선 적용
      </button>
    </div>
  `;

  const previewElement = popup.querySelector(".better-prompt-preview");
  const resultsContainer = popup.querySelector(".better-prompt-results");
  const closeButton = popup.querySelector(".better-prompt-close-button");
  const keepButton = popup.querySelector('[data-action="keep"]');
  const applyButton = popup.querySelector('[data-action="apply"]');

  if (previewElement) {
    previewElement.textContent = currentPrompt || "입력된 프롬프트가 없습니다.";
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

/**
 * Shows loading text while API request is running.
 */
function renderLoadingState(resultsContainer) {
  if (!resultsContainer) {
    return;
  }

  resultsContainer.innerHTML = `
    <div class="better-prompt-popup-section">
      <p class="better-prompt-section-title">분석 결과</p>
      <div class="better-prompt-status">프롬프트를 분석하고 있습니다...</div>
    </div>
  `;
}

/**
 * Shows error text in popup when request fails.
 */
function renderErrorState(resultsContainer, message) {
  if (!resultsContainer) {
    return;
  }

  resultsContainer.innerHTML = `
    <div class="better-prompt-popup-section">
      <p class="better-prompt-section-title">오류 안내</p>
      <div class="better-prompt-error-box">${message}</div>
    </div>
  `;
}

/**
 * Shows non-error notice text in popup.
 */
function renderNoticeState(resultsContainer, message) {
  if (!resultsContainer) {
    return;
  }

  resultsContainer.innerHTML = `
    <div class="better-prompt-popup-section">
      <p class="better-prompt-section-title">안내</p>
      <div class="better-prompt-status">${message}</div>
    </div>
  `;
}

/**
 * Renders issue items in the popup.
 */
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

/**
 * 문제점이 없을 때 긍정 안내 문구를 보여준다.
 */
function renderNoIssuesMessage(resultsContainer) {
  resultsContainer.innerHTML = `
    <div class="better-prompt-popup-section">
      <p class="better-prompt-section-title">분석 결과</p>
      <div class="better-prompt-status">충분히 좋은 프롬프트입니다!</div>
    </div>
    <div class="better-prompt-popup-section">
      <p class="better-prompt-section-title">추천 프롬프트</p>
      <div class="better-prompt-improved-prompt"></div>
    </div>
  `;
}

/**
 * Shows API analysis content inside the popup.
 */
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
      <p class="better-prompt-section-title">문제점</p>
      <ul class="better-prompt-issue-list"></ul>
    </div>
    <div class="better-prompt-popup-section">
      <p class="better-prompt-section-title">개선 프롬프트</p>
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

/**
 * Handles click: read prompt, request backend analysis, then render result.
 */
async function handleBetterPromptClick(inputElement) {
  const promptText = getPromptText(inputElement);
  console.log("[Better Prompt] Current prompt:", promptText);

  const popupParts = createBetterPromptPopup(promptText);
  if (!promptText) {
    renderNoticeState(popupParts.resultsContainer, "프롬프트를 먼저 입력해 주세요.");
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
        : "백엔드 서버에 연결할 수 없습니다.";
    renderErrorState(popupParts.resultsContainer, message);
  }
}

/**
 * Adds the Better Prompt button next to the ChatGPT input box.
 * If the button already exists, we do nothing.
 */
function injectBetterPromptButton() {
  const inputElement = getPromptInputElement();

  if (!inputElement) {
    return;
  }

  const inputWrapper = inputElement.parentElement;

  if (!inputWrapper) {
    return;
  }

  // Prevent duplicate button creation when the page re-renders.
  if (inputWrapper.querySelector(`#${BETTER_PROMPT_BUTTON_ID}`)) {
    return;
  }

  inputWrapper.classList.add(BETTER_PROMPT_WRAPPER_CLASS);

  const button = document.createElement("button");
  button.id = BETTER_PROMPT_BUTTON_ID;
  button.type = "button";
  button.className = "better-prompt-button";
  button.textContent = "✨";
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

/**
 * ChatGPT updates the page dynamically, so we observe DOM changes
 * and try to inject the button whenever the input box appears again.
 */
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
