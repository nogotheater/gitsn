import re
from hashlib import sha256
from pathlib import Path
from django import template
from django.contrib.staticfiles import finders
from django.templatetags.static import static
register = template.Library()


@register.simple_tag
def versioned_static(path):
    """Change the asset URL when its bytes change, including across rebuilds."""
    url = static(path)
    filename = finders.find(path)
    if not filename:
        return url
    version = sha256(Path(filename).read_bytes()).hexdigest()[:16]
    return url + ('&' if '?' in url else '?') + 'v=' + version


@register.filter
def badge_color(value):
    return value if isinstance(value, str) and re.fullmatch(r'#[0-9a-fA-F]{6}', value) else '#6B7580'
