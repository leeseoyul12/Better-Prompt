# Better Prompt

ChatGPT 입력창에 `✨` 버튼을 붙여, 사용자가 쓴 문장을 더 나은 프롬프트로 바꿔 주는 Chrome 확장 프로그램입니다.

## 현재 구성

- Chrome Extension (Manifest V3)
- FastAPI 백엔드
- OpenAI Responses API 기반 프롬프트 개선
- Google 로그인 + 저장 프롬프트 기능

## 프로젝트 구조

```text
Better-Prompt/
├─ backend/
│  ├─ auth.py
│  ├─ config.py
│  ├─ database.py
│  ├─ main.py
│  ├─ providers.py
│  ├─ requirements.txt
│  └─ .env.example
├─ extension/
│  ├─ background.js
│  ├─ config.js
│  ├─ content.css
│  ├─ content.js
│  └─ manifest.json
└─ tests/
```

## 환경변수

`backend/.env.example`를 복사해서 `backend/.env`를 만든 뒤 아래 값을 채웁니다.

```env
BETTER_PROMPT_PROVIDER=openai
OPENAI_API_KEY=your_api_key
OPENAI_MODEL=gpt-5-mini
OPENAI_API_BASE=https://api.openai.com/v1
OPENAI_TIMEOUT_SECONDS=20
OPENAI_RETRY_ATTEMPTS=1
OPENAI_MAX_OUTPUT_TOKENS=1024
```

DB와 로그인 기능을 함께 테스트하려면 아래 값도 필요합니다.

```env
BETTER_PROMPT_DATABASE_URL=postgresql+psycopg://postgres:postgres@127.0.0.1:5432/better_prompt
BETTER_PROMPT_GOOGLE_USERINFO_URL=https://www.googleapis.com/oauth2/v3/userinfo
```

SQLite로 먼저 테스트하려면 예를 들어 이렇게 쓸 수 있습니다.

```env
BETTER_PROMPT_DATABASE_URL=sqlite:///./backend/better_prompt.sqlite3
```

## 백엔드 실행

```powershell
cd backend
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
# .env에 OPENAI_API_KEY 등 실제 값을 입력
cd ..
.\backend\.venv\Scripts\python.exe -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

## 확장 프로그램 실행

1. Chrome에서 `chrome://extensions` 열기
2. `개발자 모드` 켜기
3. `압축해제된 확장 프로그램 로드` 클릭
4. `extension` 폴더 선택
5. `extension/config.js`의 백엔드 주소가 로컬 테스트 기준으로 맞는지 확인

## API 응답 형식

`POST /improve`는 아래 형식을 유지합니다.

```json
{
  "issues": [
    { "type": "string", "description": "string" }
  ],
  "improved_prompt": "string"
}
```

## 테스트

```powershell
.\backend\.venv\Scripts\python.exe -m unittest discover -s tests -v
```
