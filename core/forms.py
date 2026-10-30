from django import forms


class StyledFormMixin:
    """Apply the shadcn control classes to every widget."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                widget.attrs.setdefault('class', 'checkbox')
            elif isinstance(widget, forms.SelectMultiple):
                widget.attrs.setdefault('class', 'select min-h-28')
            elif isinstance(widget, forms.Select):
                widget.attrs.setdefault('class', 'select')
            elif isinstance(widget, forms.Textarea):
                widget.attrs.setdefault('class', 'input min-h-24')
                widget.attrs.setdefault('rows', 3)
            elif isinstance(widget, forms.CheckboxSelectMultiple):
                widget.attrs.setdefault('class', 'checkbox-list')
            else:
                widget.attrs.setdefault('class', 'input')
            if field.required:
                widget.attrs.setdefault('required', 'required')


class StyledModelForm(StyledFormMixin, forms.ModelForm):
    pass


class StyledForm(StyledFormMixin, forms.Form):
    pass
