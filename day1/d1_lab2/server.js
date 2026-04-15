const express = require('express');
const Database = require('better-sqlite3');
const path = require('path');
const { EventEmitter } = require('events');

const app = express();
const PORT = 3030;

// ---------------------------------------------------------------------------
// 이벤트 버스
// ---------------------------------------------------------------------------
const eventBus = new EventEmitter();

// ---------------------------------------------------------------------------
// Middleware
// ---------------------------------------------------------------------------
app.use(express.json({ type: 'application/json' }));
app.use(express.urlencoded({ extended: true }));
app.use(express.static(path.join(__dirname, 'public')));

// 모든 JSON 응답에 UTF-8 charset 명시
app.use((req, res, next) => {
  res.set('Content-Type', 'application/json; charset=utf-8');
  next();
});

// ---------------------------------------------------------------------------
// Database setup
// ---------------------------------------------------------------------------
const db = new Database(path.join(__dirname, 'inquiries.db'));
db.pragma('journal_mode = WAL');

db.exec(`
  CREATE TABLE IF NOT EXISTS inquiries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT '일반문의',
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    password TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT '접수',
    reply TEXT,
    ai_category TEXT,
    ai_sentiment TEXT,
    ai_urgency TEXT,
    ai_keywords TEXT,
    ai_summary TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
  )
`);

// 기존 테이블에 AI 컬럼이 없으면 추가
const columns = db.prepare("PRAGMA table_info(inquiries)").all().map(c => c.name);
const aiColumns = {
  ai_category: 'TEXT',
  ai_sentiment: 'TEXT',
  ai_urgency: 'TEXT',
  ai_keywords: 'TEXT',
  ai_summary: 'TEXT',
};
for (const [col, type] of Object.entries(aiColumns)) {
  if (!columns.includes(col)) {
    db.exec(`ALTER TABLE inquiries ADD COLUMN ${col} ${type}`);
  }
}

// ---------------------------------------------------------------------------
// SSE: 이벤트 스트림 엔드포인트
// ---------------------------------------------------------------------------
const sseClients = new Set();

app.get('/api/events', (req, res) => {
  res.writeHead(200, {
    'Content-Type': 'text/event-stream',
    'Cache-Control': 'no-cache',
    'Connection': 'keep-alive',
    'X-Accel-Buffering': 'no',
  });

  // 연결 직후 heartbeat 전송
  res.write('event: connected\ndata: {"status":"connected"}\n\n');

  const onInquiry = (data) => {
    res.write(`event: new_inquiry\ndata: ${JSON.stringify(data)}\n\n`);
  };

  eventBus.on('new_inquiry', onInquiry);
  sseClients.add(res);

  console.log(`[SSE] 클라이언트 연결 (총 ${sseClients.size}개)`);

  // 30초마다 heartbeat
  const heartbeat = setInterval(() => {
    res.write(': heartbeat\n\n');
  }, 30000);

  req.on('close', () => {
    eventBus.off('new_inquiry', onInquiry);
    sseClients.delete(res);
    clearInterval(heartbeat);
    console.log(`[SSE] 클라이언트 연결 해제 (총 ${sseClients.size}개)`);
  });
});

// ---------------------------------------------------------------------------
// API: 문의 목록 조회
// ---------------------------------------------------------------------------
app.get('/api/inquiries', (req, res) => {
  const page = parseInt(req.query.page) || 1;
  const limit = 10;
  const offset = (page - 1) * limit;
  const search = req.query.search || '';

  let countSql = 'SELECT COUNT(*) as total FROM inquiries';
  let listSql = 'SELECT id, name, category, title, status, created_at FROM inquiries';

  const params = [];
  if (search) {
    const where = ' WHERE title LIKE ? OR content LIKE ?';
    countSql += where;
    listSql += where;
    params.push(`%${search}%`, `%${search}%`);
  }

  listSql += ' ORDER BY id DESC LIMIT ? OFFSET ?';

  const total = db.prepare(countSql).get(...params).total;
  const inquiries = db.prepare(listSql).all(...params, limit, offset);
  const totalPages = Math.ceil(total / limit);

  res.json({ inquiries, total, page, totalPages });
});

// ---------------------------------------------------------------------------
// API: 문의 작성 + 이벤트 발행
// ---------------------------------------------------------------------------
app.post('/api/inquiries', (req, res) => {
  const { name, email, category, title, content, password } = req.body;

  if (!name || !email || !title || !content || !password) {
    return res.status(400).json({ error: '모든 필수 항목을 입력해주세요.' });
  }

  const stmt = db.prepare(
    'INSERT INTO inquiries (name, email, category, title, content, password) VALUES (?, ?, ?, ?, ?, ?)'
  );
  const result = stmt.run(name, email, category || '일반문의', title, content, password);
  const inquiryId = Number(result.lastInsertRowid);

  // SSE 이벤트 발행
  const eventData = {
    id: inquiryId,
    name,
    email,
    category: category || '일반문의',
    title,
    content,
    created_at: new Date().toISOString(),
  };
  eventBus.emit('new_inquiry', eventData);
  console.log(`[이벤트] 새 문의 #${inquiryId} 발행 → SSE 구독자 ${sseClients.size}개`);

  res.status(201).json({ id: inquiryId, message: '문의가 등록되었습니다.' });
});

// ---------------------------------------------------------------------------
// API: 문의 상세 조회
// ---------------------------------------------------------------------------
app.get('/api/inquiries/:id', (req, res) => {
  const inquiry = db.prepare(
    'SELECT id, name, email, category, title, content, status, reply, ai_category, ai_sentiment, ai_urgency, ai_keywords, ai_summary, created_at, updated_at FROM inquiries WHERE id = ?'
  ).get(req.params.id);

  if (!inquiry) {
    return res.status(404).json({ error: '문의를 찾을 수 없습니다.' });
  }

  res.json(inquiry);
});

// ---------------------------------------------------------------------------
// API: 문의 분석 결과 저장 (에이전트 → 서버)
// ---------------------------------------------------------------------------
app.patch('/api/inquiries/:id/analysis', (req, res) => {
  const { ai_category, ai_sentiment, ai_urgency, ai_keywords, ai_summary } = req.body;
  const id = req.params.id;

  const inquiry = db.prepare('SELECT id FROM inquiries WHERE id = ?').get(id);
  if (!inquiry) {
    return res.status(404).json({ error: '문의를 찾을 수 없습니다.' });
  }

  db.prepare(`
    UPDATE inquiries
    SET ai_category = ?, ai_sentiment = ?, ai_urgency = ?, ai_keywords = ?, ai_summary = ?, updated_at = CURRENT_TIMESTAMP
    WHERE id = ?
  `).run(ai_category, ai_sentiment, ai_urgency, ai_keywords, ai_summary, id);

  console.log(`[AI] 문의 #${id} 분석 결과 저장 완료`);
  res.json({ message: '분석 결과가 저장되었습니다.' });
});

// ---------------------------------------------------------------------------
// API: 비밀번호 확인
// ---------------------------------------------------------------------------
app.post('/api/inquiries/:id/verify', (req, res) => {
  const { password } = req.body;
  const inquiry = db.prepare('SELECT password FROM inquiries WHERE id = ?').get(req.params.id);

  if (!inquiry) {
    return res.status(404).json({ error: '문의를 찾을 수 없습니다.' });
  }

  if (inquiry.password !== password) {
    return res.status(403).json({ error: '비밀번호가 일치하지 않습니다.' });
  }

  res.json({ verified: true });
});

// ---------------------------------------------------------------------------
// API: 문의 삭제
// ---------------------------------------------------------------------------
app.delete('/api/inquiries/:id', (req, res) => {
  const { password } = req.body;
  const inquiry = db.prepare('SELECT password FROM inquiries WHERE id = ?').get(req.params.id);

  if (!inquiry) {
    return res.status(404).json({ error: '문의를 찾을 수 없습니다.' });
  }

  if (inquiry.password !== password) {
    return res.status(403).json({ error: '비밀번호가 일치하지 않습니다.' });
  }

  db.prepare('DELETE FROM inquiries WHERE id = ?').run(req.params.id);
  res.json({ message: '문의가 삭제되었습니다.' });
});

// ---------------------------------------------------------------------------
// 서버 시작
// ---------------------------------------------------------------------------
app.listen(PORT, () => {
  console.log(`서버가 http://localhost:${PORT} 에서 실행 중입니다.`);
  console.log(`SSE 이벤트 스트림: http://localhost:${PORT}/api/events`);
});
