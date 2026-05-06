const express = require('express');
const path = require('path');
const { Pool } = require('pg');
require('dotenv').config();

const app = express();
const PORT = process.env.PORT || 3000;

const pool = new Pool({
  host: process.env.PG_HOST,
  port: Number(process.env.PG_PORT),
  user: process.env.PG_USER,
  password: process.env.PG_PASSWORD,
  database: process.env.PG_DB,
});

app.set('view engine', 'ejs');
app.set('views', path.join(__dirname, 'views'));
app.use('/static', express.static(path.join(__dirname, 'public')));

const PAGE_SIZE = 10;

app.get('/', async (req, res, next) => {
  try {
    const page = Math.max(1, parseInt(req.query.page, 10) || 1);
    const category = (req.query.category || '').trim();
    const q = (req.query.q || '').trim();

    const where = [];
    const params = [];
    if (category) {
      params.push(category);
      where.push(`category = $${params.length}`);
    }
    if (q) {
      params.push(`%${q}%`);
      where.push(`(subject ILIKE $${params.length} OR sender ILIKE $${params.length} OR body ILIKE $${params.length})`);
    }
    const whereSql = where.length ? `WHERE ${where.join(' AND ')}` : '';

    const totalRes = await pool.query(
      `SELECT COUNT(*)::int AS n FROM classified_emails ${whereSql}`,
      params
    );
    const total = totalRes.rows[0].n;
    const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
    const currentPage = Math.min(page, totalPages);
    const offset = (currentPage - 1) * PAGE_SIZE;

    const listRes = await pool.query(
      `SELECT id, email_id, sender, subject, category, confidence, classified_at
       FROM classified_emails
       ${whereSql}
       ORDER BY classified_at DESC NULLS LAST, id DESC
       LIMIT ${PAGE_SIZE} OFFSET ${offset}`,
      params
    );

    const catRes = await pool.query(
      `SELECT category, COUNT(*)::int AS n
       FROM classified_emails
       WHERE category IS NOT NULL AND category <> ''
       GROUP BY category ORDER BY n DESC, category ASC`
    );

    res.render('list', {
      rows: listRes.rows,
      total,
      currentPage,
      totalPages,
      pageSize: PAGE_SIZE,
      category,
      q,
      categories: catRes.rows,
    });
  } catch (e) {
    next(e);
  }
});

app.get('/post/:id', async (req, res, next) => {
  try {
    const id = parseInt(req.params.id, 10);
    if (!Number.isFinite(id)) return res.status(400).send('Invalid id');

    const r = await pool.query(
      `SELECT * FROM classified_emails WHERE id = $1`,
      [id]
    );
    if (r.rowCount === 0) return res.status(404).render('error', { message: '게시글을 찾을 수 없습니다.' });

    const navR = await pool.query(
      `SELECT
         (SELECT id FROM classified_emails WHERE id < $1 ORDER BY id DESC LIMIT 1) AS prev_id,
         (SELECT id FROM classified_emails WHERE id > $1 ORDER BY id ASC LIMIT 1) AS next_id`,
      [id]
    );

    res.render('detail', { row: r.rows[0], nav: navR.rows[0] });
  } catch (e) {
    next(e);
  }
});

app.use((err, req, res, _next) => {
  console.error(err);
  res.status(500).render('error', { message: err.message });
});

app.listen(PORT, () => {
  console.log(`게시판이 http://localhost:${PORT} 에서 실행 중입니다`);
});
