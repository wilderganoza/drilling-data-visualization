-- Los indices y las restricciones tambien llevaban el prefijo en el nombre.
-- Dejarlos asi seria la misma incoherencia, solo que menos visible al mirar
-- el esquema por encima.
--
-- El orden importa: primero se liberan los nombres wells_* que arrastraba la
-- tabla antigua, porque si no ops_wells_pkey no puede pasar a wells_pkey.
--
-- Va en un bloque DO porque son 236 objetos y el nombre nuevo se deduce del
-- viejo quitando el prefijo; escribirlos uno a uno seria mas largo y mas facil
-- de equivocar.

do $$
declare
  r record;
  nuevo text;
begin
  -- 1. Los objetos de la tabla antigua pasan a llamarse sensor_wells_*
  for r in
    select c.conname
    from pg_constraint c
    join pg_class t on t.oid = c.conrelid
    join pg_namespace n on n.oid = t.relnamespace
    where n.nspname = 'ddv' and t.relname = 'sensor_wells'
      and c.conname like 'wells!_%' escape '!'
    order by c.conname
  loop
    execute format('alter table ddv.sensor_wells rename constraint %I to %I',
                   r.conname, 'sensor_' || r.conname);
  end loop;

  for r in
    select indexname from pg_indexes
    where schemaname = 'ddv' and tablename = 'sensor_wells'
      and (indexname like 'ix!_wells!_%' escape '!' or indexname like 'wells!_%' escape '!')
    order by indexname
  loop
    execute format('alter index ddv.%I rename to %I',
                   r.indexname,
                   case when r.indexname like 'ix!_wells!_%' escape '!'
                        then 'ix_sensor_wells_' || substring(r.indexname from 10)
                        else 'sensor_' || r.indexname end);
  end loop;

  -- 2. Ahora si, quitamos el prefijo ops_ de restricciones e indices
  for r in
    select c.conname, t.relname as tabla
    from pg_constraint c
    join pg_class t on t.oid = c.conrelid
    join pg_namespace n on n.oid = t.relnamespace
    where n.nspname = 'ddv' and c.conname like 'ops!_%' escape '!'
    order by c.conname
  loop
    nuevo := substring(r.conname from 5);
    execute format('alter table ddv.%I rename constraint %I to %I',
                   r.tabla, r.conname, nuevo);
  end loop;

  for r in
    select indexname from pg_indexes
    where schemaname = 'ddv' and indexname like 'ops!_%' escape '!'
    order by indexname
  loop
    nuevo := substring(r.indexname from 5);
    execute format('alter index ddv.%I rename to %I', r.indexname, nuevo);
  end loop;

  -- 3. Y los indices ix_ops_*, que llevan el prefijo en medio
  for r in
    select indexname from pg_indexes
    where schemaname = 'ddv' and indexname like 'ix!_ops!_%' escape '!'
    order by indexname
  loop
    nuevo := 'ix_' || substring(r.indexname from 8);
    execute format('alter index ddv.%I rename to %I', r.indexname, nuevo);
  end loop;
end $$;
