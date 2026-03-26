const BETTER_PROMPT_CONFIG = Object.freeze({
  // 공개 배포용 백엔드 주소를 여기 한 곳에서만 바꾼다.
  apiUrl: "https://YOUR-PUBLIC-BACKEND.example.com/improve",
  promptSelectors: [
    "#prompt-textarea",
    'textarea[data-testid="prompt-textarea"]',
    'textarea[placeholder*="Message"]',
    '[contenteditable="true"][role="textbox"]'
  ]
});
