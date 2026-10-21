import logging
from uuid import UUID
from django import forms
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse, QueryDict
from django.shortcuts import render
from django.template.loader import render_to_string
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET
from playwright.sync_api import Error as PlaywrightError
from .portal_forms import PerformanceFilterForm
from .services.access import audience_for_user
from .services.printing import print_document, document_assets, render_pdf, SCOPE_CHOICES


class OutputScopeForm(forms.Form):
    scope = forms.ChoiceField(label='출력할 고객사', choices=SCOPE_CHOICES)


def selected_product_order(products, validated_values):
    """Preserve canonical request order after the form has checked every ID."""
    rank = {}
    for value in validated_values:
        rank.setdefault(UUID(str(value)), len(rank))
    return sorted(products, key=lambda product: rank[product.pk])


def context_for(request):
    audience = audience_for_user(request.user)
    form = PerformanceFilterForm(request.GET)
    # Employees see public and private customers together on the web list, so the printed
    # document starts from the same set; they can still narrow it from the preview.
    scope = request.GET.get('scope') or 'all'
    if audience == 'partner' and scope != 'all':
        raise PermissionDenied
    scope_form = OutputScopeForm({'scope': scope})
    valid = form.is_valid() and scope_form.is_valid()
    if not valid:
        return {'form': form, 'scope_form': scope_form, 'is_partner': audience == 'partner'}, False
    form.cleaned_data['products'] = selected_product_order(form.cleaned_data['products'], request.GET.getlist('products'))
    document = print_document(request.user, form.cleaned_data, scope)
    query = QueryDict('', mutable=True)
    query.setlist('products', [str(p.pk) for p in form.cleaned_data['products']])
    query.setlist('category', form.cleaned_data['category'])
    query['scope'] = scope
    return {**document, **document_assets(), 'scope_form': scope_form, 'query': query.urlencode(),
            'selected_products': [str(p.pk) for p in form.cleaned_data['products']],
            'selected_categories': form.cleaned_data['category']}, True


@login_required
@never_cache
@require_GET
def preview(request):
    context, valid = context_for(request)
    if not valid:
        return render(request, 'portal/print_error.html', context, status=400)
    return render(request, 'portal/print_document.html', {**context, 'show_controls': True})


@login_required
@never_cache
@require_GET
def download(request):
    context, valid = context_for(request)
    if not valid:
        return render(request, 'portal/print_error.html', context, status=400)
    html = render_to_string('portal/print_document.html', {**context, 'show_controls': False})
    try:
        result = render_pdf(html)
    except (PlaywrightError, OSError, RuntimeError):
        logging.getLogger(__name__).exception('Reference PDF generation failed')
        return render(request, 'portal/print_error.html', {'pdf_failed': True}, status=503)
    response = HttpResponse(result, content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="gitsn-references-' + context['date'].strftime('%Y%m%d') + '.pdf"'
    response['Content-Length'] = len(result)
    return response
