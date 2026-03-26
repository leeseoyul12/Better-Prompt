const BETTER_PROMPT_BUTTON_ID = "better-prompt-trigger";
const BETTER_PROMPT_WRAPPER_CLASS = "better-prompt-wrapper";
const BETTER_PROMPT_POPUP_ID = "better-prompt-popup";

const BETTER_PROMPT_EMPTY_PROMPT_MESSAGE = "\uC785\uB825\uB41C \uD504\uB86C\uD504\uD2B8\uAC00 \uC5C6\uC2B5\uB2C8\uB2E4.";
const BETTER_PROMPT_STALE_PROMPT_MESSAGE = "\uD504\uB86C\uD504\uD2B8\uAC00 \uBC14\uB00C\uC5C8\uC2B5\uB2C8\uB2E4. \uB2E4\uC2DC \uBD84\uC11D\uD574 \uC8FC\uC138\uC694.";

const BETTER_PROMPT_RUNTIME_CONFIG =
  typeof BETTER_PROMPT_CONFIG !== "undefined"
    ? BETTER_PROMPT_CONFIG
    : Object.freeze({
        apiUrl: "https://YOUR-PUBLIC-BACKEND.example.com/improve",
        promptSelectors: ["#prompt-textarea"]
      });

let activeAnalysisRequestId = 0;
let isRequestInFlight = false;
let activeAnalysisSession = null;

function getPromptSelectors() {
  return Array.isArray(BETTER_PROMPT_RUNTIME_CONFIG.promptSelectors) &&
    BETTER_PROMPT_RUNTIME_CONFIG.promptSelectors.length > 0
    ? BETTER_PROMPT_RUNTIME_CONFIG.promptSelectors
    : ["#prompt-textarea"];
}

function isVisibleElement(element) {
  return element instanceof Element && element.getClientRects().length > 0;
}

function getPromptInputElement() {
  for (const selector of getPromptSelectors()) {
    const candidate = document.querySelector(selector);
    if (candidate && isVisibleElement(candidate)) {
      return candidate;
    }
  }

  // ChatGPT DOM이 바뀌어도 입력창을 최대한 다시 찾는다.
  const textareaCandidates = Array.from(document.querySelectorAll("textarea")).filter(
    isVisibleElement
  );

  const preferredTextarea = textareaCandidates.find((element) => {
    return element.closest("form") || element.id.includes("prompt");
  });

  if (preferredTextarea) {
    return preferredTextarea;
  }

  const editorCandidates = Array.from(
    document.querySelectorAll('[contenteditable="true"][role="textbox"]')
  ).filter(isVisibleElement);

  return (
    editorCandidates.find((element) => {
      return element.closest("form") || element.closest('[aria-label*="message" i]');
    }) ?? editorCandidates[0] ?? null
  );
}

function getPromptInputContainer(inputElement) {
  return inputElement.closest("form") || inputElement.parentElement || inputElement;
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

function clearElement(element) {
  while (element.firstChild) {
    element.removeChild(element.firstChild);
  }
}

function createPopupSection(titleText) {
  const section = document.createElement("div");
  section.className = "better-prompt-popup-section";

  const title = document.createElement("p");
  title.className = "better-prompt-section-title";
  title.textContent = titleText;

  section.appendChild(title);
  return section;
}

function renderMessageBlock(resultsContainer, titleText, message, blockClass) {
  if (!resultsContainer || !resultsContainer.isConnected) {
    return;
  }

  clearElement(resultsContainer);

  const section = createPopupSection(titleText);
  const block = document.createElement("div");
  block.className = blockClass;
  block.textContent = message;

  section.appendChild(block);
  resultsContainer.appendChild(section);
}

function setTriggerButtonBusy(isBusy) {
  const triggerButton = document.querySelector(`#${BETTER_PROMPT_BUTTON_ID}`);

  if (!triggerButton) {
    return;
  }

  triggerButton.disabled = isBusy;
  triggerButton.setAttribute("aria-busy", String(isBusy));
  triggerButton.classList.toggle("is-busy", isBusy);
  triggerButton.textContent = isBusy ? "\u23F3" : "\u2728";
}

function invalidateCurrentSession() {
  activeAnalysisSession = null;
  activeAnalysisRequestId += 1;
  isRequestInFlight = false;
  setTriggerButtonBusy(false);
}

function dismissActiveSession() {
  invalidateCurrentSession();
  removeBetterPromptPopup();
}

async function requestPromptImprovement(promptText) {
  const response = await fetch(BETTER_PROMPT_RUNTIME_CONFIG.apiUrl, {
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

  const header = document.createElement("div");
  header.className = "better-prompt-popup-header";

  const title = document.createElement("h3");
  title.textContent = "Better Prompt";

  const closeButton = document.createElement("button");
  closeButton.type = "button";
  closeButton.className = "better-prompt-close-button";
  closeButton.setAttribute("aria-label", "\uB2EB\uAE30");
  closeButton.textContent = "\u2715";

  header.appendChild(title);
  header.appendChild(closeButton);

  const currentPromptSection = createPopupSection("\uD604\uC7AC \uD504\uB86C\uD504\uD2B8");
  const previewElement = document.createElement("div");
  previewElement.className = "better-prompt-preview";
  previewElement.textContent = currentPrompt || BETTER_PROMPT_EMPTY_PROMPT_MESSAGE;
  currentPromptSection.appendChild(previewElement);

  const resultsContainer = document.createElement("div");
  resultsContainer.className = "better-prompt-results";

  const actions = document.createElement("div");
  actions.className = "better-prompt-popup-actions";

  const keepButton = document.createElement("button");
  keepButton.type = "button";
  keepButton.className = "better-prompt-secondary-button";
  keepButton.setAttribute("data-action", "keep");
  keepButton.textContent = "\uC720\uC9C0\uD558\uAE30";

  const applyButton = document.createElement("button");
  applyButton.type = "button";
  applyButton.className = "better-prompt-primary-button";
  applyButton.setAttribute("data-action", "apply");
  applyButton.textContent = "\uAC1C\uC120 \uC801\uC6A9";
  applyButton.disabled = true;

  actions.appendChild(keepButton);
  actions.appendChild(applyButton);

  popup.appendChild(header);
  popup.appendChild(currentPromptSection);
  popup.appendChild(resultsContainer);
  popup.appendChild(actions);

  closeButton.addEventListener("click", () => {
    dismissActiveSession();
  });

  keepButton.addEventListener("click", () => {
    dismissActiveSession();
  });

  document.body.appendChild(popup);

  return {
    popup,
    resultsContainer,
    applyButton
  };
}

function renderLoadingState(resultsContainer) {
  renderMessageBlock(
    resultsContainer,
    "\uBD84\uC11D \uACB0\uACFC",
    "\uD504\uB86C\uD504\uD2B8\uB97C \uBD84\uC11D\uD558\uACE0 \uC788\uC2B5\uB2C8\uB2E4...",
    "better-prompt-status"
  );
}

function renderErrorState(resultsContainer, message) {
  renderMessageBlock(resultsContainer, "\uC624\uB958 \uC548\uB0B4", message, "better-prompt-error-box");
}

function renderNoticeState(resultsContainer, message) {
  renderMessageBlock(resultsContainer, "\uC548\uB0B4", message, "better-prompt-status");
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

function renderNoIssuesMessage(resultsContainer, improvedPrompt) {
  if (!resultsContainer || !resultsContainer.isConnected) {
    return;
  }

  clearElement(resultsContainer);

  const resultSection = createPopupSection("\uBD84\uC11D \uACB0\uACFC");
  const resultBlock = document.createElement("div");
  resultBlock.className = "better-prompt-status";
  resultBlock.textContent = "\uCDA9\uBD84\uD788 \uC88B\uC740 \uD504\uB86C\uD504\uD2B8\uC785\uB2C8\uB2E4.";
  resultSection.appendChild(resultBlock);

  const improvedPromptSection = createPopupSection("\uCD94\uCC9C \uD504\uB86C\uD504\uD2B8");
  const improvedPromptElement = document.createElement("div");
  improvedPromptElement.className = "better-prompt-improved-prompt";
  improvedPromptElement.textContent = improvedPrompt || "";
  improvedPromptSection.appendChild(improvedPromptElement);

  resultsContainer.appendChild(resultSection);
  resultsContainer.appendChild(improvedPromptSection);
}

function renderAnalysisState(resultsContainer, analysisResult) {
  if (!resultsContainer || !resultsContainer.isConnected) {
    return;
  }

  const issues = Array.isArray(analysisResult?.issues) ? analysisResult.issues : [];
  const improvedPrompt = analysisResult?.improved_prompt || "";

  if (issues.length === 0) {
    renderNoIssuesMessage(resultsContainer, improvedPrompt);
    return;
  }

  clearElement(resultsContainer);

  const issuesSection = createPopupSection("\uBB38\uC81C\uC810");
  const issueListElement = document.createElement("ul");
  issueListElement.className = "better-prompt-issue-list";
  issuesSection.appendChild(issueListElement);

  const improvedPromptSection = createPopupSection("\uAC1C\uC120 \uD504\uB86C\uD504\uD2B8");
  const improvedPromptElement = document.createElement("div");
  improvedPromptElement.className = "better-prompt-improved-prompt";
  improvedPromptElement.textContent = improvedPrompt;
  improvedPromptSection.appendChild(improvedPromptElement);

  resultsContainer.appendChild(issuesSection);
  resultsContainer.appendChild(improvedPromptSection);
  renderIssues(issueListElement, issues);
}

function getCurrentSession(requestId) {
  return activeAnalysisSession && activeAnalysisSession.requestId === requestId
    ? activeAnalysisSession
    : null;
}

async function handleBetterPromptClick(inputElement) {
  if (isRequestInFlight) {
    return;
  }

  const promptText = getPromptText(inputElement);
  console.log("[Better Prompt] Current prompt:", promptText);

  const popupParts = createBetterPromptPopup(promptText);
  if (!promptText) {
    activeAnalysisSession = null;
    renderNoticeState(popupParts.resultsContainer, "\uD504\uB86C\uD504\uD2B8\uB97C \uBA3C\uC800 \uC785\uB825\uD574 \uC8FC\uC138\uC694.");
    return;
  }

  const requestId = ++activeAnalysisRequestId;

  activeAnalysisSession = {
    requestId,
    inputElement,
    promptSnapshot: promptText,
    popup: popupParts.popup,
    resultsContainer: popupParts.resultsContainer,
    applyButton: popupParts.applyButton
  };

  isRequestInFlight = true;
  setTriggerButtonBusy(true);
  renderLoadingState(popupParts.resultsContainer);

  try {
    const analysisResult = await requestPromptImprovement(promptText);
    const currentSession = getCurrentSession(requestId);

    if (!currentSession || !currentSession.resultsContainer?.isConnected) {
      return;
    }

    renderAnalysisState(currentSession.resultsContainer, analysisResult);

    if (currentSession.applyButton) {
      currentSession.applyButton.disabled = false;
      currentSession.applyButton.addEventListener(
        "click",
        () => {
          const latestSession = getCurrentSession(requestId);

          if (!latestSession || !latestSession.resultsContainer?.isConnected) {
            return;
          }

          const currentPrompt = getPromptText(latestSession.inputElement);
          if (currentPrompt !== latestSession.promptSnapshot) {
            renderNoticeState(latestSession.resultsContainer, BETTER_PROMPT_STALE_PROMPT_MESSAGE);
            return;
          }

          const improvedPrompt = analysisResult?.improved_prompt || "";
          setPromptText(latestSession.inputElement, improvedPrompt);
          latestSession.inputElement.focus();
          dismissActiveSession();
        },
        { once: true }
      );
    }
  } catch (error) {
    const currentSession = getCurrentSession(requestId);

    if (!currentSession || !currentSession.resultsContainer?.isConnected) {
      return;
    }

    console.error("[Better Prompt] Failed to improve prompt:", error);
    const message =
      error instanceof Error && error.message
        ? error.message
        : "\uBC31\uC5D4\uB4DC \uC11C\uBC84\uC5D0 \uC5F0\uACB0\uD560 \uC218 \uC5C6\uC2B5\uB2C8\uB2E4.";
    renderErrorState(currentSession.resultsContainer, message);
  } finally {
    if (getCurrentSession(requestId)) {
      isRequestInFlight = false;
      setTriggerButtonBusy(false);
    }
  }
}

function injectBetterPromptButton() {
  const inputElement = getPromptInputElement();

  if (!inputElement) {
    return;
  }

  const inputWrapper = getPromptInputContainer(inputElement);

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

    if (!latestInput || isRequestInFlight) {
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
