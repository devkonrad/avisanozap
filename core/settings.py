import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = 'fi$d^a_u8j$eb-_##$v9*47_nvue_2q4r_in^7i_$m1khh(%8v'

DEBUG = False

ALLOWED_HOSTS = ['localhost','127.0.0.1']

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'appointments',
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

STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Configurações do Celery e Redis
CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', 'redis://redis:6379/0')
CELERY_RESULT_BACKEND = os.environ.get('CELERY_RESULT_BACKEND', 'redis://redis:6379/0')
CELERY_TIMEZONE = 'America/Sao_Paulo'
CELERY_USE_TZ = True

# Agendador de tarefas periódicas (Celery Beat)
CELERY_BEAT_SCHEDULE = {
    'process-whatsapp-reminders-every-minute': {
        'task': 'appointments.tasks.process_pending_reminders',
        'schedule': 60.0,  # Executa a cada 60 segundos
    },
}

# Configurações da Evolution API
# Configurações da Evolution API
EVOLUTION_API_URL = os.environ.get('EVOLUTION_API_URL', 'http://whatsapp_api:8080')
EVOLUTION_API_KEY = os.environ.get('EVOLUTION_API_KEY', 'SUA_API_KEY_AQUI')
EVOLUTION_INSTANCE_NAME = os.environ.get('EVOLUTION_INSTANCE_NAME', 'sua_instancia')
