# Better Prompt

ChatGPT 입력창에 `✨` 버튼을 붙여, 사용자가 쓴 문장을 더 나은 프롬프트로 바꿔 주는 Chrome 확장 프로그램입니다.

## 현재 구성

- Chrome Extension (Manifest V3)
- FastAPI 백엔드
- OpenAI Responses API 기반 프롬프트 개선
- Google 로그인 + 저장 프롬프트 기능

현재 배포 범위는 초대된 계정의 비공개 테스트입니다. 프롬프트 개선에는
Google 로그인과 `BETTER_PROMPT_ALLOWED_EMAILS`에 등록된 계정이 필요합니다.
목록이 비어 있으면 모든 AI 개선 요청을 차단합니다. 친구 테스트는 허용
계정 추가 후 진행합니다. 이 제한은 월 전체 지출의 자동 상한은 아닙니다.

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
BETTER_PROMPT_ALLOWED_EMAILS=초대할_Google_계정_이메일
OPENAI_API_KEY=your_api_key
OPENAI_MODEL=gpt-5-mini
OPENAI_API_BASE=https://api.openai.com/v1
OPENAI_TIMEOUT_SECONDS=20
OPENAI_RETRY_ATTEMPTS=0
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

로컬에서는 `apiBaseUrl`을 `http://127.0.0.1:8000`, `apiUrl`을
`http://127.0.0.1:8000/improve`로 함께 바꿉니다. 저장소의 기존 기본 주소는
Render 운영 주소입니다. 이번 수정본은 운영 서버에 배포하지 않았습니다.
새 확장을 사용하려면 `/health`가 있는 새 백엔드도 함께 실행해야 합니다.
실제 AI 개선 요청은 OpenAI API 비용이 발생할 수 있습니다.
확장 버전은 `0.2.1`입니다. 소스 변경만으로 기존에 설치한 확장 프로그램이
자동 갱신되지는 않습니다. 압축 해제 설치를 사용 중이라면 새 `extension`
폴더를 불러오고 ChatGPT 탭을 새로고침해야 합니다. Google OAuth는 확장 ID에
연결된 리디렉션 설정에 따라 추가 설정이 필요할 수 있습니다.

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

`GET /health`는 앱 준비가 끝나면 `{"status":"ok"}`를 반환합니다.
AI 호출·로그인 검증·DB 조회를 하지 않습니다. DB/모델의 상태를 보증하는
종합 상태 검사는 아닙니다.

확장은 준비 확인에 최대 75초, 개선 응답에 최대 70초를 각각 기다립니다.
응답 본문을 다 읽을 때까지 제한을 유지합니다. 준비가 실패하면 개선 요청은
보내지 않으며, 개선 요청을 확장에서 자동 반복하지 않습니다.
닫기/취소는 원문을 유지하고 로컬 대기를 중단합니다. 이미 보낸 AI 요청의
서버 처리·과금까지 취소된다는 뜻은 아닙니다.

잘못된 모델 출력·직접 답변으로 의심되는 출력·통신 실패는 `502` 오류로
알리고, 원문을 성공 결과로 대체하지 않습니다. 답변 감지는 보수적인
패턴 검사이므로 의미·사실·번역의 정확성을 보증하지 않습니다.
개선문 내부의 줄바꿈과 코드 블록은 보존합니다.

기본 자동 재시도는 0회입니다. 명시적으로 설정하면 일부 HTTP 오류에만
최대 1회 재시도하며, 네트워크 타임아웃·잘못된 출력은 자동 재시도하지
않습니다. 호출별 네트워크 제한시간은 1~30초로 제한합니다. 이것은 HTTP
단계별 제한으로, 서버 전체 작업의 엄격한 벽시계 제한은 아닙니다.
기존 `.env`는 자동으로 수정하지 않으므로 예제와 실제 설정을 대조해야 합니다.
분당 요청 제한·재시도 상한은 월 전체 지출 상한을 보장하지 않습니다.

## 테스트

```powershell
.\backend\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Node가 PATH에 있으면 외부 HTTP를 차단하는 통합 점검을 실행할 수 있습니다.

```powershell
.\backend\.venv\Scripts\python.exe scripts/verify_offline.py
```

이 점검은 Python 회귀 시험과 Node의 확장 동작 모의 시험을 모두 실행합니다.
Google/OpenAI는 모의 처리하고, 임시 DB만 만듭니다. 로그는 `verification/`에
저장합니다. 실제 Chrome의 버튼 배치·입력창 호환성·OAuth·AI 개선 효과는
별도 확인해야 합니다.
