-- Quita el prefijo ops_ de las tablas de ddv.
--
-- El prefijo venia de cuando todo vivia en el esquema public y hacia falta
-- separar el modulo operacional de las tablas antiguas. Ahora cada aplicacion
-- tiene su propio esquema, asi que el esquema ya cumple esa funcion y el
-- prefijo sobra: ddv.wells y fdp.wells no chocan. Las otras cuatro
-- aplicaciones nunca lo llevaron, de modo que esto las homologa.
--
-- Choca un nombre: ops_wells y wells son cosas distintas.
--   wells (antigua) = el pozo cuyos datos de sensores se importaron de un archivo
--   ops_wells       = el pozo maestro de la jerarquia compania -> proyecto -> sitio
-- Cada una pasa a llamarse por lo que es.
--
-- Las claves foraneas siguen a la tabla por su OID, no por su nombre, asi que
-- no hay que rehacer ninguna: annotations, well_data y processed_datasets
-- siguen apuntando a sensor_wells, y wellbores a wells.

set search_path = ddv, public;

-- Primero liberamos el nombre wells
alter table wells rename to sensor_wells;

-- Y despues quitamos el prefijo, ops_wells incluido
alter table ops_attachments          rename to attachments;
alter table ops_bha_components       rename to bha_components;
alter table ops_casing_components    rename to casing_components;
alter table ops_casing_running       rename to casing_running;
alter table ops_cement_jobs          rename to cement_jobs;
alter table ops_companies            rename to companies;
alter table ops_cost_items           rename to cost_items;
alter table ops_daily_reports        rename to daily_reports;
alter table ops_drill_params         rename to drill_params;
alter table ops_engineering_designs  rename to engineering_designs;
alter table ops_events               rename to events;
alter table ops_fluid_readings       rename to fluid_readings;
alter table ops_npt_events           rename to npt_events;
alter table ops_personnel_entries    rename to personnel_entries;
alter table ops_pipe_tally_joints    rename to pipe_tally_joints;
alter table ops_plan_casing          rename to plan_casing;
alter table ops_plan_cement          rename to plan_cement;
alter table ops_plan_costs           rename to plan_costs;
alter table ops_plan_directional     rename to plan_directional;
alter table ops_plan_formation_tops  rename to plan_formation_tops;
alter table ops_plan_geopressure     rename to plan_geopressure;
alter table ops_plan_hole            rename to plan_hole;
alter table ops_plan_mud             rename to plan_mud;
alter table ops_plan_risks           rename to plan_risks;
alter table ops_plan_time_depth      rename to plan_time_depth;
alter table ops_projects             rename to projects;
alter table ops_pump_operations      rename to pump_operations;
alter table ops_realtime_sources     rename to realtime_sources;
alter table ops_reg_bop_tests        rename to reg_bop_tests;
alter table ops_reg_certifications   rename to reg_certifications;
alter table ops_reg_hse_incidents    rename to reg_hse_incidents;
alter table ops_reg_lessons          rename to reg_lessons;
alter table ops_reg_materials        rename to reg_materials;
alter table ops_remarks              rename to remarks;
alter table ops_rigs                 rename to rigs;
alter table ops_safety_events        rename to safety_events;
alter table ops_sites                rename to sites;
alter table ops_step_catalog         rename to step_catalog;
alter table ops_survey_stations      rename to survey_stations;
alter table ops_time_summary_rows    rename to time_summary_rows;
alter table ops_user_roles           rename to user_roles;
alter table ops_validation_rules     rename to validation_rules;
alter table ops_well_plans           rename to well_plans;
alter table ops_wellbores            rename to wellbores;
alter table ops_wellhead_components  rename to wellhead_components;
alter table ops_wells                rename to wells;

comment on table sensor_wells is
  'Pozo cuyos datos de sensores se importaron de un archivo; wells es el pozo maestro';
