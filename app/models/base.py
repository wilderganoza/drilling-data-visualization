# Importamos declarative_base para crear nuestro propio registro de clases mapeadas
from sqlalchemy.orm import declarative_base # Base declarativa de SQLAlchemy
from app.models.legacy import Base as LegacyBase # Base legacy, de la que reutilizamos el MetaData compartido

# Creamos un registro declarativo separado de app.models.legacy.Base (un set distinto de
# clases mapeadas), pero compartiendo el objeto MetaData de la Base legacy — lo necesitamos
# porque las tablas de ops tienen FKs reales hacia tablas legacy (users.id, wells.id), y
# SQLAlchemy solo resuelve ForeignKey en forma de string dentro de un mismo MetaData, no
# entre dos distintos. La llamada a create_all() de DatabaseManager.initialize() está acotada
# a una lista explícita de tablas (solo las legacy) precisamente para que compartir este
# MetaData no cree automáticamente las tablas ops_* — esas vienen de las migraciones
# SQL versionadas en supabase/migrations/.
OpsBase = declarative_base(metadata=LegacyBase.metadata)
