from enum import Enum


class OpsRole(str, Enum):
    RIG_SUPERVISOR = "rig_supervisor"
    SITE_GEOLOGIST = "site_geologist"
    OFFICE_ENGINEER = "office_engineer"
    ADMIN = "admin"
    READ_ONLY = "read_only"
