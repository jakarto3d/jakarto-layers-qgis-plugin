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
-- Name: sub_layer_deletes; Type: TABLE; Schema: public; Owner: supabase_admin
--

CREATE TABLE public.sub_layer_deletes (
    sub_layer_id uuid NOT NULL,
    uuid uuid DEFAULT gen_random_uuid() NOT NULL,
    parent_feature_id uuid NOT NULL
);


ALTER TABLE public.sub_layer_deletes OWNER TO supabase_admin;

--
-- Name: sub_layer_deletes sub_layer_deletes_pkey; Type: CONSTRAINT; Schema: public; Owner: supabase_admin
--

ALTER TABLE ONLY public.sub_layer_deletes
    ADD CONSTRAINT sub_layer_deletes_pkey PRIMARY KEY (uuid);


--
-- Name: sub_layer_deletes_parent_feature_id; Type: INDEX; Schema: public; Owner: supabase_admin
--

CREATE INDEX sub_layer_deletes_parent_feature_id ON public.sub_layer_deletes USING btree (parent_feature_id);


--
-- Name: sub_layer_deletes_sub_layer_id; Type: INDEX; Schema: public; Owner: supabase_admin
--

CREATE INDEX sub_layer_deletes_sub_layer_id ON public.sub_layer_deletes USING btree (uuid);


--
-- Name: sub_layer_deletes sub_layer_deletes_parent_feature_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: supabase_admin
--

ALTER TABLE ONLY public.sub_layer_deletes
    ADD CONSTRAINT sub_layer_deletes_parent_feature_id_fkey FOREIGN KEY (parent_feature_id) REFERENCES public.points(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: sub_layer_deletes sub_layer_deletes_sub_layer_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: supabase_admin
--

ALTER TABLE ONLY public.sub_layer_deletes
    ADD CONSTRAINT sub_layer_deletes_sub_layer_id_fkey FOREIGN KEY (sub_layer_id) REFERENCES public.layers(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: sub_layer_deletes allow all to authenticated; Type: POLICY; Schema: public; Owner: supabase_admin
--

CREATE POLICY "allow all to authenticated" ON public.sub_layer_deletes TO authenticated USING (true);


--
-- Name: sub_layer_deletes; Type: ROW SECURITY; Schema: public; Owner: supabase_admin
--

ALTER TABLE public.sub_layer_deletes ENABLE ROW LEVEL SECURITY;

--
-- Name: TABLE sub_layer_deletes; Type: ACL; Schema: public; Owner: supabase_admin
--

GRANT SELECT,INSERT,REFERENCES,DELETE,TRIGGER,TRUNCATE,UPDATE ON TABLE public.sub_layer_deletes TO postgres;
GRANT SELECT,INSERT,REFERENCES,DELETE,TRIGGER,TRUNCATE,UPDATE ON TABLE public.sub_layer_deletes TO anon;
GRANT SELECT,INSERT,REFERENCES,DELETE,TRIGGER,TRUNCATE,UPDATE ON TABLE public.sub_layer_deletes TO authenticated;
GRANT SELECT,INSERT,REFERENCES,DELETE,TRIGGER,TRUNCATE,UPDATE ON TABLE public.sub_layer_deletes TO service_role;


--
-- PostgreSQL database dump complete
--
