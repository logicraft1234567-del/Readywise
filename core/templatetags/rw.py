from django import template
register = template.Library()
@register.filter
def mmss(v):
    v = int(v or 0); return f"{v//60:02d}:{v%60:02d}"
