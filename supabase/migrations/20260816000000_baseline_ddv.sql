-- Migracion base de Drilling Data Visualization.
-- Reemplaza las 20 revisiones de Alembic por un unico punto de partida.
-- 52 tablas provienen de los modelos SQLAlchemy; well_data, well_data_time y
-- annotations provienen del esquema real (la app las refleja en runtime).

set search_path = ddv, public;

CREATE TABLE users (
	id SERIAL NOT NULL, 
	username VARCHAR(100) NOT NULL, 
	full_name VARCHAR(200), 
	email VARCHAR(200), 
	hashed_password VARCHAR(255) NOT NULL, 
	is_active BOOLEAN, 
	is_admin BOOLEAN, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	updated_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id)
);

CREATE UNIQUE INDEX ix_users_username ON users (username);

CREATE INDEX ix_users_id ON users (id);

CREATE TABLE wells (
	id SERIAL NOT NULL, 
	well_name VARCHAR NOT NULL, 
	filename VARCHAR, 
	total_rows INTEGER, 
	total_columns INTEGER, 
	date_imported TIMESTAMP WITHOUT TIME ZONE, 
	field_name VARCHAR(100), 
	PRIMARY KEY (id)
);

CREATE INDEX ix_wells_field_name ON wells (field_name);

CREATE INDEX ix_wells_id ON wells (id);

CREATE INDEX ix_wells_well_name ON wells (well_name);

CREATE TABLE rop_wizard_jobs (
	job_id VARCHAR(64) NOT NULL, 
	kind VARCHAR(20) NOT NULL, 
	state JSONB NOT NULL, 
	result JSONB NOT NULL, 
	pipeline_path VARCHAR(300), 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (job_id)
);

CREATE TABLE processed_datasets (
	id SERIAL NOT NULL, 
	well_id INTEGER NOT NULL, 
	domain VARCHAR(20) DEFAULT 'depth' NOT NULL, 
	name VARCHAR(128) NOT NULL, 
	description VARCHAR(500), 
	pipeline_config JSONB NOT NULL, 
	metrics JSONB, 
	status VARCHAR(50), 
	record_count INTEGER, 
	created_by INTEGER, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	updated_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(well_id) REFERENCES wells (id), 
	FOREIGN KEY(created_by) REFERENCES users (id)
);

CREATE INDEX ix_processed_datasets_well_id ON processed_datasets (well_id);

CREATE INDEX ix_processed_datasets_id ON processed_datasets (id);

CREATE TABLE rop_experiments (
	id SERIAL NOT NULL, 
	name VARCHAR(160) NOT NULL, 
	description VARCHAR(500), 
	model_key VARCHAR(50) NOT NULL, 
	status VARCHAR(30), 
	config JSONB NOT NULL, 
	metrics JSONB, 
	training_detail JSONB, 
	artifact_path VARCHAR(300), 
	created_by INTEGER, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	updated_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(created_by) REFERENCES users (id)
);

CREATE INDEX ix_rop_experiments_id ON rop_experiments (id);

CREATE TABLE ops_attachments (
	owner_type VARCHAR(30) NOT NULL, 
	owner_id UUID NOT NULL, 
	filename VARCHAR(300) NOT NULL, 
	content_type VARCHAR(120), 
	size_bytes INTEGER, 
	caption VARCHAR(500), 
	data BYTEA NOT NULL, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	created_by INTEGER, 
	updated_by INTEGER, 
	PRIMARY KEY (id), 
	FOREIGN KEY(created_by) REFERENCES users (id), 
	FOREIGN KEY(updated_by) REFERENCES users (id)
);

CREATE INDEX ix_ops_attachments_owner_type ON ops_attachments (owner_type);

CREATE INDEX ix_ops_attachments_owner_id ON ops_attachments (owner_id);

CREATE TABLE ops_companies (
	name VARCHAR(200) NOT NULL, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	created_by INTEGER, 
	updated_by INTEGER, 
	PRIMARY KEY (id), 
	FOREIGN KEY(created_by) REFERENCES users (id), 
	FOREIGN KEY(updated_by) REFERENCES users (id)
);

CREATE TABLE ops_rigs (
	name VARCHAR(100) NOT NULL, 
	protocol VARCHAR(20) NOT NULL, 
	wits_mode VARCHAR(10) NOT NULL, 
	wits_host VARCHAR(100), 
	wits_port INTEGER, 
	is_active BOOLEAN NOT NULL, 
	notes VARCHAR(1000), 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	created_by INTEGER, 
	updated_by INTEGER, 
	PRIMARY KEY (id), 
	UNIQUE (name), 
	FOREIGN KEY(created_by) REFERENCES users (id), 
	FOREIGN KEY(updated_by) REFERENCES users (id)
);

CREATE TABLE ops_user_roles (
	user_id INTEGER NOT NULL, 
	role VARCHAR(50) NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (user_id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE TABLE ops_step_catalog (
	profile VARCHAR(50) NOT NULL, 
	version VARCHAR(20) NOT NULL, 
	step_no INTEGER NOT NULL, 
	phase VARCHAR(50) NOT NULL, 
	operation VARCHAR(300) NOT NULL, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	created_by INTEGER, 
	updated_by INTEGER, 
	PRIMARY KEY (id), 
	FOREIGN KEY(created_by) REFERENCES users (id), 
	FOREIGN KEY(updated_by) REFERENCES users (id)
);

CREATE INDEX ix_ops_step_catalog_profile ON ops_step_catalog (profile);

CREATE TABLE ops_validation_rules (
	report_type VARCHAR(50) NOT NULL, 
	field_name VARCHAR(80) NOT NULL, 
	level VARCHAR(20) NOT NULL, 
	"check" VARCHAR(40) NOT NULL, 
	param1 NUMERIC(16, 4), 
	param2 NUMERIC(16, 4), 
	field_name2 VARCHAR(80), 
	message VARCHAR(300) NOT NULL, 
	is_active BOOLEAN NOT NULL, 
	sort_order INTEGER NOT NULL, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	created_by INTEGER, 
	updated_by INTEGER, 
	PRIMARY KEY (id), 
	FOREIGN KEY(created_by) REFERENCES users (id), 
	FOREIGN KEY(updated_by) REFERENCES users (id)
);

CREATE INDEX ix_ops_validation_rules_report_type ON ops_validation_rules (report_type);

CREATE TABLE processed_records (
	id SERIAL NOT NULL, 
	dataset_id INTEGER NOT NULL, 
	source_record_id INTEGER, 
	data JSONB NOT NULL, 
	scaled_data JSONB, 
	component_scores JSONB, 
	is_outlier BOOLEAN, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(dataset_id) REFERENCES processed_datasets (id)
);

CREATE INDEX ix_processed_records_dataset_id ON processed_records (dataset_id);

CREATE INDEX ix_processed_records_id ON processed_records (id);

CREATE TABLE ops_projects (
	company_id UUID NOT NULL, 
	name VARCHAR(200) NOT NULL, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	created_by INTEGER, 
	updated_by INTEGER, 
	PRIMARY KEY (id), 
	FOREIGN KEY(company_id) REFERENCES ops_companies (id), 
	FOREIGN KEY(created_by) REFERENCES users (id), 
	FOREIGN KEY(updated_by) REFERENCES users (id)
);

CREATE INDEX ix_ops_projects_company_id ON ops_projects (company_id);

CREATE TABLE ops_sites (
	project_id UUID NOT NULL, 
	name VARCHAR(200) NOT NULL, 
	location VARCHAR(300), 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	created_by INTEGER, 
	updated_by INTEGER, 
	PRIMARY KEY (id), 
	FOREIGN KEY(project_id) REFERENCES ops_projects (id), 
	FOREIGN KEY(created_by) REFERENCES users (id), 
	FOREIGN KEY(updated_by) REFERENCES users (id)
);

CREATE INDEX ix_ops_sites_project_id ON ops_sites (project_id);

CREATE TABLE ops_wells (
	site_id UUID NOT NULL, 
	legacy_well_id INTEGER, 
	legal_well_name VARCHAR(200) NOT NULL, 
	common_well_name VARCHAR(200), 
	uwi VARCHAR(100), 
	operator VARCHAR(200), 
	api_no VARCHAR(100), 
	description VARCHAR(200), 
	target_formation VARCHAR(200), 
	purpose VARCHAR(200), 
	reason VARCHAR(200), 
	spud_date DATE, 
	country VARCHAR(100), 
	well_classification VARCHAR(100), 
	datum_name VARCHAR(50), 
	datum_elevation NUMERIC(10, 2), 
	ground_elevation NUMERIC(10, 2), 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	created_by INTEGER, 
	updated_by INTEGER, 
	PRIMARY KEY (id), 
	FOREIGN KEY(site_id) REFERENCES ops_sites (id), 
	FOREIGN KEY(legacy_well_id) REFERENCES wells (id), 
	FOREIGN KEY(created_by) REFERENCES users (id), 
	FOREIGN KEY(updated_by) REFERENCES users (id)
);

CREATE INDEX ix_ops_wells_uwi ON ops_wells (uwi);

CREATE INDEX ix_ops_wells_site_id ON ops_wells (site_id);

CREATE TABLE ops_wellbores (
	well_id UUID NOT NULL, 
	parent_wellbore_id UUID, 
	name VARCHAR(100) NOT NULL, 
	sidetrack_no VARCHAR(20), 
	trajectory_type VARCHAR(50), 
	api12 VARCHAR(20), 
	arch_no VARCHAR(50), 
	start_date DATE, 
	drilling_end_date DATE, 
	completion_end_date DATE, 
	vs_azimuth NUMERIC(6, 2), 
	max_angle_est NUMERIC(6, 2), 
	kick_off_top_md NUMERIC(10, 2), 
	kick_off_top_tvd NUMERIC(10, 2), 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	created_by INTEGER, 
	updated_by INTEGER, 
	PRIMARY KEY (id), 
	FOREIGN KEY(well_id) REFERENCES ops_wells (id), 
	FOREIGN KEY(parent_wellbore_id) REFERENCES ops_wellbores (id), 
	FOREIGN KEY(created_by) REFERENCES users (id), 
	FOREIGN KEY(updated_by) REFERENCES users (id)
);

CREATE INDEX ix_ops_wellbores_well_id ON ops_wellbores (well_id);

CREATE TABLE ops_events (
	wellbore_id UUID NOT NULL, 
	event_code VARCHAR(50), 
	event_type VARCHAR(50), 
	objective VARCHAR(200), 
	contractor VARCHAR(200), 
	rig_name VARCHAR(200), 
	start_date DATE, 
	end_date DATE, 
	authorized_cost INTEGER, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	created_by INTEGER, 
	updated_by INTEGER, 
	PRIMARY KEY (id), 
	FOREIGN KEY(wellbore_id) REFERENCES ops_wellbores (id), 
	FOREIGN KEY(created_by) REFERENCES users (id), 
	FOREIGN KEY(updated_by) REFERENCES users (id)
);

CREATE INDEX ix_ops_events_wellbore_id ON ops_events (wellbore_id);

CREATE TABLE ops_daily_reports (
	event_id UUID NOT NULL, 
	report_date DATE NOT NULL, 
	report_no INTEGER, 
	description VARCHAR(300), 
	supervisor VARCHAR(200), 
	engineer VARCHAR(200), 
	geologist VARCHAR(200), 
	dol NUMERIC(6, 2), 
	dfs NUMERIC(6, 2), 
	previous_md NUMERIC(10, 2), 
	md NUMERIC(10, 2), 
	tvd NUMERIC(10, 2), 
	progress NUMERIC(10, 2), 
	rotating_hrs NUMERIC(6, 2), 
	sliding_hrs NUMERIC(6, 2), 
	hole_size NUMERIC(6, 3), 
	formation VARCHAR(200), 
	lithology VARCHAR(200), 
	current_status TEXT, 
	summary_24hr TEXT, 
	forecast_24hr TEXT, 
	general_complete BOOLEAN NOT NULL, 
	workflow_status VARCHAR(20) NOT NULL, 
	is_locked BOOLEAN NOT NULL, 
	submitted_at TIMESTAMP WITHOUT TIME ZONE, 
	submitted_by INTEGER, 
	approved_at TIMESTAMP WITHOUT TIME ZONE, 
	approved_by INTEGER, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	created_by INTEGER, 
	updated_by INTEGER, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_daily_report_event_date UNIQUE (event_id, report_date), 
	FOREIGN KEY(event_id) REFERENCES ops_events (id), 
	FOREIGN KEY(submitted_by) REFERENCES users (id), 
	FOREIGN KEY(approved_by) REFERENCES users (id), 
	FOREIGN KEY(created_by) REFERENCES users (id), 
	FOREIGN KEY(updated_by) REFERENCES users (id)
);

CREATE INDEX ix_ops_daily_reports_event_id ON ops_daily_reports (event_id);

CREATE TABLE ops_engineering_designs (
	event_id UUID NOT NULL, 
	module VARCHAR(40) NOT NULL, 
	scenario VARCHAR(60) DEFAULT 'Base' NOT NULL, 
	params JSONB NOT NULL, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	created_by INTEGER, 
	updated_by INTEGER, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_eng_design_event_module_scenario UNIQUE (event_id, module, scenario), 
	FOREIGN KEY(event_id) REFERENCES ops_events (id), 
	FOREIGN KEY(created_by) REFERENCES users (id), 
	FOREIGN KEY(updated_by) REFERENCES users (id)
);

CREATE INDEX ix_ops_engineering_designs_event_id ON ops_engineering_designs (event_id);

CREATE INDEX ix_ops_engineering_designs_module ON ops_engineering_designs (module);

CREATE TABLE ops_well_plans (
	event_id UUID NOT NULL, 
	afe_number VARCHAR(100), 
	description VARCHAR(500), 
	approved_by VARCHAR(200), 
	engineer VARCHAR(200), 
	status VARCHAR(50), 
	authorized_date DATE, 
	is_locked BOOLEAN DEFAULT 'false' NOT NULL, 
	submitted_at TIMESTAMP WITHOUT TIME ZONE, 
	submitted_by INTEGER, 
	approved_at TIMESTAMP WITHOUT TIME ZONE, 
	approved_by_user INTEGER, 
	objective_primary TEXT, 
	objective_secondary TEXT, 
	target_formation VARCHAR(200), 
	geology_prognosis TEXT, 
	authorized_md NUMERIC(10, 2), 
	authorized_tvd NUMERIC(10, 2), 
	kop_md NUMERIC(10, 2), 
	max_inclination NUMERIC(6, 2), 
	target_azimuth NUMERIC(6, 2), 
	rig_name VARCHAR(200), 
	rig_type VARCHAR(100), 
	planned_spud_date DATE, 
	est_days NUMERIC(6, 2), 
	surface_location VARCHAR(300), 
	surface_northing NUMERIC(14, 2), 
	surface_easting NUMERIC(14, 2), 
	currency VARCHAR(10), 
	dry_hole_cost NUMERIC(16, 2), 
	completion_cost NUMERIC(16, 2), 
	contingency_pct NUMERIC(6, 2), 
	budget_total NUMERIC(16, 2), 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	created_by INTEGER, 
	updated_by INTEGER, 
	PRIMARY KEY (id), 
	FOREIGN KEY(event_id) REFERENCES ops_events (id), 
	FOREIGN KEY(submitted_by) REFERENCES users (id), 
	FOREIGN KEY(approved_by_user) REFERENCES users (id), 
	FOREIGN KEY(created_by) REFERENCES users (id), 
	FOREIGN KEY(updated_by) REFERENCES users (id)
);

CREATE UNIQUE INDEX ix_ops_well_plans_event_id ON ops_well_plans (event_id);

CREATE TABLE ops_plan_formation_tops (
	event_id UUID NOT NULL, 
	sort_order INTEGER NOT NULL, 
	formation VARCHAR(300), 
	md NUMERIC(16, 3), 
	tvd NUMERIC(16, 3), 
	lithology VARCHAR(300), 
	comments TEXT, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	created_by INTEGER, 
	updated_by INTEGER, 
	PRIMARY KEY (id), 
	FOREIGN KEY(event_id) REFERENCES ops_events (id), 
	FOREIGN KEY(created_by) REFERENCES users (id), 
	FOREIGN KEY(updated_by) REFERENCES users (id)
);

CREATE INDEX ix_ops_plan_formation_tops_event_id ON ops_plan_formation_tops (event_id);

CREATE TABLE ops_plan_geopressure (
	event_id UUID NOT NULL, 
	sort_order INTEGER NOT NULL, 
	md NUMERIC(16, 3), 
	tvd NUMERIC(16, 3), 
	pore_ppg NUMERIC(16, 3), 
	frac_ppg NUMERIC(16, 3), 
	temp_f NUMERIC(16, 3), 
	comments TEXT, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	created_by INTEGER, 
	updated_by INTEGER, 
	PRIMARY KEY (id), 
	FOREIGN KEY(event_id) REFERENCES ops_events (id), 
	FOREIGN KEY(created_by) REFERENCES users (id), 
	FOREIGN KEY(updated_by) REFERENCES users (id)
);

CREATE INDEX ix_ops_plan_geopressure_event_id ON ops_plan_geopressure (event_id);

CREATE TABLE ops_plan_casing (
	event_id UUID NOT NULL, 
	sort_order INTEGER NOT NULL, 
	string VARCHAR(60), 
	od_in NUMERIC(16, 3), 
	weight_ppf NUMERIC(16, 3), 
	grade VARCHAR(300), 
	connection VARCHAR(300), 
	setting_md NUMERIC(16, 3), 
	setting_tvd NUMERIC(16, 3), 
	comments TEXT, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	created_by INTEGER, 
	updated_by INTEGER, 
	PRIMARY KEY (id), 
	FOREIGN KEY(event_id) REFERENCES ops_events (id), 
	FOREIGN KEY(created_by) REFERENCES users (id), 
	FOREIGN KEY(updated_by) REFERENCES users (id)
);

CREATE INDEX ix_ops_plan_casing_event_id ON ops_plan_casing (event_id);

CREATE TABLE ops_plan_hole (
	event_id UUID NOT NULL, 
	sort_order INTEGER NOT NULL, 
	section VARCHAR(60), 
	hole_size_in NUMERIC(16, 3), 
	bit_type VARCHAR(300), 
	top_md NUMERIC(16, 3), 
	bottom_md NUMERIC(16, 3), 
	length_ft NUMERIC(16, 3), 
	comments TEXT, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	created_by INTEGER, 
	updated_by INTEGER, 
	PRIMARY KEY (id), 
	FOREIGN KEY(event_id) REFERENCES ops_events (id), 
	FOREIGN KEY(created_by) REFERENCES users (id), 
	FOREIGN KEY(updated_by) REFERENCES users (id)
);

CREATE INDEX ix_ops_plan_hole_event_id ON ops_plan_hole (event_id);

CREATE TABLE ops_plan_mud (
	event_id UUID NOT NULL, 
	sort_order INTEGER NOT NULL, 
	section VARCHAR(60), 
	mud_type VARCHAR(300), 
	top_md NUMERIC(16, 3), 
	bottom_md NUMERIC(16, 3), 
	weight_min NUMERIC(16, 3), 
	weight_max NUMERIC(16, 3), 
	comments TEXT, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	created_by INTEGER, 
	updated_by INTEGER, 
	PRIMARY KEY (id), 
	FOREIGN KEY(event_id) REFERENCES ops_events (id), 
	FOREIGN KEY(created_by) REFERENCES users (id), 
	FOREIGN KEY(updated_by) REFERENCES users (id)
);

CREATE INDEX ix_ops_plan_mud_event_id ON ops_plan_mud (event_id);

CREATE TABLE ops_plan_cement (
	event_id UUID NOT NULL, 
	sort_order INTEGER NOT NULL, 
	string VARCHAR(60), 
	slurry_type VARCHAR(300), 
	density_ppg NUMERIC(16, 3), 
	volume_bbl NUMERIC(16, 3), 
	top_md NUMERIC(16, 3), 
	bottom_md NUMERIC(16, 3), 
	comments TEXT, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	created_by INTEGER, 
	updated_by INTEGER, 
	PRIMARY KEY (id), 
	FOREIGN KEY(event_id) REFERENCES ops_events (id), 
	FOREIGN KEY(created_by) REFERENCES users (id), 
	FOREIGN KEY(updated_by) REFERENCES users (id)
);

CREATE INDEX ix_ops_plan_cement_event_id ON ops_plan_cement (event_id);

CREATE TABLE ops_plan_directional (
	event_id UUID NOT NULL, 
	sort_order INTEGER NOT NULL, 
	md NUMERIC(16, 3), 
	inclination NUMERIC(16, 3), 
	azimuth NUMERIC(16, 3), 
	tvd NUMERIC(16, 3), 
	ns NUMERIC(16, 3), 
	ew NUMERIC(16, 3), 
	dls NUMERIC(16, 3), 
	comments TEXT, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	created_by INTEGER, 
	updated_by INTEGER, 
	PRIMARY KEY (id), 
	FOREIGN KEY(event_id) REFERENCES ops_events (id), 
	FOREIGN KEY(created_by) REFERENCES users (id), 
	FOREIGN KEY(updated_by) REFERENCES users (id)
);

CREATE INDEX ix_ops_plan_directional_event_id ON ops_plan_directional (event_id);

CREATE TABLE ops_plan_time_depth (
	event_id UUID NOT NULL, 
	sort_order INTEGER NOT NULL, 
	day INTEGER, 
	planned_md NUMERIC(16, 3), 
	phase VARCHAR(300), 
	comments TEXT, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	created_by INTEGER, 
	updated_by INTEGER, 
	PRIMARY KEY (id), 
	FOREIGN KEY(event_id) REFERENCES ops_events (id), 
	FOREIGN KEY(created_by) REFERENCES users (id), 
	FOREIGN KEY(updated_by) REFERENCES users (id)
);

CREATE INDEX ix_ops_plan_time_depth_event_id ON ops_plan_time_depth (event_id);

CREATE TABLE ops_plan_costs (
	event_id UUID NOT NULL, 
	sort_order INTEGER NOT NULL, 
	category VARCHAR(60), 
	description VARCHAR(300), 
	qty NUMERIC(16, 3), 
	unit_cost NUMERIC(16, 3), 
	amount NUMERIC(16, 3), 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	created_by INTEGER, 
	updated_by INTEGER, 
	PRIMARY KEY (id), 
	FOREIGN KEY(event_id) REFERENCES ops_events (id), 
	FOREIGN KEY(created_by) REFERENCES users (id), 
	FOREIGN KEY(updated_by) REFERENCES users (id)
);

CREATE INDEX ix_ops_plan_costs_event_id ON ops_plan_costs (event_id);

CREATE TABLE ops_plan_risks (
	event_id UUID NOT NULL, 
	sort_order INTEGER NOT NULL, 
	category VARCHAR(60), 
	description TEXT, 
	severity VARCHAR(60), 
	likelihood VARCHAR(60), 
	mitigation TEXT, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	created_by INTEGER, 
	updated_by INTEGER, 
	PRIMARY KEY (id), 
	FOREIGN KEY(event_id) REFERENCES ops_events (id), 
	FOREIGN KEY(created_by) REFERENCES users (id), 
	FOREIGN KEY(updated_by) REFERENCES users (id)
);

CREATE INDEX ix_ops_plan_risks_event_id ON ops_plan_risks (event_id);

CREATE TABLE ops_realtime_sources (
	event_id UUID NOT NULL, 
	rig_id UUID NOT NULL, 
	enabled BOOLEAN NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	last_error VARCHAR(500), 
	last_data_at TIMESTAMP WITHOUT TIME ZONE, 
	rows_ingested INTEGER NOT NULL, 
	started_at TIMESTAMP WITHOUT TIME ZONE, 
	stopped_at TIMESTAMP WITHOUT TIME ZONE, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	created_by INTEGER, 
	updated_by INTEGER, 
	PRIMARY KEY (id), 
	FOREIGN KEY(event_id) REFERENCES ops_events (id), 
	FOREIGN KEY(rig_id) REFERENCES ops_rigs (id), 
	FOREIGN KEY(created_by) REFERENCES users (id), 
	FOREIGN KEY(updated_by) REFERENCES users (id)
);

CREATE INDEX ix_ops_realtime_sources_rig_id ON ops_realtime_sources (rig_id);

CREATE INDEX ix_ops_realtime_sources_event_id ON ops_realtime_sources (event_id);

CREATE TABLE ops_reg_hse_incidents (
	event_id UUID NOT NULL, 
	sort_order INTEGER NOT NULL, 
	date VARCHAR(300), 
	category VARCHAR(60), 
	severity VARCHAR(60), 
	title VARCHAR(300), 
	description TEXT, 
	immediate_action TEXT, 
	root_cause TEXT, 
	status VARCHAR(60), 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	created_by INTEGER, 
	updated_by INTEGER, 
	PRIMARY KEY (id), 
	FOREIGN KEY(event_id) REFERENCES ops_events (id), 
	FOREIGN KEY(created_by) REFERENCES users (id), 
	FOREIGN KEY(updated_by) REFERENCES users (id)
);

CREATE INDEX ix_ops_reg_hse_incidents_event_id ON ops_reg_hse_incidents (event_id);

CREATE TABLE ops_reg_bop_tests (
	event_id UUID NOT NULL, 
	sort_order INTEGER NOT NULL, 
	date VARCHAR(300), 
	test_type VARCHAR(60), 
	component VARCHAR(60), 
	low_psi NUMERIC(16, 3), 
	high_psi NUMERIC(16, 3), 
	hold_min NUMERIC(16, 3), 
	result VARCHAR(60), 
	next_due VARCHAR(300), 
	comments TEXT, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	created_by INTEGER, 
	updated_by INTEGER, 
	PRIMARY KEY (id), 
	FOREIGN KEY(event_id) REFERENCES ops_events (id), 
	FOREIGN KEY(created_by) REFERENCES users (id), 
	FOREIGN KEY(updated_by) REFERENCES users (id)
);

CREATE INDEX ix_ops_reg_bop_tests_event_id ON ops_reg_bop_tests (event_id);

CREATE TABLE ops_reg_certifications (
	event_id UUID NOT NULL, 
	sort_order INTEGER NOT NULL, 
	item VARCHAR(300), 
	cert_type VARCHAR(60), 
	holder VARCHAR(300), 
	authority VARCHAR(300), 
	issued VARCHAR(300), 
	expires VARCHAR(300), 
	status VARCHAR(60), 
	comments TEXT, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	created_by INTEGER, 
	updated_by INTEGER, 
	PRIMARY KEY (id), 
	FOREIGN KEY(event_id) REFERENCES ops_events (id), 
	FOREIGN KEY(created_by) REFERENCES users (id), 
	FOREIGN KEY(updated_by) REFERENCES users (id)
);

CREATE INDEX ix_ops_reg_certifications_event_id ON ops_reg_certifications (event_id);

CREATE TABLE ops_reg_lessons (
	event_id UUID NOT NULL, 
	sort_order INTEGER NOT NULL, 
	date VARCHAR(300), 
	category VARCHAR(60), 
	phase VARCHAR(300), 
	event_description TEXT, 
	lesson TEXT, 
	recommendation TEXT, 
	npt_hours NUMERIC(16, 3), 
	impact VARCHAR(60), 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	created_by INTEGER, 
	updated_by INTEGER, 
	PRIMARY KEY (id), 
	FOREIGN KEY(event_id) REFERENCES ops_events (id), 
	FOREIGN KEY(created_by) REFERENCES users (id), 
	FOREIGN KEY(updated_by) REFERENCES users (id)
);

CREATE INDEX ix_ops_reg_lessons_event_id ON ops_reg_lessons (event_id);

CREATE TABLE ops_reg_materials (
	event_id UUID NOT NULL, 
	sort_order INTEGER NOT NULL, 
	category VARCHAR(60), 
	item VARCHAR(300), 
	unit VARCHAR(60), 
	planned_qty NUMERIC(16, 3), 
	received_qty NUMERIC(16, 3), 
	consumed_qty NUMERIC(16, 3), 
	on_hand NUMERIC(16, 3), 
	unit_cost NUMERIC(16, 3), 
	comments TEXT, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	created_by INTEGER, 
	updated_by INTEGER, 
	PRIMARY KEY (id), 
	FOREIGN KEY(event_id) REFERENCES ops_events (id), 
	FOREIGN KEY(created_by) REFERENCES users (id), 
	FOREIGN KEY(updated_by) REFERENCES users (id)
);

CREATE INDEX ix_ops_reg_materials_event_id ON ops_reg_materials (event_id);

CREATE TABLE ops_casing_components (
	daily_report_id UUID NOT NULL, 
	sort_order INTEGER NOT NULL, 
	section_type VARCHAR(60), 
	od_in NUMERIC(16, 3), 
	id_in NUMERIC(16, 3), 
	weight_ppf NUMERIC(16, 3), 
	grade VARCHAR(300), 
	connection VARCHAR(300), 
	top_md NUMERIC(16, 3), 
	bottom_md NUMERIC(16, 3), 
	length_ft NUMERIC(16, 3), 
	comments TEXT, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	created_by INTEGER, 
	updated_by INTEGER, 
	PRIMARY KEY (id), 
	FOREIGN KEY(daily_report_id) REFERENCES ops_daily_reports (id), 
	FOREIGN KEY(created_by) REFERENCES users (id), 
	FOREIGN KEY(updated_by) REFERENCES users (id)
);

CREATE INDEX ix_ops_casing_components_daily_report_id ON ops_casing_components (daily_report_id);

CREATE TABLE ops_casing_running (
	daily_report_id UUID NOT NULL, 
	sort_order INTEGER NOT NULL, 
	string VARCHAR(60), 
	od_in NUMERIC(16, 3), 
	planned_shoe_md NUMERIC(16, 3), 
	actual_shoe_md NUMERIC(16, 3), 
	joints_run INTEGER, 
	running_hours NUMERIC(16, 3), 
	mud_displaced_bbl NUMERIC(16, 3), 
	returns_pct NUMERIC(16, 3), 
	landed VARCHAR(60), 
	comments TEXT, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	created_by INTEGER, 
	updated_by INTEGER, 
	PRIMARY KEY (id), 
	FOREIGN KEY(daily_report_id) REFERENCES ops_daily_reports (id), 
	FOREIGN KEY(created_by) REFERENCES users (id), 
	FOREIGN KEY(updated_by) REFERENCES users (id)
);

CREATE INDEX ix_ops_casing_running_daily_report_id ON ops_casing_running (daily_report_id);

CREATE TABLE ops_cement_jobs (
	daily_report_id UUID NOT NULL, 
	sort_order INTEGER NOT NULL, 
	stage VARCHAR(60), 
	casing_size VARCHAR(300), 
	slurry_type VARCHAR(300), 
	cement_class VARCHAR(60), 
	density_ppg NUMERIC(16, 3), 
	volume_bbl NUMERIC(16, 3), 
	top_md NUMERIC(16, 3), 
	bottom_md NUMERIC(16, 3), 
	returns_pct NUMERIC(16, 3), 
	comments TEXT, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	created_by INTEGER, 
	updated_by INTEGER, 
	PRIMARY KEY (id), 
	FOREIGN KEY(daily_report_id) REFERENCES ops_daily_reports (id), 
	FOREIGN KEY(created_by) REFERENCES users (id), 
	FOREIGN KEY(updated_by) REFERENCES users (id)
);

CREATE INDEX ix_ops_cement_jobs_daily_report_id ON ops_cement_jobs (daily_report_id);

CREATE TABLE ops_wellhead_components (
	daily_report_id UUID NOT NULL, 
	sort_order INTEGER NOT NULL, 
	component VARCHAR(60), 
	size VARCHAR(300), 
	pressure_rating VARCHAR(300), 
	manufacturer VARCHAR(300), 
	serial_no VARCHAR(300), 
	associated_string VARCHAR(60), 
	test_pressure_psi NUMERIC(16, 3), 
	comments TEXT, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	created_by INTEGER, 
	updated_by INTEGER, 
	PRIMARY KEY (id), 
	FOREIGN KEY(daily_report_id) REFERENCES ops_daily_reports (id), 
	FOREIGN KEY(created_by) REFERENCES users (id), 
	FOREIGN KEY(updated_by) REFERENCES users (id)
);

CREATE INDEX ix_ops_wellhead_components_daily_report_id ON ops_wellhead_components (daily_report_id);

CREATE TABLE ops_survey_stations (
	daily_report_id UUID NOT NULL, 
	sort_order INTEGER NOT NULL, 
	md NUMERIC(16, 3), 
	inclination NUMERIC(16, 3), 
	azimuth NUMERIC(16, 3), 
	tvd NUMERIC(16, 3), 
	ns NUMERIC(16, 3), 
	ew NUMERIC(16, 3), 
	dls NUMERIC(16, 3), 
	comments TEXT, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	created_by INTEGER, 
	updated_by INTEGER, 
	PRIMARY KEY (id), 
	FOREIGN KEY(daily_report_id) REFERENCES ops_daily_reports (id), 
	FOREIGN KEY(created_by) REFERENCES users (id), 
	FOREIGN KEY(updated_by) REFERENCES users (id)
);

CREATE INDEX ix_ops_survey_stations_daily_report_id ON ops_survey_stations (daily_report_id);

CREATE TABLE ops_bha_components (
	daily_report_id UUID NOT NULL, 
	sort_order INTEGER NOT NULL, 
	component VARCHAR(60), 
	od_in NUMERIC(16, 3), 
	id_in NUMERIC(16, 3), 
	length_ft NUMERIC(16, 3), 
	serial_no VARCHAR(300), 
	description TEXT, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	created_by INTEGER, 
	updated_by INTEGER, 
	PRIMARY KEY (id), 
	FOREIGN KEY(daily_report_id) REFERENCES ops_daily_reports (id), 
	FOREIGN KEY(created_by) REFERENCES users (id), 
	FOREIGN KEY(updated_by) REFERENCES users (id)
);

CREATE INDEX ix_ops_bha_components_daily_report_id ON ops_bha_components (daily_report_id);

CREATE TABLE ops_cost_items (
	daily_report_id UUID NOT NULL, 
	sort_order INTEGER NOT NULL, 
	category VARCHAR(60), 
	description VARCHAR(300), 
	vendor VARCHAR(300), 
	afe_code VARCHAR(300), 
	qty NUMERIC(16, 3), 
	unit_cost NUMERIC(16, 3), 
	amount NUMERIC(16, 3), 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	created_by INTEGER, 
	updated_by INTEGER, 
	PRIMARY KEY (id), 
	FOREIGN KEY(daily_report_id) REFERENCES ops_daily_reports (id), 
	FOREIGN KEY(created_by) REFERENCES users (id), 
	FOREIGN KEY(updated_by) REFERENCES users (id)
);

CREATE INDEX ix_ops_cost_items_daily_report_id ON ops_cost_items (daily_report_id);

CREATE TABLE ops_pipe_tally_joints (
	daily_report_id UUID NOT NULL, 
	sort_order INTEGER NOT NULL, 
	joint_no INTEGER, 
	length_ft NUMERIC(16, 3), 
	cumulative_ft NUMERIC(16, 3), 
	od_in NUMERIC(16, 3), 
	serial_no VARCHAR(300), 
	comments TEXT, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	created_by INTEGER, 
	updated_by INTEGER, 
	PRIMARY KEY (id), 
	FOREIGN KEY(daily_report_id) REFERENCES ops_daily_reports (id), 
	FOREIGN KEY(created_by) REFERENCES users (id), 
	FOREIGN KEY(updated_by) REFERENCES users (id)
);

CREATE INDEX ix_ops_pipe_tally_joints_daily_report_id ON ops_pipe_tally_joints (daily_report_id);

CREATE TABLE ops_drill_params (
	daily_report_id UUID NOT NULL, 
	sort_order INTEGER NOT NULL, 
	depth_md NUMERIC(16, 3), 
	formation VARCHAR(300), 
	bit_size NUMERIC(16, 3), 
	wob NUMERIC(16, 3), 
	rpm NUMERIC(16, 3), 
	flow_gpm NUMERIC(16, 3), 
	torque_ftlb NUMERIC(16, 3), 
	spp_psi NUMERIC(16, 3), 
	rop NUMERIC(16, 3), 
	mse_ksi NUMERIC(16, 3), 
	comments TEXT, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	created_by INTEGER, 
	updated_by INTEGER, 
	PRIMARY KEY (id), 
	FOREIGN KEY(daily_report_id) REFERENCES ops_daily_reports (id), 
	FOREIGN KEY(created_by) REFERENCES users (id), 
	FOREIGN KEY(updated_by) REFERENCES users (id)
);

CREATE INDEX ix_ops_drill_params_daily_report_id ON ops_drill_params (daily_report_id);

CREATE TABLE ops_fluid_readings (
	daily_report_id UUID NOT NULL, 
	sort_order INTEGER NOT NULL, 
	time VARCHAR(5), 
	mud_type VARCHAR(300), 
	weight_ppg NUMERIC(16, 3), 
	funnel_vis NUMERIC(16, 3), 
	pv NUMERIC(16, 3), 
	yp NUMERIC(16, 3), 
	ph NUMERIC(16, 3), 
	chlorides NUMERIC(16, 3), 
	comments TEXT, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	created_by INTEGER, 
	updated_by INTEGER, 
	PRIMARY KEY (id), 
	FOREIGN KEY(daily_report_id) REFERENCES ops_daily_reports (id), 
	FOREIGN KEY(created_by) REFERENCES users (id), 
	FOREIGN KEY(updated_by) REFERENCES users (id)
);

CREATE INDEX ix_ops_fluid_readings_daily_report_id ON ops_fluid_readings (daily_report_id);

CREATE TABLE ops_pump_operations (
	daily_report_id UUID NOT NULL, 
	sort_order INTEGER NOT NULL, 
	equipment VARCHAR(60), 
	model VARCHAR(300), 
	liner_size_in NUMERIC(16, 3), 
	spm NUMERIC(16, 3), 
	pressure_psi NUMERIC(16, 3), 
	flow_rate_gpm NUMERIC(16, 3), 
	hours_run NUMERIC(16, 3), 
	comments TEXT, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	created_by INTEGER, 
	updated_by INTEGER, 
	PRIMARY KEY (id), 
	FOREIGN KEY(daily_report_id) REFERENCES ops_daily_reports (id), 
	FOREIGN KEY(created_by) REFERENCES users (id), 
	FOREIGN KEY(updated_by) REFERENCES users (id)
);

CREATE INDEX ix_ops_pump_operations_daily_report_id ON ops_pump_operations (daily_report_id);

CREATE TABLE ops_personnel_entries (
	daily_report_id UUID NOT NULL, 
	sort_order INTEGER NOT NULL, 
	company VARCHAR(300), 
	name VARCHAR(300), 
	position VARCHAR(300), 
	persons INTEGER, 
	hours NUMERIC(16, 3), 
	comments TEXT, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	created_by INTEGER, 
	updated_by INTEGER, 
	PRIMARY KEY (id), 
	FOREIGN KEY(daily_report_id) REFERENCES ops_daily_reports (id), 
	FOREIGN KEY(created_by) REFERENCES users (id), 
	FOREIGN KEY(updated_by) REFERENCES users (id)
);

CREATE INDEX ix_ops_personnel_entries_daily_report_id ON ops_personnel_entries (daily_report_id);

CREATE TABLE ops_safety_events (
	daily_report_id UUID NOT NULL, 
	sort_order INTEGER NOT NULL, 
	time VARCHAR(5), 
	event_type VARCHAR(60), 
	severity VARCHAR(60), 
	description TEXT, 
	action TEXT, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	created_by INTEGER, 
	updated_by INTEGER, 
	PRIMARY KEY (id), 
	FOREIGN KEY(daily_report_id) REFERENCES ops_daily_reports (id), 
	FOREIGN KEY(created_by) REFERENCES users (id), 
	FOREIGN KEY(updated_by) REFERENCES users (id)
);

CREATE INDEX ix_ops_safety_events_daily_report_id ON ops_safety_events (daily_report_id);

CREATE TABLE ops_remarks (
	daily_report_id UUID NOT NULL, 
	sort_order INTEGER NOT NULL, 
	time VARCHAR(5), 
	category VARCHAR(60), 
	remark TEXT, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	created_by INTEGER, 
	updated_by INTEGER, 
	PRIMARY KEY (id), 
	FOREIGN KEY(daily_report_id) REFERENCES ops_daily_reports (id), 
	FOREIGN KEY(created_by) REFERENCES users (id), 
	FOREIGN KEY(updated_by) REFERENCES users (id)
);

CREATE INDEX ix_ops_remarks_daily_report_id ON ops_remarks (daily_report_id);

CREATE TABLE ops_time_summary_rows (
	daily_report_id UUID NOT NULL, 
	sort_order INTEGER NOT NULL, 
	time_from VARCHAR(5), 
	time_to VARCHAR(5), 
	step_no INTEGER, 
	phase VARCHAR(50), 
	op_class VARCHAR(10), 
	op_code VARCHAR(50), 
	operation_detail TEXT, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	created_by INTEGER, 
	updated_by INTEGER, 
	PRIMARY KEY (id), 
	FOREIGN KEY(daily_report_id) REFERENCES ops_daily_reports (id), 
	FOREIGN KEY(created_by) REFERENCES users (id), 
	FOREIGN KEY(updated_by) REFERENCES users (id)
);

CREATE INDEX ix_ops_time_summary_rows_daily_report_id ON ops_time_summary_rows (daily_report_id);

CREATE TABLE ops_npt_events (
	daily_report_id UUID NOT NULL, 
	time_summary_row_id UUID, 
	parent_id UUID, 
	npt_type VARCHAR(100), 
	title VARCHAR(300), 
	description TEXT, 
	cause VARCHAR(300), 
	start_time TIMESTAMP WITHOUT TIME ZONE, 
	end_time TIMESTAMP WITHOUT TIME ZONE, 
	gross_hours NUMERIC(6, 2), 
	net_hours NUMERIC(6, 2), 
	failure_md NUMERIC(10, 2), 
	contractor_name VARCHAR(200), 
	contractual_link VARCHAR(50), 
	contractual_no VARCHAR(50), 
	type_cost NUMERIC(12, 2), 
	equip_cost NUMERIC(12, 2), 
	other_cost NUMERIC(12, 2), 
	reviewer_name VARCHAR(200), 
	preventive_actions TEXT, 
	lessons_learned TEXT, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	created_by INTEGER, 
	updated_by INTEGER, 
	is_closed BOOLEAN NOT NULL, 
	closed_at TIMESTAMP WITHOUT TIME ZONE, 
	closed_by INTEGER, 
	superseded_by_id UUID, 
	PRIMARY KEY (id), 
	FOREIGN KEY(daily_report_id) REFERENCES ops_daily_reports (id), 
	FOREIGN KEY(time_summary_row_id) REFERENCES ops_time_summary_rows (id), 
	FOREIGN KEY(parent_id) REFERENCES ops_npt_events (id), 
	FOREIGN KEY(created_by) REFERENCES users (id), 
	FOREIGN KEY(updated_by) REFERENCES users (id), 
	FOREIGN KEY(closed_by) REFERENCES users (id), 
	FOREIGN KEY(superseded_by_id) REFERENCES ops_npt_events (id)
);

CREATE INDEX ix_ops_npt_events_daily_report_id ON ops_npt_events (daily_report_id);

-- === Tablas reflejadas en runtime (fuera del alcance de Alembic) ===========

CREATE TABLE ddv.annotations (
    id integer NOT NULL,
    well_id integer NOT NULL,
    depth double precision,
    "timestamp" character varying,
    event_type character varying NOT NULL,
    description text,
    "user" character varying,
    created_at timestamp without time zone
);

CREATE SEQUENCE ddv.annotations_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE ddv.annotations_id_seq OWNED BY ddv.annotations.id;

CREATE TABLE ddv.well_data (
    id integer NOT NULL,
    well_id integer NOT NULL,
    hole_depth_feet double precision,
    rate_of_penetration_ft_per_hr double precision,
    time_of_penetration_min_per_ft double precision,
    bit_depth_feet double precision,
    hook_load_klbs double precision,
    standpipe_pressure_psi double precision,
    pump_1_strokes_min_spm double precision,
    pump_2_strokes_min_spm double precision,
    rotary_rpm_rpm double precision,
    weight_on_bit_klbs double precision,
    on_bottom_rop_ft_per_hr double precision,
    line_wear_ton_miles double precision,
    pump_1_total_strokes_strokes double precision,
    pump_2_total_strokes_strokes double precision,
    total_pump_output_gal_per_min double precision,
    totalpumpdisplacement_barrels double precision,
    block_height_feet double precision,
    pump_3_total_strokes_strokes double precision,
    on_bottom_hours_hrs double precision,
    circulating_hours_hrs double precision,
    over_pull_klbs double precision,
    fill_strokes_strokes double precision,
    total_fill_strokes_strokes double precision,
    differential_pressure_psi double precision,
    trip_speed_ft_per_min double precision,
    pump_4_total_strokes_strokes double precision,
    total_strokes_p1plusp2plusp3plusp4_strokes double precision,
    motor_rpm_rpm double precision,
    yyyy_mm_dd text,
    hh_mm_ss text,
    bit_size double precision
);

CREATE SEQUENCE ddv.well_data_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE ddv.well_data_id_seq OWNED BY ddv.well_data.id;

CREATE TABLE ddv.well_data_time (
    id integer DEFAULT nextval('ddv.well_data_id_seq'::regclass) NOT NULL,
    well_id integer NOT NULL,
    hole_depth_feet double precision,
    rate_of_penetration_ft_per_hr double precision,
    time_of_penetration_min_per_ft double precision,
    bit_depth_feet double precision,
    hook_load_klbs double precision,
    standpipe_pressure_psi double precision,
    pump_1_strokes_min_spm double precision,
    pump_2_strokes_min_spm double precision,
    rotary_rpm_rpm double precision,
    weight_on_bit_klbs double precision,
    on_bottom_rop_ft_per_hr double precision,
    line_wear_ton_miles double precision,
    pump_1_total_strokes_strokes double precision,
    pump_2_total_strokes_strokes double precision,
    total_pump_output_gal_per_min double precision,
    totalpumpdisplacement_barrels double precision,
    block_height_feet double precision,
    pump_3_total_strokes_strokes double precision,
    on_bottom_hours_hrs double precision,
    circulating_hours_hrs double precision,
    over_pull_klbs double precision,
    fill_strokes_strokes double precision,
    total_fill_strokes_strokes double precision,
    differential_pressure_psi double precision,
    trip_speed_ft_per_min double precision,
    pump_4_total_strokes_strokes double precision,
    total_strokes_p1plusp2plusp3plusp4_strokes double precision,
    motor_rpm_rpm double precision,
    yyyy_mm_dd text,
    hh_mm_ss text,
    src_id bigint
);

ALTER TABLE ONLY ddv.annotations ALTER COLUMN id SET DEFAULT nextval('ddv.annotations_id_seq'::regclass);

ALTER TABLE ONLY ddv.well_data ALTER COLUMN id SET DEFAULT nextval('ddv.well_data_id_seq'::regclass);

ALTER TABLE ONLY ddv.annotations
    ADD CONSTRAINT annotations_pkey PRIMARY KEY (id);

ALTER TABLE ONLY ddv.well_data
    ADD CONSTRAINT well_data_pkey PRIMARY KEY (id);

ALTER TABLE ONLY ddv.well_data_time
    ADD CONSTRAINT well_data_time_pkey PRIMARY KEY (id);

CREATE INDEX idx_well_data_bit_depth ON ddv.well_data USING btree (bit_depth_feet);

CREATE INDEX idx_well_data_time_well_id_id ON ddv.well_data_time USING btree (well_id, id);

CREATE INDEX idx_well_data_well_id_id ON ddv.well_data USING btree (well_id, id);

CREATE INDEX ix_annotations_id ON ddv.annotations USING btree (id);

CREATE INDEX ix_annotations_well_id ON ddv.annotations USING btree (well_id);

CREATE INDEX ix_wdt_src_id ON ddv.well_data_time USING btree (src_id);

CREATE INDEX well_data_time_bit_depth_feet_idx ON ddv.well_data_time USING btree (bit_depth_feet);

ALTER TABLE ONLY ddv.annotations
    ADD CONSTRAINT annotations_well_id_fkey FOREIGN KEY (well_id) REFERENCES ddv.wells(id);

ALTER TABLE ONLY ddv.well_data
    ADD CONSTRAINT well_data_well_id_fkey FOREIGN KEY (well_id) REFERENCES ddv.wells(id);
