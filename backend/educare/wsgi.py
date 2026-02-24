import os
from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'educare.settings')
application = get_wsgi_application()

# Vercel requires this named 'app'
app = application
