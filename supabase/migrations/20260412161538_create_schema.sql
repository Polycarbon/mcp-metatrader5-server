-- PeterQuant Trading Dashboard - Database Schema (additive)
-- Existing tables: deals, equity_snapshots (untouched)
-- New tables: bot_status, commands, positions, price_data

-- ============================================================
-- 1. bot_status - Tracks the trading bot's current state
-- ============================================================
create table if not exists bot_status (
  id bigint generated always as identity primary key,
  status text not null default 'offline' check (status in ('online', 'offline', 'error')),
  mode text not null default 'idle',
  symbol text,
  timeframe text,
  last_heartbeat timestamptz not null default now(),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table bot_status enable row level security;

-- ============================================================
-- 2. commands - Queue for web -> agent command relay
-- ============================================================
create table if not exists commands (
  id bigint generated always as identity primary key,
  command text not null,
  payload jsonb default '{}'::jsonb,
  status text not null default 'pending' check (status in ('pending', 'executed', 'failed')),
  created_at timestamptz not null default now(),
  executed_at timestamptz
);

alter table commands enable row level security;

-- ============================================================
-- 3. positions - Current open trading positions
--    (deals table already holds historical trades; this is live)
-- ============================================================
create table if not exists positions (
  id bigint generated always as identity primary key,
  ticket bigint not null unique,
  symbol text not null,
  type text not null check (type in ('buy', 'sell')),
  volume numeric not null,
  open_price numeric not null,
  current_price numeric not null default 0,
  profit numeric not null default 0,
  open_time timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table positions enable row level security;

-- ============================================================
-- 4. price_data - OHLCV candle data for charting
-- ============================================================
create table if not exists price_data (
  id bigint generated always as identity primary key,
  symbol text not null,
  timeframe text not null,
  open numeric not null,
  high numeric not null,
  low numeric not null,
  close numeric not null,
  volume numeric not null default 0,
  time timestamptz not null,
  created_at timestamptz not null default now()
);

-- Prevent duplicate candles for the same symbol/timeframe/time
create unique index if not exists price_data_symbol_tf_time_idx on price_data (symbol, timeframe, time);

alter table price_data enable row level security;

-- ============================================================
-- Indexes
-- ============================================================
create index if not exists bot_status_heartbeat_idx on bot_status (last_heartbeat desc);
create index if not exists commands_pending_idx on commands (status, created_at) where status = 'pending';
create index if not exists positions_symbol_idx on positions (symbol);
create index if not exists price_data_query_idx on price_data (symbol, timeframe, time desc);

-- Index on existing equity_snapshots for dashboard queries
create index if not exists equity_snapshots_captured_idx on equity_snapshots (captured_at desc);

-- ============================================================
-- RLS Policies - Authenticated users get full access
-- (Single-user app; Windows agent uses service_role key)
-- ============================================================
create policy "Authenticated users can manage bot_status"
  on bot_status for all
  to authenticated
  using (true)
  with check (true);

create policy "Authenticated users can manage commands"
  on commands for all
  to authenticated
  using (true)
  with check (true);

create policy "Authenticated users can manage positions"
  on positions for all
  to authenticated
  using (true)
  with check (true);

create policy "Authenticated users can manage price_data"
  on price_data for all
  to authenticated
  using (true)
  with check (true);

-- RLS on existing tables (if not already enabled)
alter table deals enable row level security;
alter table equity_snapshots enable row level security;

create policy "Authenticated users can manage deals"
  on deals for all
  to authenticated
  using (true)
  with check (true);

create policy "Authenticated users can manage equity_snapshots"
  on equity_snapshots for all
  to authenticated
  using (true)
  with check (true);

-- ============================================================
-- Enable Realtime for dashboard-critical tables
-- ============================================================
alter publication supabase_realtime add table commands;
alter publication supabase_realtime add table bot_status;
alter publication supabase_realtime add table equity_snapshots;
alter publication supabase_realtime add table positions;
