CREATE TABLE users (
  id SERIAL PRIMARY KEY,
  tg_id BIGINT UNIQUE NOT NULL,
  username TEXT,
  balance BIGINT DEFAULT 0,
  total_deposit BIGINT DEFAULT 0,
  free_given BOOLEAN DEFAULT FALSE,
  free_locked BOOLEAN DEFAULT TRUE,
  rounds_played INTEGER DEFAULT 0
);

CREATE TABLE rounds (
  id SERIAL PRIMARY KEY,
  chat_id BIGINT NOT NULL,
  started_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
  sequence TEXT, -- e.g. "4,5,7,8,9,1"
  status TEXT DEFAULT 'running', -- running|finished|cancelled
  override TEXT DEFAULT NULL -- 'Nho','Lon','Chan','Le' if admin forced
);

CREATE TABLE bets (
  id SERIAL PRIMARY KEY,
  round_id INTEGER REFERENCES rounds(id) ON DELETE CASCADE,
  user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
  bet_type TEXT NOT NULL, -- N|L|C|Le|S (S=single number)
  bet_value TEXT, -- for S: number(s) like '1' or '91' etc
  amount BIGINT NOT NULL,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
  paid BOOLEAN DEFAULT FALSE
);

CREATE TABLE groups (
  chat_id BIGINT PRIMARY KEY,
  approved BOOLEAN DEFAULT FALSE,
  running BOOLEAN DEFAULT FALSE
);

CREATE TABLE codes (
  id SERIAL PRIMARY KEY,
  code TEXT UNIQUE,
  amount BIGINT NOT NULL,
  rounds_required INTEGER DEFAULT 0,
  used_by INTEGER REFERENCES users(id),
  used_at TIMESTAMP WITH TIME ZONE
);
