-- Enable required extensions on first database init.
-- Runs automatically via docker-entrypoint-initdb.d.
CREATE EXTENSION IF NOT EXISTS "pgcrypto";      -- gen_random_uuid(), pgp_sym_*
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- The application role owns schema objects created by Alembic.
GRANT ALL PRIVILEGES ON DATABASE hermes TO hermes;

-- Optional: helper view for auditing encryption coverage (no plaintext).
-- Example usage (operator only, key must be supplied at runtime):
--   SELECT id, pgp_sym_decrypt(content_encrypted, :key) FROM chat_logs;
COMMENT ON EXTENSION pgcrypto IS 'Used for UUID generation and optional SQL-side crypto parity.';
