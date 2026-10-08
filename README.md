# Threads AI 트렌드 아카이브 v1.0 — 1단계

Python + Render Cron + Notion 데이터베이스 + Telegram 완료 알림. **n8n 없음.**

## 제공 기능

- 샘플 모드: Threads API 승인 없이 게시글 5건으로 전체 파이프라인 테스트(중복 1건, 무관 1건 포함)
- 주제 분류: AI·생성형 AI / 교육·대학 / IT·개발 도구 / 산업·정책
- OpenAI 키가 없으면 키워드 규칙 기반 분류 및 본문 발췌(진짜 AI 요약이 아님)
- 본문·원문 URL·작성자·게시일을 Notion 페이지로 저장
- 배치 내부 중복 제거 + 기존 Notion 제목의 `[ID:...]` 값 조회로 재실행 중복 방지
- 텔레그램은 시작/진행/개별 오류를 보내지 않고 실행 종료 시 한 번만 알림(실제 모드만)
- `reports/last_run.json`에 오류 및 집계 저장(로컬 실행시만 지속)
- Threads 실연동은 권한과 엔드포인트 확인 전까지 안전 잠금

## 로컬 실행 (Windows PowerShell)

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install -r requirements.txt
Copy-Item .env.example .env
py -m src.main
py -m unittest discover -s tests -v
```

기본 설정은 `SOURCE_MODE=sample`, `DRY_RUN=true`입니다. 외부 Notion 저장과 Telegram 전송 없이 결과를 보여줍니다. 정상 기대값은 `수집 5 / 배치 중복 1 / 유효 4 / 관련 3 / 무관 1 / 저장 예정 3 / 실패 0`입니다.

## Notion 실연동

1. Notion에서 **새 데이터베이스(표)**를 만듭니다. 제목 열의 이름을 `Name`으로 맞춥니다(다르면 `NOTION_TITLE_PROPERTY` 변경).
2. Notion Integrations 사이트에서 내부 연결(Integration)을 만들고 API 토큰을 복사합니다.
3. 데이터베이스를 연결(Connections) 메뉴에서 해당 Integration과 공유합니다.
4. 최신 Notion API의 **data source ID**를 확인하여 `NOTION_DATA_SOURCE_ID`로 설정합니다. `database_id`와 다를 수 있으므로 혼동하지 마세요.
5. `.env`에 `NOTION_TOKEN`, `NOTION_DATA_SOURCE_ID`를 설정하고 `DRY_RUN=false`로 변경하면 **샘플 데이터를 실제 Notion에 저장**합니다. 샘플 글은 실제 Threads 글이 아니므로 Notion에 예시용이라고 구별해 사용하세요.
6. 같은 설정으로 두 번 실행하면 Notion 제목에 심은 16자리 게시글 식별값을 기준으로 두 번째 실행은 중복 건을 건너뜁니다.

현재 구현은 Notion API `2026-03-11`을 기본값으로 사용합니다. API 버전을 고정 변경해야 하면 `NOTION_VERSION`을 설정하세요.

## Telegram

1. Telegram에서 `@BotFather`로 봇을 만들고 토큰을 발급받습니다.
2. 봇과 대화를 시작한 다음 Chat ID를 확인합니다(예: getUpdates API로 확인).
3. `.env`에 `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` 설정.
4. `DRY_RUN=false`일 때 실행 종료 알림이 정확히 한 번 발송됩니다. 봇이 사용자와 대화를 먼저 시작할 수는 없습니다.

## Threads 공식 API 연결 전 확인

`SOURCE_MODE=threads`를 선택하면 공식 API 토큰이 필요합니다. 1단계에서는 `THREADS_API_ENABLED=false`가 기본값이므로 토큰이 실수로 들어가도 외부 수집을 시작하지 않습니다. 권한을 받은 뒤 실제 발급 계정에서 검색 엔드포인트·검색 파라미터·허용 범위를 확인하고 다음 값을 설정하세요.

```dotenv
SOURCE_MODE=threads
THREADS_API_ENABLED=true
THREADS_ACCESS_TOKEN=...
THREADS_SEARCH_ENDPOINT=/실제_확인한_경로
THREADS_QUERY_PARAM=q
THREADS_QUERIES=AI,생성형 AI,교육,Python
```

비공식 크롤링, 로그인 우회, 화면 스크래핑은 포함하지 않았습니다.

## Render 설정

- 이 폴더를 GitHub/GitLab/Bitbucket 저장소 루트에 업로드한 후 Render의 New → Blueprint에서 `render.yaml` 사용
- 기본 UTC 스케줄 `0 23 * * *` = 한국시간 매일 **08:00**
- 필수 자격증명은 Render 환경변수 화면에서 지정. `.env`를 GitHub에 올리지 마세요.
- 빌드 명령은 의존성 설치 후 8개 테스트를 실행하며, 테스트 실패 시 배포도 실패합니다.
- 실서비스에서 `SOURCE_MODE=threads`, `DRY_RUN=false`로 바꾸기 전에 API 승인을 먼저 확인하세요.
- Render Cron의 디스크는 **지속되지 않습니다**. 중복 제거는 Notion의 페이지 제목 검색으로 보장하며, 실행 로그는 Render 로그에서 확인하세요.
- `render.yaml`은 현재 소형 Cron 플랜 `0.5c-512mb`를 사용합니다. Render Cron은 무료가 아니며 최소 월 요금이 발생할 수 있습니다.

## 테스트 범위

```powershell
py -m unittest discover -s tests -v
```

테스트는 규칙 분류, 안정적인 ID, 입력 정규화, 배치 중복 제거, Notion 페이지네이션 중복 조회, 샘플 전체 실행, Notion 저장과 텔레그램 단일 종료 알림을 네트워크 없이 검증합니다.

## 운영 시 유의사항

- 게시글 전체 또는 제3자 콘텐츠를 보관·재배포하기 전에 Threads/Meta 약관, 사용허락, 개인정보와 저작권을 확인하세요.
- 이번 버전은 단순 키워드 기반 적합성 또는 선택적 OpenAI 요약입니다. 법률/정책 사실 검증 기능은 아닙니다.
- Threads 실시간 API 동작, 외부 서비스 호출, 인증된 Notion/Telegram 저장·발송은 이 샘플 테스트에서 검증하지 않았습니다.
