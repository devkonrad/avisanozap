import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ["SECRET_KEY"]

DEBUG = os.getenv("DEBUG", "0").lower() in ("1", "true", "yes")

ALLOWED_HOSTS = [
    host.strip()
    for host in os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if host.strip()
]

CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CSRF_TRUSTED_ORIGINS", "").split(",")
    if origin.strip()
]

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'appointments',
    'billing',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'core.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'core.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ.get('POSTGRES_DB', 'saas_db'),
        'USER': os.environ.get('POSTGRES_USER', 'saas_user'),
        'PASSWORD': os.environ.get('POSTGRES_PASSWORD', 'saas_pass'),
        'HOST': 'db',
        'PORT': '5432',
    }
}

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

# Celery and Redis settings
CELERY_BROKER_URL = os.environ.get(
    "CELERY_BROKER_URL",
    "redis://redis:6379/0",
)
CELERY_RESULT_BACKEND = os.environ.get(
    "CELERY_RESULT_BACKEND",
    "redis://redis:6379/0",
)
CELERY_TIMEZONE = "America/Sao_Paulo"
CELERY_USE_TZ = True

# Celery Beat schedule
CELERY_BEAT_SCHEDULE = {
    "process-whatsapp-reminders-every-minute": {
        "task": "appointments.tasks.process_pending_reminders",
        "schedule": 60.0,
    },
}

# Evolution API settings
EVOLUTION_API_URL = os.environ.get(
    "EVOLUTION_API_URL",
    "http://whatsapp_api:8080",
)
EVOLUTION_API_KEY = os.environ["EVOLUTION_API_KEY"]
EVOLUTION_WEBHOOK_TOKEN = os.environ["EVOLUTION_WEBHOOK_TOKEN"]
EVOLUTION_INSTANCE_NAME = os.environ.get(
    "EVOLUTION_INSTANCE_NAME",
    "avisanozap",
)

# Asaas Integration
ASAAS_BASE_URL = os.environ.get(
    'ASAAS_BASE_URL',
    'https://api-sandbox.asaas.com/v3',
).rstrip('/')

# Assas
ASAAS_API_KEY = os.environ.get('ASAAS_API_KEY', '')
ASAAS_WEBHOOK_TOKEN = os.environ.get('ASAAS_WEBHOOK_TOKEN', '')

# Mercado Pago
MERCADO_PAGO_ACCESS_TOKEN = os.environ.get(
    'MERCADO_PAGO_ACCESS_TOKEN',
    '',
)
MERCADO_PAGO_WEBHOOK_SECRET = os.environ.get(
    'MERCADO_PAGO_WEBHOOK_SECRET',
    '',
)

LOGIN_URL = "/accounts/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/"
