from pathlib import Path
from decouple import config

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_LOCAL_ORIGINS = [
    'http://localhost:3000',
    'http://127.0.0.1:3000',
    'http://192.168.1.11:3000',
]


def _split_csv(value):
    return [item.strip() for item in value.split(',') if item.strip()]

SECRET_KEY = config('DJANGO_SECRET_KEY', default='replace-me-with-a-secure-key')
DEBUG = config('DEBUG', default=True, cast=bool)
ALLOWED_HOSTS = _split_csv(
    config('ALLOWED_HOSTS', default='localhost,127.0.0.1')
)

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'daphne',
    'django.contrib.staticfiles',
    'channels',
    'corsheaders',
    'rest_framework',
    'accounts',
    'learning',
    'agents',
    'analytics',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'xiavlearn.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
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

WSGI_APPLICATION = 'xiavlearn.wsgi.application'
ASGI_APPLICATION = 'xiavlearn.asgi.application'

DATABASE_ENGINE = config('DB_ENGINE', default='django.db.backends.sqlite3')
if DATABASE_ENGINE == 'django.db.backends.sqlite3':
    DATABASES = {
        'default': {
            'ENGINE': DATABASE_ENGINE,
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': DATABASE_ENGINE,
            'NAME': config('POSTGRES_DB', default='xiavlearn'),
            'USER': config('POSTGRES_USER', default='postgres'),
            'PASSWORD': config('POSTGRES_PASSWORD', default='postgres'),
            'HOST': config('POSTGRES_HOST', default='localhost'),
            'PORT': config('POSTGRES_PORT', default='5432'),
            'CONN_MAX_AGE': config('DB_CONN_MAX_AGE', default=60, cast=int),
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Manila'
USE_I18N = True
USE_L10N = True
USE_TZ = True

STATIC_URL = '/static/'
MEDIA_ROOT = BASE_DIR
MEDIA_URL = '/media/'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

CORS_ALLOWED_ORIGINS = _split_csv(
    config('CORS_ALLOWED_ORIGINS', default=','.join(DEFAULT_LOCAL_ORIGINS))
)
CORS_ALLOW_CREDENTIALS = True
CSRF_TRUSTED_ORIGINS = _split_csv(
    config('CSRF_TRUSTED_ORIGINS', default=','.join(DEFAULT_LOCAL_ORIGINS))
)
SESSION_COOKIE_SECURE = config('SESSION_COOKIE_SECURE', default=False, cast=bool)
CSRF_COOKIE_SECURE = config('CSRF_COOKIE_SECURE', default=False, cast=bool)
SESSION_COOKIE_SAMESITE = config('SESSION_COOKIE_SAMESITE', default='Lax')
CSRF_COOKIE_SAMESITE = config('CSRF_COOKIE_SAMESITE', default='Lax')
SECURE_SSL_REDIRECT = config('SECURE_SSL_REDIRECT', default=False, cast=bool)
SECURE_HSTS_SECONDS = config('SECURE_HSTS_SECONDS', default=0, cast=int)
SECURE_HSTS_INCLUDE_SUBDOMAINS = config(
    'SECURE_HSTS_INCLUDE_SUBDOMAINS',
    default=False,
    cast=bool,
)
SECURE_HSTS_PRELOAD = config('SECURE_HSTS_PRELOAD', default=False, cast=bool)
SECURE_REFERRER_POLICY = config('SECURE_REFERRER_POLICY', default='same-origin')
USE_X_FORWARDED_PROTO = config('USE_X_FORWARDED_PROTO', default=False, cast=bool)
if USE_X_FORWARDED_PROTO:
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
        'rest_framework.authentication.BasicAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'EXCEPTION_HANDLER': 'xiavlearn.api.api_exception_handler',
}

CHANNEL_LAYER_BACKEND = config(
    'CHANNEL_LAYER_BACKEND',
    default='channels.layers.InMemoryChannelLayer',
).strip()
CHANNEL_REDIS_URL = config('CHANNEL_REDIS_URL', default='').strip()
if CHANNEL_REDIS_URL:
    CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'channels_redis.core.RedisChannelLayer',
            'CONFIG': {
                'hosts': [CHANNEL_REDIS_URL],
            },
        }
    }
else:
    CHANNEL_LAYERS = {
        'default': {
            'BACKEND': CHANNEL_LAYER_BACKEND,
        }
    }

VOICE_CONVERSATION_REALTIME_STT_FORWARD_TIMEOUT_SECONDS = config(
    'VOICE_CONVERSATION_REALTIME_STT_FORWARD_TIMEOUT_SECONDS',
    default=10,
    cast=int,
)
VOICE_CONVERSATION_REALTIME_AI_TIMEOUT_SECONDS = config(
    'VOICE_CONVERSATION_REALTIME_AI_TIMEOUT_SECONDS',
    default=45,
    cast=int,
)
VOICE_CONVERSATION_REALTIME_TTS_TIMEOUT_SECONDS = config(
    'VOICE_CONVERSATION_REALTIME_TTS_TIMEOUT_SECONDS',
    default=45,
    cast=int,
)
VOICE_CONVERSATION_REALTIME_IDLE_TIMEOUT_SECONDS = config(
    'VOICE_CONVERSATION_REALTIME_IDLE_TIMEOUT_SECONDS',
    default=120,
    cast=int,
)
VOICE_CONVERSATION_REALTIME_IDLE_POLL_SECONDS = config(
    'VOICE_CONVERSATION_REALTIME_IDLE_POLL_SECONDS',
    default=5,
    cast=int,
)
VOICE_CONVERSATION_REALTIME_MAX_EVENTS_PER_MINUTE = config(
    'VOICE_CONVERSATION_REALTIME_MAX_EVENTS_PER_MINUTE',
    default=240,
    cast=int,
)
VOICE_CONVERSATION_REALTIME_MAX_AUDIO_CHUNKS_PER_MINUTE = config(
    'VOICE_CONVERSATION_REALTIME_MAX_AUDIO_CHUNKS_PER_MINUTE',
    default=180,
    cast=int,
)
VOICE_CONVERSATION_REALTIME_MAX_AUDIO_BYTES_PER_MINUTE = config(
    'VOICE_CONVERSATION_REALTIME_MAX_AUDIO_BYTES_PER_MINUTE',
    default=8 * 1024 * 1024,
    cast=int,
)
VOICE_CONVERSATION_REALTIME_DUPLICATE_TRANSCRIPT_WINDOW_SECONDS = config(
    'VOICE_CONVERSATION_REALTIME_DUPLICATE_TRANSCRIPT_WINDOW_SECONDS',
    default=3,
    cast=int,
)

DEEPGRAM_API_KEY = config('DEEPGRAM_API_KEY', default='')
DEEPGRAM_TTS_MODEL = config('DEEPGRAM_TTS_MODEL', default='aura-2-thalia-en')
DEEPGRAM_STT_MODEL = config('DEEPGRAM_STT_MODEL', default='nova-2')
DEEPGRAM_REALTIME_STT_MODEL = config('DEEPGRAM_REALTIME_STT_MODEL', default='nova-3')
DEEPGRAM_REALTIME_STT_LANGUAGE = config('DEEPGRAM_REALTIME_STT_LANGUAGE', default='en')
DEEPGRAM_REALTIME_STT_UTTERANCE_END_MS = config(
    'DEEPGRAM_REALTIME_STT_UTTERANCE_END_MS',
    default=1200,
    cast=int,
)
DEEPGRAM_REALTIME_STT_KEEPALIVE_SECONDS = config(
    'DEEPGRAM_REALTIME_STT_KEEPALIVE_SECONDS',
    default=8,
    cast=int,
)
USE_VOICE_DIAGNOSTIC = config('USE_VOICE_DIAGNOSTIC', default=False, cast=bool)

LOG_LEVEL = config('LOG_LEVEL', default='INFO').upper()
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'standard': {
            'format': '%(asctime)s %(levelname)s %(name)s %(message)s',
        }
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'standard',
        }
    },
    'root': {
        'handlers': ['console'],
        'level': LOG_LEVEL,
    },
    'loggers': {
        'agents': {
            'handlers': ['console'],
            'level': LOG_LEVEL,
            'propagate': False,
        }
    },
}
