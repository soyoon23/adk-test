# 1️⃣ 네가 처음부터 일관되게 요구한 것 (요구사항 정리)

## A. 기술 스택/환경

* **Google ADK (Python)**
* **LiteLLM Proxy 경유**
* **Ollama 로컬 모델**
* OpenAI 호환(Chat Completions) 인터페이스
* system prompt / instruction을 **최대한 내 마음대로 통제**하고 싶음

## B. 구조적 요구

* **Long-horizon task** (Plan → Act → Replan)
* 단발성 질의가 아니라 **여러 단계에 걸쳐 목표 달성**
* 중간에 막히면 재계획 가능해야 함
* ADK 기본 agent/tutorial 구조를 활용하고 싶음

## C. 범용성 요구 (매우 중요)

* 특정 도메인 한정 ❌
* **리서치 / 문서작성**이 주 타겟이지만:

  * 문서
  * 구조화된 데이터(JSON/CSV)
  * 이미지 파일
  * 텍스트
  * 코드/로그
    → **모든 산출물 타입을 커버**
* 나중에:

  * Plan-and-Act
  * DAG/Workflow
  * Swarm
  * Hierarchical agent
  * Critic / Verifier
    같은 **여러 agent 패턴을 끼워 넣을 수 있는 구조**

---

# 2️⃣ ADK 관련해서 우리가 확정한 사실들

## ✅ Google ADK + LiteLLM + Ollama 가능 여부

* 가능
* LiteLLM Proxy를 OpenAI-compatible endpoint로 사용
* ADK는 모델-agnostic → Gemini 전용 아님

## ✅ system prompt 완전 커스터마이즈?

* **완전 제거/조회는 불가**
* 하지만:

  * `before_model_callback`에서
  * `llm_request.config.system_instruction`을
  * **매 호출마다 강제로 덮어쓰기**
    → **체감상 거의 100% 통제 가능**

이 방식은 이후 모든 설계의 전제 조건으로 확정됨.

---

# 3️⃣ 내가 제안한 핵심 방향 (요약)

> ❗ 결론부터 말하면
> **“범용성 + 확장성 + long-horizon 안정성”**을 동시에 만족하려면
> **에이전트 구조보다 ‘코어 데이터 모델 + 정책 분리’가 중요**

그래서 아래 3-layer 구조를 제안했어.

---

# 4️⃣ 최종 추천 아키텍처 (정리본)

## 🧱 Layer 1 — 범용 코어 (절대 안 바뀌는 부분)

### 1) Artifact 중심 설계 (모든 산출물 통일)

* 문서 / JSON / 이미지 / 파일 / 코드 전부:
  → **Artifact 객체**로 통일
* LLM은 직접 결과물을 “소유”하지 않음
* 툴이 생성 → ArtifactStore에 저장 → ID만 공유

👉 이유:

* long-horizon에서 컨텍스트 폭발 방지
* 멀티모달/파일 처리 자연스럽게 확장
* 재현성, 디버깅, 버전 관리 쉬움

---

### 2) Step(Task) 스키마를 도메인 중립으로 고정

* 모든 작업은 `Step`이라는 동일한 단위
* inputs/outputs는 artifact_id
* type은 확장 가능 (gather, analyze, draft, render 등)
* acceptance(완료 조건), budget(툴 호출 제한) 포함

👉 이유:

* 리서치/문서/데이터/이미지 모두 동일한 실행 루프 가능
* “왜 실패했는지” 구조적으로 남음

---

## 🧠 Layer 2 — Policy / Strategy 플러그인 (여기가 확장 포인트)

이게 **네가 원한 “여러 agent 패턴을 집어넣는 핵심”**이야.

### 4가지 정책 인터페이스로 분리

1. **PlanningPolicy**

   * DAG/HTN 플래너
   * Swarm 제안형 플래너
   * Hierarchical delegation
   * Tree-of-Thought
     👉 *언제든 교체 가능*

2. **ActingPolicy**

   * ReAct 스타일
   * 단일 step executor
   * 멀티툴 파이프라인

3. **QualityPolicy**

   * Critic / Verifier
   * 출처 검증
   * 요구사항 체크
   * 실패 원인 분석 후 리플랜 트리거

4. **SelectionPolicy**

   * 다음 step 선택 로직
   * 우선순위/리스크/정보가치 기반

👉 핵심:

* **Orchestrator 코드는 안 바꿈**
* policy만 갈아끼워서 패턴 변경

---

## 🔁 Layer 3 — Orchestrator (상태 머신)

Orchestrator는 **아무 똑똑한 판단도 안 함**
그냥 이 루프만 반복:

1. 계획 업데이트
2. 다음 step 선택
3. step 실행
4. 상태 반영
5. 품질 게이트
6. 종료 조건 확인

👉 이게 가능한 이유:

* 판단은 전부 policy/agent에게 위임
* Orchestrator는 **엔진** 역할만

---

# 5️⃣ 우리가 비교·검토한 agent 패턴 정리

| 패턴           | 역할       | 평가              |
| ------------ | -------- | --------------- |
| DAG / HTN    | 기본 플래닝   | ⭐⭐⭐⭐⭐ (안정·재현성)  |
| Plan-and-Act | 실행 안정성   | ⭐⭐⭐⭐⭐           |
| Swarm        | 막힘 탈출/창의 | ⭐⭐⭐⭐ (조건부 추천)   |
| Hierarchical | 병렬/확장    | ⭐⭐⭐⭐            |
| Blackboard   | 복잡 문제    | ⭐⭐⭐ (운영 난이도 높음) |
| Event/Queue  | 대규모 운영   | ⭐⭐⭐⭐ (초기엔 오버킬)  |

### 최종 추천 조합

> **DAG/HTN + Plan-and-Act + Verifier 게이트**
>
> * Swarm은 “막혔을 때만 옵션으로”

---

# 6️⃣ 지금까지 합의된 “설계 원칙” 요약

* ❌ 에이전트 수 늘리기부터 하지 않는다
* ❌ 특정 도메인 전제하지 않는다
* ✅ 산출물은 artifact로 통일
* ✅ 판단은 policy로 분리
* ✅ ADK는 orchestration 프레임워크로만 사용
* ✅ system prompt는 콜백으로 강제 통제

---

# 7️⃣ 다음 단계 제안 (선택지)

이제 여기서 **딱 3가지 루트** 중 하나로 갈 수 있어:

1. **실제 동작하는 베이스 코드**

   * ArtifactStore
   * Step 스키마
   * Planner/Actor/Verifier ADK Agent
   * LiteLLM Proxy 연결
   * system override 콜백 포함

2. **설계 문서화**

   * UML/다이어그램
   * 상태 전이표
   * policy 인터페이스 정의서

3. **특정 패턴 집중 구현**

   * 예: DAG + Verifier만 완성
   * 예: Swarm 플러그인 추가 예제

원하면
👉 **“1번부터 바로 코드로”** 가는 게 제일 자연스러워.
다음 메시지에 **“베이스 코드부터”**라고만 써줘도 바로 이어서 만들어줄게.