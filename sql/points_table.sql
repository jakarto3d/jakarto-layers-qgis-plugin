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
-- Name: points; Type: TABLE; Schema: public; Owner: supabase_admin
--

CREATE TABLE public.points (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    layer_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    geom extensions.geometry(PointZ) NOT NULL,
    attributes jsonb DEFAULT '{}'::jsonb NOT NULL,
    parent_id uuid
);


ALTER TABLE public.points OWNER TO supabase_admin;

--
-- Name: COLUMN points.parent_id; Type: COMMENT; Schema: public; Owner: supabase_admin
--

COMMENT ON COLUMN public.points.parent_id IS 'Features in a sub-layer use this field to know their original id';


--
-- Name: points points_pkey; Type: CONSTRAINT; Schema: public; Owner: supabase_admin
--

ALTER TABLE ONLY public.points
    ADD CONSTRAINT points_pkey PRIMARY KEY (id);


--
-- Name: points_geom_idx; Type: INDEX; Schema: public; Owner: supabase_admin
--

CREATE INDEX points_geom_idx ON public.points USING gist (geom);


--
-- Name: points_layer_id; Type: INDEX; Schema: public; Owner: supabase_admin
--

CREATE INDEX points_layer_id ON public.points USING btree (layer_id);


--
-- Name: points_parent_id; Type: INDEX; Schema: public; Owner: supabase_admin
--

CREATE INDEX points_parent_id ON public.points USING btree (parent_id);


--
-- Name: points points_audit_trigger; Type: TRIGGER; Schema: public; Owner: supabase_admin
--

CREATE TRIGGER points_audit_trigger AFTER INSERT OR DELETE OR UPDATE ON public.points FOR EACH ROW EXECUTE FUNCTION public.log_points_changes();


--
-- Name: points track_sub_layer_deletes_trigger; Type: TRIGGER; Schema: public; Owner: supabase_admin
--

CREATE TRIGGER track_sub_layer_deletes_trigger BEFORE DELETE ON public.points FOR EACH ROW EXECUTE FUNCTION public.track_sub_layer_deletes();


--
-- Name: points points_layer_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: supabase_admin
--

ALTER TABLE ONLY public.points
    ADD CONSTRAINT points_layer_id_fkey FOREIGN KEY (layer_id) REFERENCES public.layers(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: points points_parent_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: supabase_admin
--

ALTER TABLE ONLY public.points
    ADD CONSTRAINT points_parent_id_fkey FOREIGN KEY (parent_id) REFERENCES public.points(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: points allow all to authenticated; Type: POLICY; Schema: public; Owner: supabase_admin
--

CREATE POLICY "allow all to authenticated" ON public.points TO authenticated USING (true);


--
-- Name: points; Type: ROW SECURITY; Schema: public; Owner: supabase_admin
--

ALTER TABLE public.points ENABLE ROW LEVEL SECURITY;

--
-- Name: TABLE points; Type: ACL; Schema: public; Owner: supabase_admin
--

GRANT SELECT,INSERT,REFERENCES,DELETE,TRIGGER,TRUNCATE,UPDATE ON TABLE public.points TO postgres;
GRANT SELECT,INSERT,REFERENCES,DELETE,TRIGGER,TRUNCATE,UPDATE ON TABLE public.points TO anon;
GRANT SELECT,INSERT,REFERENCES,DELETE,TRIGGER,TRUNCATE,UPDATE ON TABLE public.points TO authenticated;
GRANT SELECT,INSERT,REFERENCES,DELETE,TRIGGER,TRUNCATE,UPDATE ON TABLE public.points TO service_role;


--
-- PostgreSQL database dump complete
--
