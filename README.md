# ADK Story Agent

Google ADK(Agent Development Kit)를 사용한 멀티 에이전트 스토리 생성 워크플로우 예제입니다.

## 개요

이 프로젝트는 여러 LLM 에이전트가 협력하여 스토리를 생성하고 개선하는 워크플로우를 구현합니다.

### 워크플로우

```
┌─────────────────┐
│ StoryGenerator  │  → 초기 스토리 생성
└────────┬────────┘
         ▼
┌─────────────────┐
│ CriticReviser   │  → 비평 및 수정 (2회 반복)
│     Loop        │
└────────┬────────┘
         ▼
┌─────────────────┐
│ PostProcessing  │  → 문법 검사 + 톤 분석
│  (Sequential)   │
└────────┬────────┘
         ▼
    톤이 부정적?
     ├── Yes → 스토리 재생성
     └── No  → 완료
```

### 에이전트 구성

| Agent | 역할 |
|-------|------|
| **StoryGenerator** | 주어진 토픽으로 100단어 내외의 짧은 스토리 생성 |
| **Critic** | 스토리의 플롯/캐릭터에 대한 건설적 비평 제공 |
| **Reviser** | 비평을 바탕으로 스토리 수정 |
| **GrammarCheck** | 문법 오류 검사 |
| **ToneCheck** | 톤 분석 (positive/negative/neutral) |

## 요구사항

- Python 3.12+
- [Ollama](https://ollama.ai/) (로컬 LLM 실행)
- [uv](https://github.com/astral-sh/uv) (패키지 관리자)

## 설치

```bash
# 저장소 클론
git clone https://github.com/soyoon23/adk-test.git
cd adk-test

# 의존성 설치
uv sync
```

## LiteLLM 프록시 설정

Ollama 모델을 사용하기 위해 LiteLLM 프록시를 설정합니다.

```bash
# Ollama에서 모델 다운로드
ollama pull qwen:7b

# LiteLLM 프록시 시작
cd litellm-proxy
./start_proxy.sh
```

## 실행

```bash
# 에이전트 실행
uv run python my_agent/agent.py

# 또는 ADK CLI 사용
adk run my_agent
```

## 프로젝트 구조

```
adk-test/
├── my_agent/
│   ├── __init__.py
│   ├── agent.py          # 메인 에이전트 코드
│   └── .env              # 환경 변수 (API 키 등)
├── litellm-proxy/
│   ├── litellm_config.yaml
│   ├── start_proxy.sh
│   └── stop_proxy.sh
├── pyproject.toml
└── README.md
```

## 설정

### 환경 변수

`my_agent/.env` 파일에서 설정:

```env
GOOGLE_API_KEY=your_api_key_here
```

### LiteLLM 프록시 설정

`litellm-proxy/litellm_config.yaml`에서 모델 및 프록시 설정을 변경할 수 있습니다.

## 라이선스

Apache License 2.0
