# 회의록 요약/분석 애플리케이션 - 단계별 프롬프트

> 각 프롬프트를 순서대로 AI에게 입력하면 애플리케이션이 단계적으로 완성됩니다.
> `========` 구분자로 단계를 구별합니다.

---

## ======== 1단계: 프로젝트 초기화 ========

```
회의록 파일(.txt, .pdf, .docx)을 업로드하면 OpenAI API로 자동 요약/분석하는 웹 애플리케이션을 만들려고 해.

먼저 프로젝트를 초기화해줘.

프로젝트 디렉토리: file-manager/

1. package.json을 생성해줘:
   - name: "meeting-minutes-analyzer"
   - scripts: start → "node server.js", dev → "node --watch server.js"
   - dependencies: express, dotenv, multer, pdf-parse, mammoth, openai, uuid

2. .env 파일 생성:
   - OPENAI_API_KEY=your_openai_api_key_here
   - PORT=3000

3. .gitignore 생성:
   - node_modules/, .env, uploads/*, data/* (각각 .gitkeep은 유지)

4. 필요한 디렉토리 구조를 미리 만들어줘:
   - public/css/, public/js/, routes/, services/, uploads/, data/

5. npm install을 실행해줘.
```

---

## ======== 2단계: Express 서버 설정 ========

```
file-manager/ 프로젝트에 Express 서버 엔트리포인트(server.js)를 만들어줘.

요구사항:
- dotenv를 로드해서 환경변수를 사용
- uploads/, data/ 디렉토리가 없으면 자동 생성
- express.json() 미들웨어 등록
- public/ 폴더를 정적 파일로 서빙
- /api/meetings 경로에 라우터 연결 (routes/meetings.js에서 가져옴)
- process.env.PORT 또는 기본 3000번 포트에서 리스닝
- 서버 시작 시 콘솔에 URL 출력

아직 routes/meetings.js는 없으니, 빈 라우터로 임시 파일을 만들어서 서버가 정상 실행되도록 해줘.
서버를 실행해서 http://localhost:3000 접속이 되는지 확인해줘.
```

---

## ======== 3단계: 파일 파싱 서비스 ========

```
services/fileParser.js를 만들어줘. 업로드된 파일에서 텍스트를 추출하는 서비스야.

요구사항:
- parseFile(filePath) 함수를 export
- 파일 확장자에 따라 분기 처리:
  - .txt → fs.readFileSync로 UTF-8 직접 읽기
  - .pdf → pdf-parse 라이브러리로 텍스트 추출
  - .docx → mammoth.extractRawText로 텍스트 추출
- 지원하지 않는 확장자면 에러를 throw
- async 함수로 구현 (pdf-parse, mammoth 모두 비동기)
```

---

## ======== 4단계: 업로드 및 CRUD API ========

```
routes/meetings.js에 회의록 관련 API 라우트를 구현해줘.
3단계에서 만든 services/fileParser.js를 사용해.

multer 설정:
- 저장 경로: uploads/ 디렉토리
- 파일명: 타임스탬프-원본파일명 형식
- 파일 크기 제한: 10MB
- 허용 확장자: .txt, .pdf, .docx만 허용 (fileFilter)

데이터 저장:
- 각 회의록은 data/{uuid}.json 파일로 저장
- uuid 패키지로 고유 ID 생성

구현할 API 엔드포인트:

1. POST /api/meetings/upload
   - multer로 파일 수신 (필드명: "file")
   - fileParser.parseFile()로 텍스트 추출
   - JSON 데이터 생성 후 data/ 폴더에 저장
   - 저장 형식: { id, fileName, fileType, storedFileName, uploadedAt, rawText, analysis: null, analyzed: false }
   - 응답: { id, fileName, uploadedAt }

2. GET /api/meetings
   - data/ 폴더의 모든 .json 파일 읽기
   - 각 항목에서 id, fileName, fileType, uploadedAt, analyzed만 반환
   - uploadedAt 기준 최신순 정렬

3. GET /api/meetings/:id
   - 해당 ID의 JSON 파일 전체 내용 반환
   - 없으면 404

4. DELETE /api/meetings/:id
   - data/{id}.json 삭제
   - uploads/에 저장된 원본 파일도 삭제
   - 없으면 404
```

---

## ======== 5단계: AI 분석 서비스 ========

```
services/aiAnalyzer.js를 만들어줘. OpenAI API를 사용해서 회의록 텍스트를 분석하는 서비스야.

요구사항:
- openai 패키지 사용 (process.env.OPENAI_API_KEY)
- OpenAI 클라이언트는 lazy 초기화해줘 (API 키 없이도 서버가 시작될 수 있도록)
- analyzeText(rawText) 함수를 export

분석 로직:
- 입력 텍스트가 길면 12,000자로 잘라서 전달
- 모델: gpt-4o
- temperature: 0.3
- response_format: { type: 'json_object' } 사용

시스템 프롬프트에서 아래 JSON 형식으로 응답하도록 지시:
{
  "summary": "회의 핵심 내용 3~5문장 요약",
  "agendas": ["핵심 안건 목록"],
  "decisions": ["결정 사항 목록"],
  "actionItems": [{ "task": "내용", "assignee": "담당자(미정)", "deadline": "기한(미정)" }],
  "attendees": ["참석자 목록 (추출 불가시 빈 배열)"]
}

응답 content를 JSON.parse해서 반환.
```

---

## ======== 6단계: 분석 API 연결 ========

```
routes/meetings.js에 AI 분석 엔드포인트를 추가해줘.
5단계에서 만든 services/aiAnalyzer.js를 사용해.

추가할 API:

POST /api/meetings/:id/analyze
- 해당 ID의 회의록 JSON을 읽어서 rawText를 가져옴
- aiAnalyzer.analyzeText(rawText) 호출
- 분석 결과를 meeting.analysis에 저장하고 meeting.analyzed = true로 변경
- JSON 파일을 다시 저장
- 응답: { id, analysis }
- 회의록이 없으면 404, 분석 실패 시 500 에러와 메시지 반환
```

---

## ======== 7단계: 프론트엔드 - 메인 페이지 ========

```
프론트엔드 메인 페이지를 만들어줘. 순수 HTML/CSS/JS로 구현하고, 프레임워크는 사용하지 마.

public/index.html:
- 헤더: "회의록 요약/분석" 타이틀
- 업로드 영역: 드래그앤드롭 가능한 영역 + 클릭으로 파일 선택
  - 안내 문구: "파일을 드래그하여 놓거나 클릭하여 업로드하세요"
  - 힌트: ".txt, .pdf, .docx 파일 지원 (최대 10MB)"
- 회의록 목록 섹션: 테이블 형태 (파일명, 형식, 업로드 일시, 분석 상태)
- 토스트 알림 영역

public/css/style.css:
- 깔끔한 모던 디자인 (메인 컬러: #1a73e8)
- .upload-area: 점선 테두리, 드래그 시 .dragover 상태 스타일
- .meetings-table: 테이블 스타일
- .badge-success (분석 완료), .badge-pending (대기 중) 배지
- .toast: 우하단 토스트 알림 (성공: 녹색, 에러: 빨간색)
- .spinner: 로딩 스피너 애니메이션
- .btn, .btn-primary, .btn-danger, .btn-secondary 버튼 스타일
- .card: 카드형 레이아웃 (상세 페이지에서도 사용)
- 반응형: 640px 이하 모바일 대응

public/js/main.js:
- 드래그앤드롭 이벤트 (dragover, dragleave, drop) + 클릭 업로드
- uploadFile(file): FormData로 POST /api/meetings/upload 호출, 업로드 중 로딩 표시
- loadMeetings(): GET /api/meetings 호출 후 테이블 렌더링
  - 파일명 클릭 시 /detail.html?id={id}로 이동
  - 분석 상태를 배지로 표시
  - 목록이 비어있으면 안내 문구 표시
- 모든 출력에 XSS 방지를 위한 HTML 이스케이프 적용
- 페이지 로드 시 자동으로 목록 조회
```

---

## ======== 8단계: 프론트엔드 - 상세 페이지 ========

```
회의록 상세 페이지를 만들어줘.

public/detail.html:
- 헤더: "회의록 요약/분석" 타이틀 + "목록으로 돌아가기" 링크
- 상세 헤더: 파일명 + "분석하기" 버튼 + "삭제" 버튼
- 분석 결과 영역 (id="analysisSection")
- 원문 텍스트 카드 (스크롤 가능, 최대 높이 400px)
- 토스트 알림 영역

public/js/detail.js:
- URL에서 ?id= 파라미터로 회의록 ID 획득
- loadMeeting(): GET /api/meetings/:id 호출
  - 파일명 표시, 원문 텍스트 표시
  - 이미 분석된 경우 분석 결과를 렌더링하고 버튼을 "다시 분석하기"로 변경

- "분석하기" 버튼 클릭 시:
  - 버튼 비활성화 + "분석 중..." 텍스트
  - 분석 영역에 로딩 스피너 표시
  - POST /api/meetings/:id/analyze 호출
  - 성공 시 분석 결과를 카드형으로 렌더링:
    - 요약 카드
    - 핵심 안건 카드 (리스트)
    - 결정 사항 카드 (리스트)
    - 액션 아이템 카드 (task + 담당자/기한 메타 표시)
    - 참석자 카드 (리스트)
  - 실패 시 에러 토스트

- "삭제" 버튼 클릭 시:
  - confirm 대화상자로 확인
  - DELETE /api/meetings/:id 호출
  - 성공 시 메인 페이지(/)로 이동

- 모든 출력에 HTML 이스케이프 적용

7단계에서 만든 style.css를 공유하므로, 이미 정의된 .card, .btn, .toast 등의 클래스를 활용해줘.
```

---
