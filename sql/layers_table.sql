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
-- Name: layers; Type: TABLE; Schema: public; Owner: supabase_admin
--

CREATE TABLE public.layers (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    created_at timestamp with time zone DEFAULT (now() AT TIME ZONE 'utc'::text) NOT NULL,
    created_by uuid DEFAULT auth.uid(),
    name text NOT NULL,
    geometry_type public.geometry_type NOT NULL,
    attributes jsonb,
    srid integer NOT NULL,
    parent_id uuid,
    CONSTRAINT layers_name_check CHECK ((length(name) < 200))
);


ALTER TABLE public.layers OWNER TO supabase_admin;

--
-- Name: layers layers_pkey; Type: CONSTRAINT; Schema: public; Owner: supabase_admin
--

ALTER TABLE ONLY public.layers
    ADD CONSTRAINT layers_pkey PRIMARY KEY (id);


--
-- Name: layers layers_parent_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: supabase_admin
--

ALTER TABLE ONLY public.layers
    ADD CONSTRAINT layers_parent_id_fkey FOREIGN KEY (parent_id) REFERENCES public.layers(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: layers allow all to authenticated; Type: POLICY; Schema: public; Owner: supabase_admin
--

CREATE POLICY "allow all to authenticated" ON public.layers TO authenticated USING (true);


--
-- Name: layers; Type: ROW SECURITY; Schema: public; Owner: supabase_admin
--

ALTER TABLE public.layers ENABLE ROW LEVEL SECURITY;

--
-- Name: TABLE layers; Type: ACL; Schema: public; Owner: supabase_admin
--

GRANT SELECT,INSERT,REFERENCES,DELETE,TRIGGER,TRUNCATE,UPDATE ON TABLE public.layers TO postgres;
GRANT SELECT,INSERT,REFERENCES,DELETE,TRIGGER,TRUNCATE,UPDATE ON TABLE public.layers TO anon;
GRANT SELECT,INSERT,REFERENCES,DELETE,TRIGGER,TRUNCATE,UPDATE ON TABLE public.layers TO authenticated;
GRANT SELECT,INSERT,REFERENCES,DELETE,TRIGGER,TRUNCATE,UPDATE ON TABLE public.layers TO service_role;


--
-- PostgreSQL database dump complete
--
