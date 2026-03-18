from django import template

register = template.Library()


@register.filter(name='dict_get')
def dict_get(d, key):
    """Lookup a dictionary value by key in Django templates."""
    if isinstance(d, dict):
        return d.get(key, 0)
    return 0
