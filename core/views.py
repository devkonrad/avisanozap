from django.views.generic import TemplateView
from billing.models import BillingPlan


class LandingPageView(TemplateView):
    template_name = "landing/home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["billing_plans"] = BillingPlan.objects.filter(
            is_active=True,
        ).order_by("sort_order", "name")
        return context
