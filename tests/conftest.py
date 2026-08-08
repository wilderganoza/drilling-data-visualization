import os

# ENVIRONMENT default es "production" y el validador de Settings rechaza el
# SECRET_KEY placeholder en producción; los tests corren como development.
os.environ.setdefault("ENVIRONMENT", "development")
