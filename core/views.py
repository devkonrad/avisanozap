
import re
from urllib.parse import quote

from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import redirect
from django.views.generic import TemplateView

from billing.models import BillingPlan


class LandingPageView(TemplateView):
    template_name = "landing/home.html"

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect("appointments_dashboard")

        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        billing_plans = BillingPlan.objects.filter(
            is_active=True,
        ).order_by("sort_order", "name")

        context["billing_plans"] = billing_plans
        context["billing_plan"] = billing_plans.first()

        support_phone = re.sub(
            r"\D",
            "",
            settings.WHATSAPP_SUPPORT_PHONE,
        )

        context["whatsapp_support_url"] = (
            f"https://wa.me/{support_phone}"
            f"?text={quote('Olá! Gostaria de conhecer o AvisanoZap.')}"
            if support_phone
            else ""
        )

        return context


def robots_txt_view(request):
    content = """\
User-agent: *
Allow: /

Disallow: /admin/
Disallow: /api/
Disallow: /accounts/
Disallow: /dashboard/
Disallow: /billing/

Sitemap: https://avisanozap.com.br/sitemap.xml
"""
    return HttpResponse(
        content,
        content_type="text/plain; charset=utf-8",
    )
