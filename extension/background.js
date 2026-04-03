function buildGoogleAuthUrl(clientId, redirectUri) {
  var params = new URLSearchParams({
    client_id: clientId,
    response_type: "token",
    redirect_uri: redirectUri,
    scope: "openid email profile",
    prompt: "select_account"
  });

  return "https://accounts.google.com/o/oauth2/v2/auth?" + params.toString();
}

function parseOAuthCallback(callbackUrl) {
  var hashIndex = callbackUrl.indexOf("#");
  if (hashIndex === -1) {
    throw new Error("Google login callback did not include an access token.");
  }

  var fragment = callbackUrl.slice(hashIndex + 1);
  var params = new URLSearchParams(fragment);
  var accessToken = params.get("access_token");
  var error = params.get("error");

  if (error) {
    throw new Error("Google login failed: " + error);
  }

  if (!accessToken) {
    throw new Error("Google login callback did not include an access token.");
  }

  return accessToken;
}

chrome.runtime.onMessage.addListener(function(message, sender, sendResponse) {
  if (!message || message.type !== "better-prompt-google-sign-in") {
    return false;
  }

  if (!message.clientId || message.clientId.indexOf("YOUR_GOOGLE_CLIENT_ID") === 0) {
    sendResponse({
      ok: false,
      error: "확장 프로그램 설정에 Google Client ID가 없습니다."
    });
    return false;
  }

  var redirectUri = chrome.identity.getRedirectURL("better-prompt");
  var authUrl = buildGoogleAuthUrl(message.clientId, redirectUri);

  chrome.identity.launchWebAuthFlow(
    {
      url: authUrl,
      interactive: true
    },
    function(callbackUrl) {
      if (chrome.runtime.lastError) {
        sendResponse({
          ok: false,
          error: chrome.runtime.lastError.message
        });
        return;
      }

      try {
        sendResponse({
          ok: true,
          accessToken: parseOAuthCallback(callbackUrl || "")
        });
      } catch (error) {
        sendResponse({
          ok: false,
          error: error instanceof Error ? error.message : "구글 로그인 처리에 실패했습니다."
        });
      }
    }
  );

  return true;
});
