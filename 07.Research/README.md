## 07. 검증하는 에이전트

```text
07폴더에 다음의 내용을 구현해줘.

Role:
너는 LangGraph와 Agentic AI에 능숙한 시니어 AI 엔지니어다.
ChatGPT의 Deep Research 기능을
LangGraph 기반 멀티 에이전트 그래프로 구현해야 한다.

Context:
- 실행 환경은 Cursor AI이다.
- LangGraph 최신 안정 버전(0.5.x 계열)을 사용한다.
- LLM은 OpenAI 또는 Claude로 교체 가능해야 한다.
- Deep Research는 “단일 프롬프트”가 아니라
  “상태(State) + 노드(Node) + 그래프” 구조로 설계한다.

Goal:
사용자의 질문을 입력으로 받아,
웹 검색 → 사실 추출 → 교차 검증 → 최종 보고서 생성을 수행하는
Deep Research 에이전트를 LangGraph로 구현하라.

Architecture Requirements:
다음 그래프 구조를 반드시 따른다.

1. Planner Node
   - 사용자 질문을 분석하여
     연구 계획과 검색 쿼리를 생성한다.

2. Searcher Node
   - 웹 검색 결과를 수집한다.
   - 실제 API 연동이 어려우면 mock 구조로 작성하되,
     실제 API로 교체 가능하게 설계한다.

3. Extractor Node
   - 검색 결과에서
     사실(fact)만 추출한다.
   - 해석이나 의견은 포함하지 않는다.

4. Verifier Node
   - 여러 출처에서 공통으로 확인된 사실만 남긴다.
   - 불확실하거나 충돌하는 정보는 명확히 표시한다.

5. Writer Node
   - 검증된 사실을 바탕으로
     사람이 읽을 수 있는 최종 리서치 보고서를 작성한다.
   - 사실과 해석을 구분한다.

State Design:
공유 상태(State)는 TypedDict로 정의하고,
다음 필드를 반드시 포함한다.

- question
- plan
- search_results
- extracted_facts
- verified_facts
- final_report

Implementation Requirements:
- LangGraph의 StateGraph를 사용한다.
- 각 노드는 순수 함수 형태로 작성한다.
- graph.compile()까지 포함한 완성 코드를 제공한다.
- 실행 예시(invoke) 코드도 포함한다.
- 코드에 간단한 주석을 추가한다.

Constraints:
- 불필요한 설명은 최소화한다.
- 설계 설명은 코드 앞부분에 짧게 정리한다.
- “Deep Research 흉내”가 아니라
  실제 검증 구조가 드러나도록 작성한다.

Output:
1. 전체 아키텍처 요약 (텍스트)
2. LangGraph 기반 Deep Research 전체 코드
3. 실행 예시 코드
```

```text
2026년 AI 발전 동향은?
```