
from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from appointments.models import ProfessionalProfile


class StaticViewSitemap(Sitemap):
    protocol = "https"

    def items(self):
        return ["home"]

    def location(self, item):
        return reverse(item)


class ProfessionalProfileSitemap(Sitemap):
    protocol = "https"

    def items(self):
        return (
            ProfessionalProfile.objects
            .exclude(slug="")
            .order_by("slug")
        )

    def location(self, item):
        return reverse(
            "public_schedule",
            kwargs={"slug": item.slug},
        )
