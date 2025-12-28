# 8. 에이전트 배포 및 확장

```text
Role:
너는 MCP(Model Context Protocol)에 정통한 시니어 AI 엔지니어다.
LangGraph 0.5.x 기반으로 구현된 07폴더에 작성된 Deep Research Agent를
MCP Server로 배포 가능하도록 08폴더에 변환해야 한다.

Context:
- 현재 코드에는 다음 구성 요소가 이미 구현되어 있다:
  - LangGraph StateGraph (Planner → Searcher → Extractor → Verifier → Writer)
  - run_research(question), invoke_research(question) 함수
  - ResearchState, SearchResult, Fact, VerifiedFact 타입 정의
- 이 코드는 로컬/CLI 실행은 가능하지만,
  아직 MCP Server 형태로 노출되어 있지 않다.

Goal:
이 Deep Research Agent를
Cursor AI 및 다른 Agent가 호출할 수 있는
MCP Server로 만든다.

MCP Server Requirements:
1. MCP Server 이름은 "deep-research-agent"로 한다.
2. MCP Tool을 최소 1개 정의한다.
   - Tool name: deep_research
   - Input:
       - question (string): 연구 질문
   - Output:
       - question
       - summary (final_report)
       - verified_facts
3. Tool 내부에서는
   - 기존 run_research 또는 invoke_research 함수를 그대로 재사용한다.
   - verbose 출력은 비활성화한다.
4. MCP Server는 표준 JSON 입출력을 사용한다.
5. 서버 실행 엔트리포인트를 명확히 제공한다.
   (python mcp_server.py 로 실행 가능해야 함)

Implementation Requirements:
- 기존 LangGraph 코드(graph.py, nodes.py, state.py)는 수정하지 않는다.
- MCP Server 전용 파일(mcp_server.py)을 새로 작성한다.
- mcp Python SDK를 사용한다.
- 함수와 Tool에는 간단한 주석을 추가한다.
- 실제 실행 가능한 코드 형태로 작성한다.

Output Format:
1. MCP Server 개요 설명 (짧게)
2. mcp_server.py 전체 코드
3. 실행 방법 (CLI)
4. Python에서 MCP Server를 호출하는 mcp_client.py 코드


Constraints:
- 불필요한 이론 설명은 하지 않는다.
- MCP 개념 설명보다 “바로 실행 가능한 결과물”에 집중한다.
- 추상화하지 말고, 현재 코드 구조에 정확히 맞춰 작성한다.
```

```text
신뢰성 있는 결과를 도출하기 위해 검증 가능한 도구 있다면 도구를 사용하여
2026년 AI 발전 동향을 조사해줘.
```