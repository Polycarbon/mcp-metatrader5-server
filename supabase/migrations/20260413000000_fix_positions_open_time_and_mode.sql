-- Fix 1: Add open_time column to positions (agent sends MT5 position open time)
alter table positions add column if not exists open_time timestamptz;

-- Fix 2: Drop restrictive mode CHECK on bot_status (dashboard uses "AI Autonomous" etc.)
alter table bot_status drop constraint if exists bot_status_mode_check;
