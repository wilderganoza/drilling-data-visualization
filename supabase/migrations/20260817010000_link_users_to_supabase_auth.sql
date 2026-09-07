-- Enlaza la tabla users de DDV con Supabase Auth.
--
-- No se migra users.id a uuid: unas 40 tablas lo referencian en created_by y
-- updated_by como entero. En su lugar se anade la referencia al usuario de
-- auth.users, de modo que Supabase pasa a ser el proveedor de identidad y la
-- fila local sigue siendo el perfil, con su id intacto.
--
-- Se aplica despues de 20260816000000_baseline_ddv.sql.

set search_path = ddv, public;

alter table users add column if not exists auth_user_id uuid;

-- Un usuario de Supabase no puede corresponder a dos filas locales
create unique index if not exists ix_users_auth_user_id
  on users (auth_user_id) where auth_user_id is not null;

-- El correo tambien identifica de forma unica, y es por donde se enlaza la
-- primera vez que alguien entra con una cuenta ya existente en Supabase
create unique index if not exists ix_users_email
  on users (lower(email)) where email is not null and email <> '';

comment on column users.auth_user_id is
  'Referencia al usuario de Supabase Auth; la contrasena ya no vive aqui';
