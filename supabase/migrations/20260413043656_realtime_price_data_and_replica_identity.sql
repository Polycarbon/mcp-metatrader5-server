-- Add price_data to Realtime publication
-- (bot_status, commands, account_snapshot, equity_snapshots, positions already added)
ALTER PUBLICATION supabase_realtime ADD TABLE public.price_data;

-- Set REPLICA IDENTITY FULL on all Realtime tables so UPDATE/DELETE events
-- include the complete row, not just the primary key.
ALTER TABLE public.bot_status       REPLICA IDENTITY FULL;
ALTER TABLE public.commands         REPLICA IDENTITY FULL;
ALTER TABLE public.account_snapshot REPLICA IDENTITY FULL;
ALTER TABLE public.equity_snapshots REPLICA IDENTITY FULL;
ALTER TABLE public.positions        REPLICA IDENTITY FULL;
ALTER TABLE public.price_data       REPLICA IDENTITY FULL;
