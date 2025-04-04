--
-- PostgreSQL database dump
--

-- Dumped from database version 15.8
-- Dumped by pg_dump version 17.4 (Debian 17.4-1.pgdg120+2)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: points_log; Type: TABLE; Schema: public; Owner: supabase_admin
--

CREATE TABLE public.points_log (
    log_id uuid DEFAULT gen_random_uuid() NOT NULL,
    operation character varying(10) NOT NULL,
    logged_at timestamp with time zone DEFAULT now() NOT NULL,
    point_id uuid NOT NULL,
    geom extensions.geometry(PointZ),
    attributes jsonb
);


ALTER TABLE public.points_log OWNER TO supabase_admin;

--
-- Name: points_log points_log_pkey; Type: CONSTRAINT; Schema: public; Owner: supabase_admin
--

ALTER TABLE ONLY public.points_log
    ADD CONSTRAINT points_log_pkey PRIMARY KEY (log_id);


--
-- Name: points_log allow all to authenticated; Type: POLICY; Schema: public; Owner: supabase_admin
--

CREATE POLICY "allow all to authenticated" ON public.points_log TO authenticated USING (true);


--
-- Name: points_log; Type: ROW SECURITY; Schema: public; Owner: supabase_admin
--

ALTER TABLE public.points_log ENABLE ROW LEVEL SECURITY;

--
-- Name: TABLE points_log; Type: ACL; Schema: public; Owner: supabase_admin
--

GRANT SELECT,INSERT,REFERENCES,DELETE,TRIGGER,TRUNCATE,UPDATE ON TABLE public.points_log TO postgres;
GRANT SELECT,INSERT,REFERENCES,DELETE,TRIGGER,TRUNCATE,UPDATE ON TABLE public.points_log TO anon;
GRANT SELECT,INSERT,REFERENCES,DELETE,TRIGGER,TRUNCATE,UPDATE ON TABLE public.points_log TO authenticated;
GRANT SELECT,INSERT,REFERENCES,DELETE,TRIGGER,TRUNCATE,UPDATE ON TABLE public.points_log TO service_role;


--
-- PostgreSQL database dump complete
--
