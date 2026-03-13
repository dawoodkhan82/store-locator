-- Supabase Schema for DM Outreach Tracking
-- Run this migration in your Supabase SQL editor or via CLI

-- Users table: stores Instagram auth data
create table if not exists public.users (
    id uuid references auth.users(id) on delete cascade primary key,
    instagram_user_id text unique,
    instagram_username text,
    access_token text, -- long-lived token (encrypted at rest by Supabase)
    token_expiry timestamptz,
    page_id text, -- Facebook Page ID linked to Instagram
    created_at timestamptz default now(),
    updated_at timestamptz default now()
);

-- DM Records: per-store tracking
create table if not exists public.dm_records (
    id uuid default gen_random_uuid() primary key,
    user_id uuid references public.users(id) on delete cascade not null,
    store_key text not null,
    store_name text,
    instagram_handle text,
    instagram_url text,
    campaigns jsonb default '{"intro": {"dm1": {"sent": false}, "dm2": {"sent": false}, "dm3": {"sent": false}}, "followUp": {"sent": false}, "feedback": {"dm1": {"sent": false}, "dm2": {"sent": false}}}'::jsonb,
    status text default 'new', -- new, contacted, responded, interested, not_interested, converted
    api_status text, -- API-detected: contacted, seen, responded
    api_seen_at timestamptz,
    api_responded_at timestamptz,
    responses jsonb default '[]'::jsonb,
    last_contact_date timestamptz,
    created_at timestamptz default now(),
    updated_at timestamptz default now(),
    unique(user_id, store_key)
);

-- DM Responses: detailed response log
create table if not exists public.dm_responses (
    id uuid default gen_random_uuid() primary key,
    user_id uuid references public.users(id) on delete cascade not null,
    dm_record_id uuid references public.dm_records(id) on delete cascade not null,
    response_type text not null, -- interested, question, not_interested, other
    notes text,
    created_at timestamptz default now()
);

-- DM Templates: user-customizable message templates
create table if not exists public.dm_templates (
    id uuid default gen_random_uuid() primary key,
    user_id uuid references public.users(id) on delete cascade not null,
    template_key text not null, -- introDm1, introDm2, introDm3, etc.
    name text,
    content text not null,
    created_at timestamptz default now(),
    updated_at timestamptz default now(),
    unique(user_id, template_key)
);

-- DM Settings: brand name, follow-up interval, etc.
create table if not exists public.dm_settings (
    id uuid default gen_random_uuid() primary key,
    user_id uuid references public.users(id) on delete cascade unique not null,
    brand_name text default 'My Brand',
    follow_up_interval_days integer default 3,
    created_at timestamptz default now(),
    updated_at timestamptz default now()
);

-- Indexes
create index if not exists idx_dm_records_user_id on public.dm_records(user_id);
create index if not exists idx_dm_records_store_key on public.dm_records(store_key);
create index if not exists idx_dm_records_status on public.dm_records(status);
create index if not exists idx_dm_responses_dm_record_id on public.dm_responses(dm_record_id);

-- Enable Row Level Security on all tables
alter table public.users enable row level security;
alter table public.dm_records enable row level security;
alter table public.dm_responses enable row level security;
alter table public.dm_templates enable row level security;
alter table public.dm_settings enable row level security;

-- RLS Policies: users can only access their own data

-- Users
create policy "Users can view own profile"
    on public.users for select
    using (auth.uid() = id);

create policy "Users can update own profile"
    on public.users for update
    using (auth.uid() = id);

-- DM Records
create policy "Users can view own dm_records"
    on public.dm_records for select
    using (auth.uid() = user_id);

create policy "Users can insert own dm_records"
    on public.dm_records for insert
    with check (auth.uid() = user_id);

create policy "Users can update own dm_records"
    on public.dm_records for update
    using (auth.uid() = user_id);

create policy "Users can delete own dm_records"
    on public.dm_records for delete
    using (auth.uid() = user_id);

-- DM Responses
create policy "Users can view own dm_responses"
    on public.dm_responses for select
    using (auth.uid() = user_id);

create policy "Users can insert own dm_responses"
    on public.dm_responses for insert
    with check (auth.uid() = user_id);

-- DM Templates
create policy "Users can view own dm_templates"
    on public.dm_templates for select
    using (auth.uid() = user_id);

create policy "Users can insert own dm_templates"
    on public.dm_templates for insert
    with check (auth.uid() = user_id);

create policy "Users can update own dm_templates"
    on public.dm_templates for update
    using (auth.uid() = user_id);

-- DM Settings
create policy "Users can view own dm_settings"
    on public.dm_settings for select
    using (auth.uid() = user_id);

create policy "Users can insert own dm_settings"
    on public.dm_settings for insert
    with check (auth.uid() = user_id);

create policy "Users can update own dm_settings"
    on public.dm_settings for update
    using (auth.uid() = user_id);

-- Service role policy for edge functions (webhook, token refresh)
create policy "Service role can manage dm_records"
    on public.dm_records for all
    using (auth.role() = 'service_role');

create policy "Service role can manage users"
    on public.users for all
    using (auth.role() = 'service_role');
