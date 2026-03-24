# Better Prompt

ChatGPT 입력창 옆 `✨` 버튼을 눌렀을 때만 동작하는 프롬프트 개선 도구입니다.

## 문제 정의

이 대AI 시대에 사람들은 프롬프트를 별로 신경쓰지 않고 쓰는 경우가 많음

## 목표
프롬프트 공부를 굳이 하지 않아도, 매번 신경쓰지 않아도
좋은 프롬프트를 쓸 수 있게 함

## 현재 구현 상태

- Chrome Extension (Manifest V3) 기반 호출형 UX
- FastAPI `POST /improve` API 연동
- 현재 활성 AI Provider: `Gemini`
- Provider 분리 구조 유지 (추후 OpenAI Provider 추가/교체 가능)

## 핵심 기능

1. ChatGPT 입력창 감지
2. 입력창 옆 `✨` 버튼 추가
3. 버튼 클릭 시 현재 입력 텍스트 수집
4. 백엔드 `/improve` API 호출
5. 아래 응답 구조 표시
   - `issues` (0~3개)
   - 각 이슈 한 줄 설명
   - `improved_prompt`
6. 팝업 UI에서 결과 확인
7. 사용자 선택
   - `유지하기`: 닫기
   - `개선 적용`: 입력창 텍스트 교체
8. 문제점이 없으면 `충분히 좋은 프롬프트입니다!` 안내 표시

## 프로젝트 구조

```text
Better-Prompt/
├─ backend/
│  ├─ __init__.py
│  ├─ config.py
│  ├─ main.py
│  ├─ providers.py
│  ├─ requirements.txt
│  └─ .env.example
├─ extension/
│  ├─ manifest.json
│  ├─ content.js
│  └─ content.css
└─ prompt/
```

## 백엔드 실행 방법

가상환경이 깨진 경우(기존 Python 경로가 바뀐 경우)는 재생성 후 실행하세요.

### Windows PowerShell

```powershell
cd backend

# 1) 기존 가상환경 삭제 (깨졌을 때만)
Remove-Item -Recurse -Force .venv

# 2) Python 3.11 기반으로 새 가상환경 생성
#    예시: py -3.11 -m venv .venv
#    또는 설치된 python 경로로 실행
py -3.11 -m venv .venv

# 3) 활성화 및 의존성 설치
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
pip install -r requirements.txt

# 4) 환경변수 파일 준비
Copy-Item .env.example .env
# .env 파일에 GEMINI_API_KEY 실제 값 입력

# 5) 서버 실행
uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

## 확장 프로그램 실행 방법

1. Chrome `chrome://extensions` 진입
2. `개발자 모드` 활성화
3. `압축해제된 확장 프로그램 로드` 클릭
4. `extension` 폴더 선택
5. `https://chatgpt.com` 새로고침 후 입력창 옆 `✨` 버튼 확인

## API 응답 계약

`POST /improve` 응답은 아래 규칙을 검증합니다.

- `issues`: 0~3개만 허용
- `issues[].type`: 비어 있지 않은 문자열
- `issues[].description`: 줄바꿈 없는 한 줄 문자열
- `improved_prompt`: 비어 있지 않은 문자열

## 기술 스택

- Frontend: Chrome Extension (Manifest V3, JavaScript)
- Backend: Python FastAPI
- AI Provider: Gemini (현재), OpenAI (추후 확장 예정)
