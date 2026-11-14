# Eco311 — Python AI agent

`What did you see?`의 설명과 지도 좌표를 받아 **신고 경로, 처리 단계, 근처 장소, 감사 메시지**를 `ai_response`라는 JSON 호환 dictionary로 반환합니다. 현재 지식 범위는 **Edmonton의 쓰레기·폐기물 관련 상황**입니다. 기존 팀원의 FastAPI/React 앱에 붙이는 모듈입니다. 별도의 챗봇이나 프런트엔드를 만들지 않습니다.

## Groq migration (2026-11-14)

Only the standalone `agent/` LLM adapter changes. `api/` and `database/` are unchanged.
The existing teammate `backend/`, `frontend/`, and `docs/` are not included in the patch.
To upgrade an existing checkout, extract `eco311-groq-patch.zip` with `unzip -o` (not `-n`).
**Do not overwrite `agent/.env`**: it contains your private settings and is deliberately absent from this patch.

From the repository root:

```bash
unzip -o eco311-groq-patch.zip -d .
uv --directory backend add 'langchain-groq>=1.1,<2'
code agent/.env
```

Set these two values in `agent/.env` (replace any old `ECO311_MODEL=gpt-4o-mini`):

```dotenv
GROQ_API_KEY=gsk_your_real_key_here
ECO311_MODEL=openai/gpt-oss-20b
```

Get a Groq key at https://console.groq.com/keys. The old `OPENAI_API_KEY` does not
activate this new module. If the teammate's parent LangGraph still has
`LLM_MODEL=openai:...`, it may independently try OpenAI; adjust that config
separately if desired. Never include API keys in a Git commit or screenshot.

Test your key before the full app:

```bash
uv --directory backend run --env-file ../agent/.env python -c 'from groq import Groq; r=Groq(timeout=20).chat.completions.create(model="openai/gpt-oss-20b",messages=[{"role":"user","content":"Reply only OK"}],max_completion_tokens=512,reasoning_effort="low"); print(r.choices[0].message.content)'
PYTHONPATH="$PWD" uv --directory backend run --env-file ../agent/.env python -m unittest agent.test_agent -v
PYTHONPATH="$PWD" uv --directory backend run --env-file ../agent/.env uvicorn api.main:app --port 8001
```

At `/docs` try `POST /api/agent/analyze`. If the Groq key is valid and the
request completes, the result should contain `ai_response.meta.llm_used: true`.
The RAG database, Edmonton 311 access and mapped-place queries work exactly as
before and can still return warnings independently of the LLM. The free tier
is rate-limited; it is not an unlimited free service.

---

## 1. 폴더와 파일

ZIP을 저장소 루트에 풀면 `agent/`, `api/`, `database/` 세 폴더가 생깁니다. 핵심 파일 9개와 `.gitignore` 3개, 총 12개입니다.

| 폴더 | 파일 | 역할 |
|---|---|---|
| `agent/` | `__init__.py` | LangChain + LangGraph, 입력 검증, RAG, 결과 조립 |
| `agent/` | `requirements.txt`, `.env.example` | 의존성과 서버 환경변수 |
| `agent/` | `test_agent.py`, `README.md` | 테스트와 연결 설명 |
| `api/` | `__init__.py`, `main.py` | 외부 데이터 클라이언트와 선택적 테스트 API |
| `database/` | `__init__.py`, `knowledge.json` | SQLite 검색/캐시와 출처가 있는 지식 데이터 |
| 각 폴더 | `.gitignore` | 키, 생성 DB, 캐시 등을 Git에서 제외 |

실행 중 `database/eco311.sqlite3` 및 SQLite 보조 파일이 생성될 수 있습니다. 팀원의 앱 DB/PostgreSQL과 별개인 작은 검색·캐시 저장소입니다.

## 2. 지금 실행할 명령어

Python 3.12와 `uv`가 필요합니다. **`backend/`와 `frontend/`가 보이는 저장소 루트**에서 실행하세요. ZIP 파일도 먼저 그 위치로 옮깁니다.

```bash
unzip -n eco311-agent.zip -d .
uv --directory backend add -r ../agent/requirements.txt
cp -n agent/.env.example agent/.env
```

VS Code에서 `agent/.env`를 열고 `GROQ_API_KEY=`를 채웁니다. 기본 모델은 `ECO311_MODEL=openai/gpt-oss-20b`이며 **GroqCloud**에서 실행됩니다 (OpenAI 결제나 키와 무관). 키를 채팅, 프런트엔드 코드 또는 `VITE_*` 환경변수에 넣지 마세요.

먼저 **독립 테스트 서버**를 실행합니다.

```bash
PYTHONPATH="$PWD" uv --directory backend run --env-file ../agent/.env uvicorn api.main:app --port 8001
```

다른 터미널에서 호출하거나 [API 문서](http://127.0.0.1:8001/docs)를 엽니다.

```bash
curl -s http://127.0.0.1:8001/api/agent/analyze \
  -H 'Content-Type: application/json' \
  -d '{"story":"A few paper cups and wrappers are on the public sidewalk.","lat":53.5461,"lng":-113.4904}'
```

응답은 `{"ai_response": {...}}`입니다. **8001 서버만 실행했다고 기존 UI가 연결되지는 않습니다.** 현재 UI는 팀원의 `/api/agent/runs`를 호출하므로 아래 4절의 세 부분을 연결해야 합니다.

`uv add`는 기존 `backend/pyproject.toml`과 `uv.lock`을 갱신할 수 있습니다. 첨부 PR에는 실제 lockfile 내용이 생략돼 있어 기존 정확한 버전 조합은 확인할 수 없었습니다. 변경된 의존성을 검토하고 기존 백엔드 테스트도 실행하세요.

## 3. 결과 변수와 Python 호출

일반 Python 함수나 기존 동기 LangGraph 노드에서는:

```python
from agent import analyze_report_sync

ai_response = analyze_report_sync(
    story="Three mattresses were dumped on public property.",
    lat=53.54136,
    lng=-113.51720,
    report_id="optional-app-report-id",
)
print(ai_response["markdown"])
print(ai_response["reporting"]["report_text"])
```

`async def` 내부에서는:

```python
from agent import analyze_report

ai_response = await analyze_report(story=user_description, lat=latitude, lng=longitude)
```

실행 중인 이벤트 루프 안에서 동기 함수를 호출하지 마세요. `ReportInput`도 `from agent import ReportInput`으로 가져올 수 있습니다. 설명은 3–4,000자, 수정 요청은 최대 1,000자입니다. GeoJSON의 `[lng, lat]` 순서와 함수의 `lat=`, `lng=`를 구분하세요.

| 결과 필드 | 팀원이 사용하는 내용 |
|---|---|
| `markdown` | 기존 Markdown 화면에 바로 표시할 완성 답변 |
| `summary`, `category`, `priority` | 관찰 요약, 분류, 우선순위 |
| `reporting` | 연락처, 공식 링크, 신고 초안, 신고 가능성, API 상태 |
| `steps` | 사용자에게 표시할 행동 단계 |
| `nearby_places` | 조건에 맞는 장소 최대 3개와 경로 정보 |
| `thank_you` | 감사 메시지 |
| `sources`, `warnings` | 근거 링크와 데이터 한계 |
| `meta` | LLM 사용 여부, 검색 방식, 처리 시간 등 개발용 정보 |

`reporting.status`는 `not_submitted`, `submitted`는 `false`입니다. 우리 앱의 지도 핀과 City 311의 접수번호는 서로 다른 데이터입니다. `ai_response`는 요청마다 별도로 생성되며 전역 “마지막 답변” 변수로 공유하지 않습니다.

## 4. 기존 팀원 코드에 연결하기: 세 부분 수정

기존 백엔드에는 이미 LangGraph, SSE, 승인 카드가 있습니다. 기존 `draft_action`만 아래 어댑터로 교체하면 새 답변을 기존 UI의 step으로 표시할 수 있습니다. 원본 파일은 이 ZIP에 포함하거나 덮어쓰지 않았습니다.

### A. `backend/app/agent/state.py`

`ReportState` 클래스 안에 추가합니다.

```python
ai_response: dict
```

### B. `backend/app/agent/runner.py`

기존 `RESULT_KEYS` 목록에 `"ai_response"`를 추가합니다. 그래야 체크포인트의 결과가 `run.result.ai_response`로 반환됩니다.

### C. `backend/app/agent/nodes.py`

위쪽에 `from agent import analyze_report_sync`를 추가하고, **기존 `draft_action` 함수 전체**를 다음으로 바꿉니다. 기존 `llm.ask_json("draft_action", ...)` 호출은 남기지 않습니다.

```python
def draft_action(state: ReportState) -> dict:
    ai_response = analyze_report_sync(
        story=state["story"],
        lat=state["lat"],
        lng=state["lng"],
        report_id=state.get("report_id"),
        review_feedback=state.get("review_feedback", ""),
    )
    reporting = ai_response["reporting"]
    phone = reporting.get("phone")
    name = reporting.get("contact_name") or "Local municipal service"
    script = list(ai_response["steps"])
    if reporting.get("report_text") and ai_response["priority"] != "emergency":
        script.append("Suggested description: " + reporting["report_text"])
    if not script:
        script = ["Confirm the appropriate local service using the linked sources."]
    draft = {
        "phone": phone,
        "contact_name": name,
        "hours": None,
        "contact_verified": bool(phone),
        "script": script,
    }
    # All supplied phone numbers come from source-backed application data.
    # Replace old candidate contacts so follow-up context stays consistent.
    contacts = [{
        "name": name, "email": None, "phone": phone, "hours": None,
        "source_url": reporting.get("url"), "verified": True,
    }] if phone else []
    title = "Recommended next steps"
    if ai_response["priority"] == "emergency":
        title = "Immediate safety guidance"
    elif phone is None:
        title = "Confirm the responsible local service"
    if state.get("review_feedback"):
        title += " (revised)"
    return {
        "ai_response": ai_response,
        "category": ai_response["category"],
        "issue_summary": ai_response["summary"],
        "contacts": contacts,
        "contact_source": "kb" if contacts else "none",
        "action_type": "call",
        "draft": draft,
        "approval_status": "awaiting",
        "review_feedback": "",
        "log": [step(
            "draft_action", title, ai_response["markdown"],
            ai_response=ai_response, draft=draft, action_type="call",
        )],
    }
```

`human_review`, `deliver`, `track`은 기존 구조를 사용합니다. 기존 call 경로는 실제 전화를 걸지 않고 전화번호와 통화 단계를 보여줍니다. 긴급 안내는 Markdown에 즉시 표시하며, 사용자가 긴급 전화를 하기 위해 앱의 승인을 기다릴 필요는 없습니다.

`phone=None`을 임의로 `311`로 바꾸지 마세요. 관할이 불명확하거나 Edmonton 밖이면 현지 기관 확인이 필요합니다. 사유지 주사기 안내처럼 공식 근거에 따라 Hiregood 등 다른 연락처가 나올 수도 있으므로 전화번호 타입은 `string | null`입니다.

연결 후 저장소 루트에서 기존 백엔드를 실행합니다.

```bash
PYTHONPATH="$PWD" uv --directory backend run --env-file ../agent/.env uvicorn app.main:app --reload --port 8000
```

`PYTHONPATH`는 새 세 폴더를 찾게 하고, `--directory backend`는 기존 `.env`와 데이터 경로를 유지합니다. `--env-file ../agent/.env`는 새 모듈이 읽는 값을 프로세스 환경변수로 넣습니다. 기존 Settings의 `extra="ignore"` 덕분에 새 설정 이름이 추가돼도 미등록 필드 오류가 나지 않습니다.

기존 `Workspace`는 `RunEvent.content`를 ReactMarkdown으로 표시하므로 지금은 프런트엔드를 수정할 필요가 없습니다. 별도 카드가 필요하면 `frontend/src/api.ts`의 `RunResult`에 다음 필드를 추가할 수 있습니다.

```ts
interface AgentResponse {
  markdown: string
  summary: string
  steps: string[]
  reporting: {
    phone: string | null
    contact_name: string | null
    reportable: boolean | null
    url: string | null
    report_text: string
    status: 'not_submitted'
  }
  nearby_places: Array<Record<string, unknown>>
  thank_you: string
  warnings: string[]
}
// Inside the existing RunResult interface:
// ai_response?: AgentResponse
// Inside a component:
// const aiResponse = run.result?.ai_response
```

기존 state의 `nearby`는 앱 안의 중복 신고 핀입니다. 새 장소 결과인 `ai_response.nearby_places`와 합치지 마세요. 새 분류명도 `ai_response.category`에 있으므로 지도 필터를 확장할 때 기존 `trash`/`dumping` 분류와 매핑할 수 있습니다.

## 5. API와 데이터가 실제로 하는 일

| 인터페이스 | 구현 상태 |
|---|---|
| `POST /api/agent/analyze` | 구현: 입력을 분석하고 `{"ai_response": ...}` 반환 |
| `GET /healthz` | 구현: 테스트 서버 상태 |
| `GET https://311.edmonton.ca/open311/v2/services.json` | 구현: City 서비스 목록 읽기 |
| `GET https://311.edmonton.ca/open311/v2/requests/{id}.json` | 구현: 지정된 City 접수번호 상태 읽기 |
| City 서비스 정의/필수 attributes 조회 | 향후 직접 제출 연결에 필요; 현재 미구현 |
| City `POST .../requests.json` | 미구현: 현재는 공식 웹/전화 안내와 초안 제공 |

직접 제출을 추가할 때는 승인된 API 접근, 실제 서비스 코드와 필수 attributes, 사용자 검토·승인, 중복 제출 방지(idempotency), 성공 응답의 실제 접수번호 저장을 연결해야 합니다. 접수 상태가 `closed`여도 상황에 따라 작업 예약을 뜻할 수 있으므로 현장의 제거 완료로 단정하지 않습니다.

독립 서버에서 `ECO311_API_KEY`를 설정하면 `X-Eco311-Key` 헤더가 필요합니다. 이 서버는 기본적으로 로컬 테스트용입니다. 기존 앱에 별도 분석 endpoint까지 붙이고 싶다면 부모 앱의 인증을 재사용합니다.

```python
from fastapi import Depends
from api.main import router as recommendation_router
from .auth import current_user

app.include_router(recommendation_router, dependencies=[Depends(current_user)])
```

이 endpoint 추가는 기존 `/runs` 연결을 대신하지 않습니다. 기존 UI에는 4절 어댑터를 사용하세요.

## 6. RAG, 실행 시간, 메모리

흐름은 공식 지식 검색·관할 확인 → **LLM 해석과 외부 조회 병렬 실행** → 검증된 데이터로 답변 조립입니다. 새 모듈은 요청당 LLM을 최대 1회 호출하며 실패하면 규칙 기반 결과를 반환합니다. 기존 부모 그래프의 `intake` 등은 설정에 따라 별도 LLM 호출이 있을 수 있습니다.

- SQLite **FTS5/BM25**로 작은 공식 문서 집합을 검색합니다. FAISS, 별도 벡터 서버, 로컬 모델 가중치를 적재하지 않습니다. FTS5가 없으면 token 검색으로 대체합니다.
- 시설/통 조회는 병렬 처리합니다. 경로 계산은 가까운 후보 최대 6개, 표시 결과는 최대 3개입니다. 조건에 맞는 장소가 부족하면 적은 수를 반환합니다.
- 캐시: 서비스 목록 1시간, City 상태/실패 60초, EPL·시 경계 24시간, OSM 10분. HTTP 429의 `Retry-After`는 provider 단위로 지키며 대기 sleep을 하지 않습니다.
- 공개 데이터 캐시는 최대 256행과 약 8 MiB의 JSON payload를 유지합니다. SQLite 파일/WAL과 인덱스 공간까지 포함한 총 디스크 크기 제한은 아닙니다. 메모리·속도 벤치마크를 측정했다는 의미도 아닙니다.
- 외부 응답은 2 MB에서 중단하고 요청별 시간 제한을 둡니다. 사용자 설명은 LLM에 전달되지만 지도/도시 조회에는 좌표 등 필요한 값만 사용하며, 이 캐시에 사용자 설명이나 API 키를 저장하지 않습니다.

`ORS_API_KEY`가 있으면 보행 경로 API가 계산한 시간과 알려진 snap 거리 여유를 포함해 10분 이내 후보를 고릅니다. 없으면 직선거리에 근거한 **추정값**이며 `route_verified=false`, `walking_minutes=null`, `within_10_min_walk=null`입니다. 실제 접근 가능성, 날씨, 개방 시간은 별도 확인이 필요합니다.

EPL 도서관은 **쓰레기통이 확인된 장소가 아닙니다**. 직원에게 확인하도록 표시합니다. OSM 통도 현재 상태가 확인된 통은 아닙니다. 가구·가정 쓰레기·위험물·주사기를 일반 공공 통으로 옮기도록 안내하지 않습니다. 사진은 현재 새 모듈에서 분석하지 않습니다.

## 7. 테스트와 확인 범위

```bash
PYTHONPATH="$PWD" uv --directory backend run python -m unittest agent.test_agent -v
uv --directory backend run pytest
```

첫 번째는 새 모듈의 테스트, 두 번째는 팀원의 기존 백엔드 테스트입니다. 새 모듈의 **34개 테스트가 통과**했으며 경계, 위험물, API 실패, 구조화 결과, 캐시, 경로와 fallback을 mock 데이터로 확인합니다. 원본 백엔드 저장소는 이 작업 환경에 없으므로 두 번째 명령은 실제 저장소에서 실행해야 합니다.

실시간 확인에서는 Edmonton 내부/외부 경계와 EPL Stanley A. Milner 위치를 확인했습니다. Open311 서버는 응답했으나 익명 서비스 목록은 빈 배열이어서 **사용 가능한 서비스 목록 접근은 검증되지 않았습니다**. 환경에 따라 403 보호 응답도 나타났습니다. OSM은 실제 확인 환경에서 timeout이 발생했습니다. Groq와 ORS는 실제 키가 없어 mock 검증만 했습니다. 따라서 “현재 주변 통 3개가 실제 검증됨”을 보장하지 않습니다.

## 8. Docker를 사용할 때

현재 팀원 Compose는 `backend/`만 build context로 사용하므로 새 형제 폴더가 자동 포함되지 않습니다. API와 worker 양쪽의 `build`, `env_file`만 다음과 같이 바꾸고 기존 DB 설정, volumes, command 등은 유지합니다.

```yaml
build:
  context: .
  dockerfile: backend/Dockerfile
env_file:
  - path: ./backend/.env
    required: false
  - path: ./agent/.env
    required: true
```

의존성을 `uv add`로 갱신한 후 `backend/Dockerfile`은 다음처럼 **필요한 소스만** 복사할 수 있습니다. `.env`나 생성 SQLite 파일을 이미지에 넣지 않습니다.

```dockerfile
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.8.17 /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project --extra openai --extra anthropic --extra postgres --extra aws
COPY backend/app ./app
COPY backend/seed ./seed
COPY agent/__init__.py ./agent/__init__.py
COPY api/__init__.py api/main.py ./api/
COPY database/__init__.py database/knowledge.json ./database/
ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
```

루트 build context의 `.dockerignore`에도 `.env`, `.venv`, 생성 DB, `__pycache__` 등을 제외하면 업로드되는 build context를 줄일 수 있습니다. 기존 `backend/.dockerignore`만으로는 루트 context 전체를 제어하지 못합니다. 새 캐시는 없어져도 다시 만들 수 있으며 앱의 신고 DB를 대체하지 않습니다.

## 공식 출처

| 목적 | 출처 |
|---|---|
| 311 안내·신고 | [City 311](https://www.edmonton.ca/programs_services/311-city-services), [신고 웹사이트](https://311.edmonton.ca/) |
| API 접근 신청 | [Open311 application](https://311.edmonton.ca/open311/app_requests/new) |
| 무단 투기 | [Illegal dumping](https://www.edmonton.ca/city_government/bylaws/illegal-dumping) |
| 안전한 청소 | [Volunteer safety](https://www.edmonton.ca/programs_services/graffiti_litter/cccu-volunteer-safety) |
| 주사기·사유지 연락처 | [Safe needle disposal](https://www.edmonton.ca/programs_services/graffiti_litter/safe-needle-disposal) |
| 공공 통 사용 | [Public-space waste container criteria](https://www.edmonton.ca/programs_services/garbage_waste/public-space-waste-container-placement-criteria) |
| 시 경계 | [City boundary dataset](https://data.edmonton.ca/Administrative/City-of-Edmonton-Corporate-Boundary-current-/qqvh-dp5m) |
| EPL 위치 | [Official branch dataset](https://data.edmonton.ca/resource/jn25-zspi.json) |
| 지도 통 위치 | [OpenStreetMap attribution](https://www.openstreetmap.org/copyright) |
| 보행 경로 | [openrouteservice](https://openrouteservice.org/) |

지식 문서의 검토 날짜와 원문 링크는 `database/knowledge.json`에 있습니다. 안내가 변경되면 해당 파일을 갱신하면 다음 실행 때 검색 인덱스가 갱신됩니다.
