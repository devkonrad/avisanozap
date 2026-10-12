from django.shortcuts import render, get_object_or_404
from .models import ProfessionalProfile

def public_schedule_view(request, slug):
    profile = get_object_or_404(ProfessionalProfile, slug=slug)
    services = profile.services.filter(is_active=True)
    
    context = {
        'profile_name': profile.slug.replace('-', ' ').title(),
        'profile': profile,
        'services': services,
    }
    return render(request, 'appointments/public_schedule.html', context)
