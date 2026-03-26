-- Run this SQL in Supabase Dashboard > SQL Editor
-- Creates the companies and profiles tables, RLS policies, and auto-profile trigger.
-- Safe to run on a fresh Supabase project.

-- ===========================================================================
-- 1. companies table
-- ===========================================================================

CREATE TABLE public.companies (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    cod         TEXT NOT NULL UNIQUE,       -- XLSX COD column; upsert key
    razao       TEXT NOT NULL DEFAULT '',   -- Razao Social
    analista    TEXT NOT NULL DEFAULT '',   -- ANALISTA column (exact match to profiles.analyst_name)
    municipio   TEXT NOT NULL DEFAULT '',   -- MUNICIPIO column
    im          TEXT NOT NULL DEFAULT '',   -- Inscricao Municipal
    cnpj        TEXT NOT NULL DEFAULT '',   -- CNPJ
    nome_empresa TEXT NOT NULL DEFAULT '',  -- NOME EMPRESA column
    created_at  TIMESTAMPTZ DEFAULT now()
);

-- Index for common query patterns (filter by analyst, filter by municipio)
CREATE INDEX idx_companies_analista  ON public.companies (analista);
CREATE INDEX idx_companies_municipio ON public.companies (municipio);

-- Enable RLS (frontend will use anon/publishable key; backend uses service role)
ALTER TABLE public.companies ENABLE ROW LEVEL SECURITY;

-- All authenticated users can read all companies.
-- The "see all, process own" visibility rule is enforced in the API layer (not RLS).
CREATE POLICY "Authenticated users can read companies"
    ON public.companies FOR SELECT
    TO authenticated
    USING (true);

-- No INSERT/UPDATE/DELETE policies for authenticated users.
-- Only the service role (via SUPABASE_SECRET_KEY) can write company rows.


-- ===========================================================================
-- 2. profiles table — one row per auth.users entry
-- ===========================================================================

CREATE TABLE public.profiles (
    id            UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    analyst_name  TEXT,                      -- exact match to companies.analista
    created_at    TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;

-- Each authenticated user can read their own profile row.
-- (Needed if the frontend ever calls this table directly.)
CREATE POLICY "Users can read own profile"
    ON public.profiles FOR SELECT
    TO authenticated
    USING (auth.uid() = id);

-- Only the service role can insert or update profiles.
-- Analysts cannot set their own analyst_name (security requirement).


-- ===========================================================================
-- 3. Trigger: auto-create profile row when admin creates a user
-- ===========================================================================
-- When admin calls auth.admin.create_user({..., user_metadata: {analyst_name: "ANA"}}),
-- this trigger inserts a matching profiles row automatically.
-- analyst_name is NULL if not provided in user_metadata.

CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER LANGUAGE plpgsql SECURITY DEFINER AS $$
BEGIN
    INSERT INTO public.profiles (id, analyst_name)
    VALUES (NEW.id, NEW.raw_user_meta_data->>'analyst_name');
    RETURN NEW;
END;
$$;

CREATE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW EXECUTE PROCEDURE public.handle_new_user();
