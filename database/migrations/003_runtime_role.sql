-- Run with psql as the schema administrator; PIX_API_PASSWORD comes from its environment.
-- Creates a separate runtime identity without changing existing decisions or admin access.
\set ON_ERROR_STOP on
\getenv pix_api_password PIX_API_PASSWORD
\if :{?pix_api_password}
\else
    \echo 'PIX_API_PASSWORD must be configured in the psql environment'
    \quit 1
\endif
SELECT length(:'pix_api_password') > 0 AS valid_runtime_password \gset
\if :valid_runtime_password
\else
    \echo 'PIX_API_PASSWORD must not be empty'
    \quit 1
\endif

BEGIN;
SELECT format(
    'CREATE ROLE pix_api LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS PASSWORD %L',
    :'pix_api_password'
) WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pix_api') \gexec

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_roles WHERE rolname = 'pix_api'
        AND (rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls)
    ) OR EXISTS (
        SELECT 1 FROM pg_auth_members m JOIN pg_roles r ON r.oid = m.member WHERE r.rolname = 'pix_api'
    ) OR EXISTS (
        SELECT 1 FROM pg_class c JOIN pg_roles r ON r.oid = c.relowner
        WHERE r.rolname = 'pix_api' AND c.oid = 'public.pix_analysis'::regclass
    ) THEN
        RAISE EXCEPTION 'Existing pix_api role has unexpected privileges; review it before migration';
    END IF;
END;
$$;

SELECT format('GRANT CONNECT ON DATABASE %I TO pix_api', current_database()) \gexec
GRANT USAGE ON SCHEMA public TO pix_api;
GRANT SELECT, INSERT ON TABLE public.pix_analysis TO pix_api;
GRANT USAGE ON SEQUENCE public.pix_analysis_id_seq TO pix_api;
REVOKE UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER ON TABLE public.pix_analysis FROM pix_api;
REVOKE CREATE ON SCHEMA public FROM pix_api;
COMMIT;
