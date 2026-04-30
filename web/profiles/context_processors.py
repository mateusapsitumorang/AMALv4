def user_preferences(request):
    if request.user.is_authenticated:
        try:
            from userprofile.models import UserProfile
            p = UserProfile.objects.get(user=request.user)
            return {
                'pref_compact':    p.display_compact,
                'pref_timestamps': p.display_timestamps,
            }
        except:
            pass
    return {'pref_compact': False, 'pref_timestamps': True}


def profile_context(request):
    if request.user.is_authenticated:
        try:
            from userprofile.models import UserProfile
            profile_obj = UserProfile.objects.get(user=request.user)
        except Exception:
            profile_obj = None
        return {'profile_obj': profile_obj}
    return {'profile_obj': None}