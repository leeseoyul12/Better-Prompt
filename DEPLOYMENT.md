# Render 테스트 배포

이 배포는 초대 계정 테스트용이다. Python 3.12.14, 확장 버전 0.2.1.

- 저장소 루트에서 빌드: `pip install -r backend/requirements.txt`
- 시작: `uvicorn backend.main:app --host 0.0.0.0 --port $PORT`
- 준비 확인: `/health`
- Free 컴퓨트 유지. 유료 디스크·유료 DB를 추가하지 않는다.
- 기존 `OPENAI_API_KEY`는 Render에만 보존하고 GitHub/확장 파일에 넣지 않는다.
- `OPENAI_RETRY_ATTEMPTS=0`, `OPENAI_TIMEOUT_SECONDS=20` 권장.
- `BETTER_PROMPT_ALLOWED_EMAILS`에 초대할 Google 계정 메일을 쉼표로 구분한다.
  빈 값은 모두 차단한다. `/improve`는 유효한 서비스 로그인 세션도 요구한다.

기존 서버의 DB 설정이 없으면 PostgreSQL 연결 실패 시 로컬 SQLite를 쓴다.
Free 서버의 재시작·휴면·재배포에서 이 파일의 변경은 유지되지 않는다.
보존해야 할 데이터가 있으면 재배포 전에 별도 보존 방법을 마련해야 한다.
현재 구조에서 저장 프롬프트를 영속 보관한다고 안내하면 안 된다.

이메일 초대 제한·출력 길이 제한·재시도 제한은 무제한 익명 AI 호출을
막기 위한 조치다. 월 전체 과금의 엄격한 상한을 보장하지는 않는다.
모델 실제 과금과 계정 전체 사용은 별도로 확인해야 한다.

서버가 준비된 후 `/health` 200과 비로그인 `/improve` 401을 먼저 확인한다.
이 두 검사는 AI 호출이 필요 없다. 허용되지 않은 로그인 계정은 403이어야 한다.
실제 프롬프트 품질·Google OAuth·Chrome 입력창 동작은 별도 시험한다.

확장 프로그램은 서버 배포만으로 업데이트되지 않는다. 새 `extension` 폴더를
Chrome에 불러오거나 기존 스토어 항목에 0.2.1 패키지를 제출해야 한다.
압축 해제 설치의 확장 ID가 달라지면 Google OAuth 리디렉션 설정이 맞지 않을
수 있으므로 실제 로그인 성공을 확인한 후 친구 테스트를 시작한다.

롤백은 Render의 이전 성공 커밋을 지정해 진행한다. 서버 롤백으로 휴면/
재배포에서 사라진 SQLite 변경 내용이 복구되지는 않는다.
