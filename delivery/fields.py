from django import forms
from django.core.exceptions import ValidationError
from django.db import models
from .domain.quantities import positive_quantity

def clean_quantity(value):
    try:
        return positive_quantity(value)
    except ValueError as exc:
        raise ValidationError(str(exc), code="invalid_quantity") from exc

class QuantityFormField(forms.Field):
    def to_python(self, value):
        return clean_quantity(value)

class PositiveQuantityField(models.PositiveBigIntegerField):
    """Reject floats/booleans before Django could coerce them to integers."""
    description = "Required positive whole product quantity"

    def to_python(self, value):
        return clean_quantity(value)

    def get_prep_value(self, value):
        return clean_quantity(value)

    def formfield(self, **kwargs):
        options = {"required": True, "label": self.verbose_name}
        options.update(kwargs)
        return QuantityFormField(**options)
