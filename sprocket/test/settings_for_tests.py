



DEBUG = True
TEMPLATE_DEBUG = True

TIME_ZONE = 'America/New_York'

INSTALLED_APPS = (
    'sprocket',
)

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'cosdev'
        }
    }    

ROOT_URLCONF = ''

