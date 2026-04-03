const BETTER_PROMPT_CONFIG = Object.freeze({
  // 공개 배포용 백엔드 주소를 여기 한 곳에서만 바꾼다.
  apiBaseUrl: "https://better-prompt-evp9.onrender.com",
  apiUrl: "https://better-prompt-evp9.onrender.com/improve",
  googleClientId: "YOUR_GOOGLE_CLIENT_ID.apps.googleusercontent.com",
  promptSelectors: [
    "#prompt-textarea",
    'textarea[data-testid="prompt-textarea"]',
    'textarea[placeholder*="Message"]',
    '[contenteditable="true"][role="textbox"]'
  ]
});
